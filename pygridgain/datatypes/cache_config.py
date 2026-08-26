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
    'MAX_HNSW_EF_CONSTRUCTION', 'VectorQuantization', 'VECTOR_SEGMENTS_ENGINE_DEFAULT',
    'MAX_VECTOR_INDEX_SEGMENTS', 'MAX_VECTOR_QUERY_THREADS'
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

#: Leaving the segment target or the query-thread count at this value lets the engine choose.
#: Mirrors ``QueryIndex.HNSW_ENGINE_DEFAULT``, which the server reuses for both.
VECTOR_SEGMENTS_ENGINE_DEFAULT = 0

#: Largest segment target the engine accepts (``QueryIndex.MAX_VECTOR_INDEX_SEGMENTS``). The
#: server refuses a value outside 1..this rather than narrowing it.
MAX_VECTOR_INDEX_SEGMENTS = 1024

#: Largest per-query thread count the engine accepts (``QueryIndex.MAX_VECTOR_QUERY_THREADS``).
#: A thread count is a resource commitment taken on every query, so it is refused, not clamped.
MAX_VECTOR_QUERY_THREADS = 64


class VectorQuantization(Int):
    """
    How a VECTOR index stores its vectors. Ordinals mirror ``org.apache.ignite.cache
    .VectorQuantization`` on the server, and the wire carries the ordinal.

    ``INT8`` was added after the quantization field itself shipped, so it needs its own feature
    bit: a peer that reads the field but does not know this value resolves it to
    ``ENGINE_DEFAULT`` and builds a full-precision index without reporting anything.
    """

    ENGINE_DEFAULT = 0
    NONE = 1
    BINARY = 2
    INT8 = 3


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

    #: ``(name, unset_value)`` pairs for the HNSW build parameters. Known whatever the
    #: negotiated layout is, so that asking for one where it cannot apply is reported rather
    #: than dropped: silently building a graph the caller did not ask for is worse than
    #: failing, and a dropped parameter is invisible until someone measures recall.
    hnsw_params = attr.ib(type=tuple, default=())

    #: Whether the negotiated protocol can carry :attr:`hnsw_params` at all.
    hnsw_supported = attr.ib(type=bool, default=False)

    #: ``(name, unset_value)`` pairs for the per-index segment parameters, known whatever the
    #: negotiated layout is, for the same reason as :attr:`hnsw_params`.
    segment_params = attr.ib(type=tuple, default=())

    #: Whether the negotiated protocol can carry :attr:`segment_params` at all.
    segment_supported = attr.ib(type=bool, default=False)

    #: Whether the negotiated protocol can carry the vector storage mode at all.
    quantization_supported = attr.ib(type=bool, default=False)

    #: Whether the negotiated protocol knows the ``INT8`` storage mode specifically.
    int8_supported = attr.ib(type=bool, default=False)

    def _following_for(self, index_type) -> list:
        if index_type == IndexType.VECTOR:
            return self.following
        return [(name, el) for name, el in self.following if name not in self.vector_only]

    def _validate(self, value):
        self._validate_group(value, self.hnsw_params, self.hnsw_supported,
                             'per-index HNSW build parameters')
        self._validate_group(value, self.segment_params, self.segment_supported,
                             'per-index vector segment parameters')
        self._validate_quantization(value)

    def _validate_group(self, value, params, supported, what):
        """
        Refuse a group of VECTOR-only parameters the wire cannot carry, rather than dropping it.

        The wire format gives a parameter on a non-VECTOR index nowhere to go, and a parameter the
        cluster never negotiated nowhere to go either. Dropping either is invisible until somebody
        measures recall or latency, so both are errors.
        """
        configured = [(name, value[name]) for name, unset in params
                      if value.get(name, unset) != unset]

        if not configured:
            return

        name, val = configured[0]
        where = f'({name}={val} on index {value.get("index_name")!r})'

        if value.get('index_type') != IndexType.VECTOR:
            raise ValueError(f'{what.capitalize()} are supported by VECTOR indexes only {where}')

        if not supported:
            raise NotSupportedByClusterError(f'The cluster does not support {what} {where}')

    def _validate_quantization(self, value):
        """
        Refuse a storage mode the peer cannot honour.

        Two separate refusals, because there are two ways to lose the request. A cluster with no
        quantization bit at all cannot carry the field. A cluster that has the field but not the
        INT8 bit reads the ordinal and resolves the value it does not know to the engine default,
        so the caller asks for byte codes and silently gets a full-precision index.
        """
        mode = value.get('quantization', VectorQuantization.ENGINE_DEFAULT)

        if mode == VectorQuantization.ENGINE_DEFAULT:
            return

        where = f'(quantization={mode} on index {value.get("index_name")!r})'

        if value.get('index_type') != IndexType.VECTOR:
            raise ValueError(f'Vector storage is supported by VECTOR indexes only {where}')

        if not self.quantization_supported:
            raise NotSupportedByClusterError(f'The cluster does not support per-index vector storage {where}')

        if mode == VectorQuantization.INT8 and not self.int8_supported:
            raise NotSupportedByClusterError(
                f'The cluster supports vector storage but not the INT8 mode {where}. INT8 is a value on a '
                f'field that shipped before it, so a peer can read the field and still not know the value: '
                f'sent anyway it resolves to the engine default and builds a full-precision index without '
                f'reporting anything.'
            )

    def _prepare(self, value) -> list:
        self._validate(value)
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


