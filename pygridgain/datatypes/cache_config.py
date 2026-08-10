#
# Copyright 2019 GridGain Systems, Inc. and Contributors.
#
# Licensed under the GridGain Community Edition License (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.gridgain.com/products/software/community-edition/gridgain-community-edition-license
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import asyncio
from functools import lru_cache

import attr

from pygridgain.exceptions import NotSupportedByClusterError, ParseError
from ..stream import READ_BACKWARD
from . import ExpiryPolicy
from .standard import String
from .internal import AnyDataObject, Struct, StructArray
from .primitive import *


__all__ = [
    'get_cache_config_struct', 'CacheMode', 'PartitionLossPolicy',
    'RebalanceMode', 'WriteSynchronizationMode', 'IndexType',
    'CacheAtomicityMode', 'HNSW_ENGINE_DEFAULT', 'MAX_HNSW_M',
    'MAX_HNSW_EF_CONSTRUCTION'
]


#: Leaving an HNSW build parameter at this value lets the vector engine choose it. Mirrors
#: ``QueryIndex.HNSW_ENGINE_DEFAULT`` on the server. Note that an index read back from a
#: cluster that does not send these parameters has the keys *absent* from its dict rather
#: than set to this value.
HNSW_ENGINE_DEFAULT = 0

#: Largest number of graph connections per node the vector engine accepts. Enforced by the
#: server (QueryUtils.validateHnswParams); mirrored here so callers can validate up front.
MAX_HNSW_M = 512

#: Largest build-time beam width the vector engine accepts. Server-enforced, as above.
MAX_HNSW_EF_CONSTRUCTION = 3200


class CacheMode(Int):
    LOCAL = 0
    REPLICATED = 1
    PARTITIONED = 2


class PartitionLossPolicy(Int):
    READ_ONLY_SAFE = 0
    READ_ONLY_ALL = 1
    READ_WRITE_SAFE = 2
    READ_WRITE_ALL = 3
    IGNORE = 4


class RebalanceMode(Int):
    SYNC = 0
    ASYNC = 1
    NONE = 2


class WriteSynchronizationMode(Int):
    FULL_SYNC = 0
    FULL_ASYNC = 1
    PRIMARY_SYNC = 2


class IndexType(Byte):
    SORTED = 0
    FULLTEXT = 1
    GEOSPATIAL = 2
    VECTOR = 3


class CacheAtomicityMode(Int):
    TRANSACTIONAL = 0
    ATOMIC = 1


QueryFields = StructArray([
    ('name', String),
    ('type_name', String),
    ('is_key_field', Bool),
    ('is_notnull_constraint_field', Bool),
    ('default_value', AnyDataObject),
    ('precision', Int),
    ('scale', Int),
], defaults={
    'is_key_field': False,
    'is_notnull_constraint_field': False,
    'default_value': None,
    'precision': -1,
    'scale': -1,
})


FieldNameAliases = StructArray([
    ('field_name', String),
    ('alias', String),
])


Fields = StructArray([
    ('name', String),
    ('is_descending', Bool),
], defaults={
    'is_descending': False,
})


@attr.s
class QueryIndexArray(StructArray):
    """
    Query indexes, whose trailing fields belong to VECTOR indexes only.

    The server appends ``similarity_function`` and the HNSW build parameters to an index only
    when the matching feature bit was negotiated **and** that index is a VECTOR index, so the
    element layout varies within one array. A flat layout breaks both directions: writing the
    fields on a non-VECTOR index leaves bytes the server never reads, and parsing them where
    the server never wrote them consumes the head of the next index — which then yields an
    absurd field count rather than an error.
    """

    #: Names the server writes for VECTOR indexes only, in wire order.
    vector_only = attr.ib(type=tuple, default=())

    #: ``(name, unset_value)`` pairs this negotiated layout cannot carry at all. Asking for
    #: one of them is refused rather than dropped: silently building a graph the caller did
    #: not ask for is worse than failing.
    unsupported = attr.ib(type=tuple, default=())

    def _following_for(self, index_type) -> list:
        if index_type == IndexType.VECTOR:
            return self.following
        return [(name, el) for name, el in self.following if name not in self.vector_only]

    def _reject_unsupported(self, value):
        if value.get('index_type') != IndexType.VECTOR:
            return
        for name, unset in self.unsupported:
            if value.get(name, unset) != unset:
                raise NotSupportedByClusterError(
                    f'The cluster does not support per-index HNSW build parameters '
                    f'({name}={value[name]} on index {value.get("index_name")!r})'
                )

    def _prepare(self, value) -> list:
        self._reject_unsupported(value)
        following = self._following_for(value.get('index_type'))
        for name, _ in following:
            if name in self.defaults:
                value.setdefault(name, self.defaults[name])
        return following

    def _element_following(self, element) -> list:
        known = {name for name, _ in self.following}
        present = [field[0] for field in element._fields_]
        unknown = [name for name in present if name not in known]
        if unknown:
            raise ParseError(f'Parsed query index carries unknown fields: {unknown}')
        return [(name, el) for name, el in self.following if name in set(present)]

    def from_python(self, stream, value):
        self._write_header(stream, len(value))

        for v in value:
            for name, el_class in self._prepare(v):
                el_class.from_python(stream, v[name])

    async def from_python_async(self, stream, value):
        self._write_header(stream, len(value))

        for v in value:
            for name, el_class in self._prepare(v):
                await el_class.from_python_async(stream, v[name])

    def parse(self, stream):
        fields, length = self._parse_header(stream)

        for i in range(length):
            el_fields, index_type = [], None
            for name, el_class in self.following:
                if name in self.vector_only and index_type != IndexType.VECTOR:
                    continue
                c_type = el_class.parse(stream)
                el_fields.append((name, c_type))
                if name == 'index_type':
                    index_type = stream.read_ctype(c_type, direction=READ_BACKWARD).value
            fields.append((f'element_{i}', Struct.build_c_type(el_fields)))

        return self.build_c_type(fields)

    async def parse_async(self, stream):
        fields, length = self._parse_header(stream)

        for i in range(length):
            el_fields, index_type = [], None
            for name, el_class in self.following:
                if name in self.vector_only and index_type != IndexType.VECTOR:
                    continue
                c_type = await el_class.parse_async(stream)
                el_fields.append((name, c_type))
                if name == 'index_type':
                    index_type = stream.read_ctype(c_type, direction=READ_BACKWARD).value
            fields.append((f'element_{i}', Struct.build_c_type(el_fields)))

        return self.build_c_type(fields)

    def to_python(self, ctypes_object, **kwargs):
        length = getattr(ctypes_object, 'length', 0)
        return [
            Struct(self._element_following(el), dict_type=dict).to_python(el, **kwargs)
            for el in (getattr(ctypes_object, f'element_{i}') for i in range(length))
        ]

    async def to_python_async(self, ctypes_object, **kwargs):
        length = getattr(ctypes_object, 'length', 0)
        result_coro = [
            Struct(self._element_following(el), dict_type=dict).to_python_async(el, **kwargs)
            for el in (getattr(ctypes_object, f'element_{i}') for i in range(length))
        ]
        return await asyncio.gather(*result_coro)


