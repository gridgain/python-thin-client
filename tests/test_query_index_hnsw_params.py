#
# Copyright 2026 GridGain Systems, Inc. and Contributors.
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
"""
Wire layout of the query index trailing fields (GG-49543).

The server appends ``similarity_function`` and the HNSW build parameters to an index only
when the matching feature bit was negotiated AND that index is a VECTOR index:

    if (writeSimilarityFunction && idx.getIndexType() == VECTOR)  writeInt(similarityId);
    if (writeHnswParams        && idx.getIndexType() == VECTOR) { writeInt(m); writeInt(ef); }

Both halves of that condition matter. These tests pin the bytes rather than the declared
field list, because a layout that is merely self-consistent still desynchronises the stream.
"""

import pytest

from pygridgain.connection.bitmask_feature import BitmaskFeature
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.datatypes.cache_config import (
    HNSW_ENGINE_DEFAULT, MAX_HNSW_EF_CONSTRUCTION, MAX_HNSW_M, IndexType,
    get_cache_config_struct, query_entities_struct,
)
from pygridgain.datatypes.cache_properties import prop_map
from pygridgain.datatypes.prop_codes import PROP_QUERY_ENTITIES
from pygridgain.stream.binary_stream import BinaryStream

# Feature flags only exist from 1.7.0; ProtocolContext drops them below that.
VERSION = (1, 7, 1)

SIMILARITY = BitmaskFeature.QUERY_INDEX_VECTOR_SIMILARITY
HNSW = BitmaskFeature.QUERY_INDEX_VECTOR_HNSW_PARAMS

BASE_INDEX_FIELDS = ['index_name', 'index_type', 'inline_size', 'fields']

ALL_COMBINATIONS = [(False, False), (True, False), (False, True), (True, True)]

SORTED_INDEX = {'index_name': 'by_name', 'index_type': IndexType.SORTED, 'inline_size': -1,
                'fields': [{'name': 'name'}]}
VECTOR_INDEX = {'index_name': 'by_embedding', 'index_type': IndexType.VECTOR, 'inline_size': -1,
                'fields': [{'name': 'embedding'}], 'similarity_function': 1,
                'hnsw_m': 16, 'hnsw_ef_construction': 100}


def context(*features):
    """A protocol context advertising exactly the given features."""
    mask = BitmaskFeature(0)
    for feature in features:
        mask |= feature
    return ProtocolContext(VERSION, mask)


def entity(indexes):
    return {
        'key_type_name': 'K', 'value_type_name': 'V', 'table_name': 'T',
        'key_field_name': None, 'value_field_name': None,
        'query_fields': [], 'field_name_aliases': [],
        # copied: serialization fills defaults into the dicts it is handed
        'query_indexes': [dict(index) for index in indexes],
    }


def serialize(has_similarity, has_hnsw_params, indexes):
    stream = BinaryStream(None)
    query_entities_struct(has_similarity, has_hnsw_params).from_python(stream, [entity(indexes)])
    return stream.getvalue()


def round_trip(has_similarity, has_hnsw_params, indexes):
    struct = query_entities_struct(has_similarity, has_hnsw_params)
    stream = BinaryStream(None, serialize(has_similarity, has_hnsw_params, indexes))
    c_type = struct.parse(stream)
    stream.seek(0)
    return struct.to_python(stream.read_ctype(c_type))[0]['query_indexes']


def declared_fields(has_similarity, has_hnsw_params):
    entities = query_entities_struct(has_similarity, has_hnsw_params)
    return [name for name, _ in dict(entities.following)['query_indexes'].following]


# --- the feature bit itself ------------------------------------------------------------

def test_feature_bit_is_38():
    # The server side is ClientBitmaskFeature.QUERY_INDEX_VECTOR_HNSW_PARAMS(38).
    assert HNSW == 1 << 38


def test_feature_is_advertised_as_supported():
    assert HNSW in BitmaskFeature.all_supported()


def test_hnsw_bounds_match_the_server():
    # Mirrors QueryIndex.HNSW_ENGINE_DEFAULT / MAX_HNSW_M / MAX_HNSW_EF_CONSTRUCTION.
    assert (HNSW_ENGINE_DEFAULT, MAX_HNSW_M, MAX_HNSW_EF_CONSTRUCTION) == (0, 512, 3200)


@pytest.mark.parametrize(
    'features, supported',
    [((), False), ((SIMILARITY,), False), ((HNSW,), True), ((SIMILARITY, HNSW), True)],
)
def test_protocol_context_reports_the_feature(features, supported):
    assert bool(context(*features).is_query_index_vector_hnsw_params_supported()) is supported


def test_feature_is_not_reported_below_1_7_0():
    # Below 1.7.0 the feature mask is dropped wholesale, so nothing may be claimed.
    stale = ProtocolContext((1, 6, 0), BitmaskFeature(0) | HNSW)
    assert not stale.is_query_index_vector_hnsw_params_supported()


# --- what actually goes on the wire ----------------------------------------------------

@pytest.mark.parametrize('has_similarity, has_hnsw_params', ALL_COMBINATIONS)
def test_non_vector_index_is_byte_identical_whatever_was_negotiated(has_similarity, has_hnsw_params):
    # The server writes and reads no trailing fields for a SORTED index under any feature
    # bit, so neither may the client: stray bytes here displace every index after them.
    baseline = serialize(False, False, [SORTED_INDEX])
    assert serialize(has_similarity, has_hnsw_params, [SORTED_INDEX]) == baseline