def _query_indexes(has_similarity: bool, has_hnsw_params: bool, has_quantization: bool = False,
                   has_segment_params: bool = False, has_int8: bool = False) -> QueryIndexArray:
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

    # Wire order follows the server's writer (ClientUtils.cacheConfiguration): quantization after
    # the graph parameters, then the segment pair. INT8 adds no field of its own -- it is a value
    # on this one -- so its bit gates the value rather than the layout.
    if has_quantization:
        following.append(('quantization', Int))
        defaults['quantization'] = VectorQuantization.ENGINE_DEFAULT
        vector_only.append('quantization')

    if has_segment_params:
        following.append(('max_segments', Int))
        following.append(('query_threads', Int))
        defaults['max_segments'] = VECTOR_SEGMENTS_ENGINE_DEFAULT
        defaults['query_threads'] = VECTOR_SEGMENTS_ENGINE_DEFAULT
        vector_only.extend(('max_segments', 'query_threads'))

    return QueryIndexArray(
        following,
        defaults=defaults,
        vector_only=tuple(vector_only),
        hnsw_params=(('hnsw_m', HNSW_ENGINE_DEFAULT),
                     ('hnsw_ef_construction', HNSW_ENGINE_DEFAULT)),
        hnsw_supported=has_hnsw_params,
        segment_params=(('max_segments', VECTOR_SEGMENTS_ENGINE_DEFAULT),
                        ('query_threads', VECTOR_SEGMENTS_ENGINE_DEFAULT)),
        segment_supported=has_segment_params,
        quantization_supported=has_quantization,
        int8_supported=has_int8,
    )


def query_entities_struct(has_similarity: bool, has_hnsw_params: bool, has_quantization: bool = False,
                          has_segment_params: bool = False, has_int8: bool = False) -> StructArray:
    """
    Query entities carrying the index layout for the given set of negotiated features.

    Memoised, and normalised before memoising. The cache config struct and the query-entities
    cache property must resolve to the SAME instance, and an ``lru_cache`` keyed on the argument
    tuple does not give that once parameters have defaults: ``(True, True)`` and
    ``(True, True, False, False, False)`` mean the same thing and would be two cache entries, so
    two layouts. Every caller therefore lands on one five-argument key.
    """
    return _query_entities_struct(bool(has_similarity), bool(has_hnsw_params), bool(has_quantization),
                                  bool(has_segment_params), bool(has_int8))


@lru_cache(maxsize=None)
def _query_entities_struct(has_similarity: bool, has_hnsw_params: bool, has_quantization: bool,
                           has_segment_params: bool, has_int8: bool) -> StructArray:
    """The memoised body of :func:`query_entities_struct`; arguments are already normalised."""
    return StructArray([
        ('key_type_name', String),
        ('value_type_name', String),
        ('table_name', String),
        ('key_field_name', String),
        ('value_field_name', String),
        ('query_fields', QueryFields),
        ('field_name_aliases', FieldNameAliases),
        ('query_indexes', _query_indexes(has_similarity, has_hnsw_params, has_quantization,
                                         has_segment_params, has_int8)),
    ])


def query_entities_for(protocol_context) -> StructArray:
    """
    Pick the query entities layout matching what this connection negotiated.
    """
    return query_entities_struct(
        bool(protocol_context.is_query_index_vector_similarity_supported()),
        bool(protocol_context.is_query_index_vector_hnsw_params_supported()),
        bool(protocol_context.is_query_index_vector_quantization_supported()),
        bool(protocol_context.is_query_index_vector_segment_params_supported()),
        bool(protocol_context.is_query_index_vector_int8_storage_supported()),
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