def _query_indexes(has_similarity: bool, has_hnsw_params: bool) -> QueryIndexArray:
    """
    Build the query index layout that the negotiated protocol actually puts on the wire.

    Which trailing fields exist at all is decided by the negotiated feature bits; whether a
    given index carries them is decided per index by :class:`QueryIndexArray`.
    """
    following = [
        ('index_name', String),
        ('index_type', IndexType),
        ('inline_size', Int),
        ('fields', Fields),
    ]
    defaults = {}
    vector_only = []
    unsupported = ()

    if has_similarity:
        following.append(('similarity_function', Int))
        defaults['similarity_function'] = 0
        vector_only.append('similarity_function')

    if has_hnsw_params:
        following.append(('hnsw_m', Int))
        following.append(('hnsw_ef_construction', Int))
        defaults['hnsw_m'] = HNSW_ENGINE_DEFAULT
        defaults['hnsw_ef_construction'] = HNSW_ENGINE_DEFAULT
        vector_only.extend(('hnsw_m', 'hnsw_ef_construction'))
    else:
        unsupported = (('hnsw_m', HNSW_ENGINE_DEFAULT),
                       ('hnsw_ef_construction', HNSW_ENGINE_DEFAULT))

    return QueryIndexArray(following, defaults=defaults,
                           vector_only=tuple(vector_only), unsupported=unsupported)


@lru_cache(maxsize=None)
def query_entities_struct(has_similarity: bool, has_hnsw_params: bool) -> StructArray:
    """
    Query entities carrying the index layout for the given pair of negotiated features.

    Memoised: the layout depends on nothing but the two flags, and both the cache config
    struct and the query-entities cache property need the same instance.
    """
    return StructArray([
        ('key_type_name', String),
        ('value_type_name', String),
        ('table_name', String),
        ('key_field_name', String),
        ('value_field_name', String),
        ('query_fields', QueryFields),
        ('field_name_aliases', FieldNameAliases),
        ('query_indexes', _query_indexes(has_similarity, has_hnsw_params)),
    ])


def query_entities_for(protocol_context) -> StructArray:
    """
    Pick the query entities layout matching what this connection negotiated.
    """
    return query_entities_struct(
        bool(protocol_context.is_query_index_vector_similarity_supported()),
        bool(protocol_context.is_query_index_vector_hnsw_params_supported()),
    )


# The two layouts that predate the HNSW build parameters, named because cache_properties
# binds them to its query entities properties.
QueryEntities = query_entities_struct(True, False)
QueryEntitiesNoSimilarity = query_entities_struct(False, False)


CacheKeyConfiguration = StructArray([
    ('type_name', String),
    ('affinity_key_field_name', String),
])


def get_cache_config_struct(protocol_context):
    fields = [
        ('length', Int),
        ('cache_atomicity_mode', CacheAtomicityMode),
        ('backups_number', Int),
        ('cache_mode', CacheMode),
        ('copy_on_read', Bool),
        ('data_region_name', String),
        ('eager_ttl', Bool),
        ('statistics_enabled', Bool),
        ('group_name', String),
        ('default_lock_timeout', Long),
        ('max_concurrent_async_operations', Int),
        ('max_query_iterators', Int),
        ('name', String),
        ('is_onheap_cache_enabled', Bool),
        ('partition_loss_policy', PartitionLossPolicy),
        ('query_detail_metric_size', Int),
        ('query_parallelism', Int),
        ('read_from_backup', Bool),
        ('rebalance_batch_size', Int),
        ('rebalance_batches_prefetch_count', Long),
        ('rebalance_delay', Long),
        ('rebalance_mode', RebalanceMode),
        ('rebalance_order', Int),
        ('rebalance_throttle', Long),
        ('rebalance_timeout', Long),
        ('sql_escape_all', Bool),
        ('sql_index_inline_max_size', Int),
        ('sql_schema', String),
        ('write_synchronization_mode', WriteSynchronizationMode),
        ('cache_key_configuration', CacheKeyConfiguration),
    ]
    fields.append(('query_entities', query_entities_for(protocol_context)))
    if protocol_context.is_expiry_policy_supported():
        fields.append(('expiry_policy', ExpiryPolicy))
    return Struct(fields=fields)