@pytest.mark.parametrize(
    'has_similarity, has_hnsw_params, extra_bytes',
    [
        (False, False, 0),
        (True, False, 4),           # similarity_function
        (False, True, 8),           # hnsw_m + hnsw_ef_construction
        (True, True, 12),           # all three
    ],
)
def test_vector_index_gains_exactly_the_negotiated_fields(has_similarity, has_hnsw_params, extra_bytes):
    baseline = len(serialize(False, False, [VECTOR_INDEX]))
    assert len(serialize(has_similarity, has_hnsw_params, [VECTOR_INDEX])) == baseline + extra_bytes


@pytest.mark.parametrize('indexes', [
    [SORTED_INDEX, VECTOR_INDEX],
    [VECTOR_INDEX, SORTED_INDEX],
])
def test_mixed_index_array_round_trips(indexes):
    # The regression that a flat layout causes: the trailing fields of one index get read
    # as the head of the next, and the array length of a later field becomes garbage.
    parsed = round_trip(True, True, indexes)

    assert [index['index_name'] for index in parsed] == [index['index_name'] for index in indexes]

    for original, actual in zip(indexes, parsed):
        assert actual['index_type'] == original['index_type']
        if original['index_type'] == IndexType.VECTOR:
            assert actual['similarity_function'] == original['similarity_function']
            assert actual['hnsw_m'] == original['hnsw_m']
            assert actual['hnsw_ef_construction'] == original['hnsw_ef_construction']
        else:
            assert 'similarity_function' not in actual
            assert 'hnsw_m' not in actual
            assert 'hnsw_ef_construction' not in actual


def test_vector_index_round_trips_the_engine_default():
    # Zero is "let the engine choose", and is what a pre-GG-49543 index deserializes to.
    index = dict(VECTOR_INDEX, hnsw_m=HNSW_ENGINE_DEFAULT, hnsw_ef_construction=HNSW_ENGINE_DEFAULT)
    parsed = round_trip(True, True, [index])[0]
    assert parsed['hnsw_m'] == HNSW_ENGINE_DEFAULT
    assert parsed['hnsw_ef_construction'] == HNSW_ENGINE_DEFAULT


def test_hnsw_params_default_to_engine_default_when_omitted():
    index = {k: v for k, v in VECTOR_INDEX.items() if not k.startswith('hnsw_')}
    parsed = round_trip(True, True, [index])[0]
    assert parsed['hnsw_m'] == HNSW_ENGINE_DEFAULT
    assert parsed['hnsw_ef_construction'] == HNSW_ENGINE_DEFAULT


def test_defaults_are_not_injected_into_a_non_vector_index():
    # A SORTED index has no HNSW parameters at all; filling them in would be misleading
    # to any caller that inspects the dict it passed in.
    index = dict(SORTED_INDEX)
    serialize(True, True, [index])
    assert 'hnsw_m' not in index
    assert 'similarity_function' not in index


# --- layout selection ------------------------------------------------------------------

@pytest.mark.parametrize(
    'has_similarity, has_hnsw_params, expected',
    [
        (False, False, BASE_INDEX_FIELDS),
        (True, False, BASE_INDEX_FIELDS + ['similarity_function']),
        (False, True, BASE_INDEX_FIELDS + ['hnsw_m', 'hnsw_ef_construction']),
        (True, True, BASE_INDEX_FIELDS + ['similarity_function', 'hnsw_m', 'hnsw_ef_construction']),
    ],
)
def test_declared_layout_tracks_the_negotiated_features(has_similarity, has_hnsw_params, expected):
    # Which trailing fields can exist at all, in wire order. Whether a given index carries
    # them is decided per index — see the byte-level tests above.
    assert declared_fields(has_similarity, has_hnsw_params) == expected


def test_layout_is_shared_between_config_and_property():
    # The cache config struct and the query entities property must agree byte for byte;
    # they agree because both resolve through the same memoised layout.
    ctx = context(SIMILARITY, HNSW)

    from_config = dict(get_cache_config_struct(ctx).fields)['query_entities']
    from_property = prop_map(PROP_QUERY_ENTITIES, ctx).prop_data_class

    assert from_config is from_property
    assert from_config is query_entities_struct(True, True)


@pytest.mark.parametrize(
    'features, has_similarity, has_hnsw_params',
    [((), False, False), ((SIMILARITY,), True, False), ((SIMILARITY, HNSW), True, True)],
)
def test_cache_config_struct_selects_the_negotiated_layout(features, has_similarity, has_hnsw_params):
    struct = get_cache_config_struct(context(*features))
    assert dict(struct.fields)['query_entities'] is query_entities_struct(has_similarity, has_hnsw_params)


def test_bytes_are_unchanged_against_a_cluster_without_bit_38():
    # Compatibility promise: a cluster that predates bit 38 must see exactly what it saw
    # before this change, for vector and non-vector indexes alike.
    ctx = context(SIMILARITY)
    assert prop_map(PROP_QUERY_ENTITIES, ctx).prop_data_class is query_entities_struct(True, False)
    assert declared_fields(True, False) == BASE_INDEX_FIELDS + ['similarity_function']


def test_prop_map_without_context_keeps_the_legacy_default():
    from pygridgain.datatypes.cache_properties import PropQueryEntities

    assert prop_map(PROP_QUERY_ENTITIES) is PropQueryEntities
