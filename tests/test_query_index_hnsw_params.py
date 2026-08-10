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
Wire layout of the per-index HNSW build parameters (GG-49543).

The server appends ``hnsw_m`` and ``hnsw_ef_construction`` to a query index only when
feature bit 38 was negotiated. Get the layout wrong in either direction and the cache
configuration stream desynchronises, so these tests pin the field order and the gating
rather than any behaviour a cluster would show.
"""

import pytest

from pygridgain.connection.bitmask_feature import BitmaskFeature
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.datatypes.cache_config import (
    HNSW_ENGINE_DEFAULT, MAX_HNSW_EF_CONSTRUCTION, MAX_HNSW_M,
    get_cache_config_struct, query_entities_struct,
)
from pygridgain.datatypes.cache_properties import prop_map
from pygridgain.datatypes.prop_codes import PROP_QUERY_ENTITIES

# Feature flags only exist from 1.7.0; ProtocolContext drops them below that.
VERSION = (1, 7, 1)

SIMILARITY = BitmaskFeature.QUERY_INDEX_VECTOR_SIMILARITY
HNSW = BitmaskFeature.QUERY_INDEX_VECTOR_HNSW_PARAMS

BASE_INDEX_FIELDS = ['index_name', 'index_type', 'inline_size', 'fields']


def context(*features):
    """A protocol context advertising exactly the given features."""
    mask = BitmaskFeature(0)
    for feature in features:
        mask |= feature
    return ProtocolContext(VERSION, mask)


def index_field_names(has_similarity, has_hnsw_params):
    entities = query_entities_struct(has_similarity, has_hnsw_params)
    query_indexes = dict(entities.following)['query_indexes']
    return [name for name, _ in query_indexes.following]


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
    [
        ((), False),
        ((SIMILARITY,), False),
        ((HNSW,), True),
        ((SIMILARITY, HNSW), True),
    ],
)
def test_protocol_context_reports_the_feature(features, supported):
    assert bool(context(*features).is_query_index_vector_hnsw_params_supported()) is supported


def test_feature_is_not_reported_below_1_7_0():
    # Below 1.7.0 the feature mask is dropped wholesale, so nothing may be claimed.
    stale = ProtocolContext((1, 6, 0), BitmaskFeature(0) | HNSW)
    assert not stale.is_query_index_vector_hnsw_params_supported()


@pytest.mark.parametrize(
    'has_similarity, has_hnsw_params, expected',
    [
        (False, False, BASE_INDEX_FIELDS),
        (True, False, BASE_INDEX_FIELDS + ['similarity_function']),
        (False, True, BASE_INDEX_FIELDS + ['hnsw_m', 'hnsw_ef_construction']),
        (True, True, BASE_INDEX_FIELDS + ['similarity_function', 'hnsw_m', 'hnsw_ef_construction']),
    ],
)
def test_index_layout_tracks_the_negotiated_features(has_similarity, has_hnsw_params, expected):
    # Order matters as much as presence: the server writes similarity first, then the
    # HNSW pair, both at the end of the index.
    assert index_field_names(has_similarity, has_hnsw_params) == expected


def test_hnsw_params_default_to_engine_default():
    entities = query_entities_struct(True, True)
    defaults = dict(entities.following)['query_indexes'].defaults
    assert defaults['hnsw_m'] == HNSW_ENGINE_DEFAULT
    assert defaults['hnsw_ef_construction'] == HNSW_ENGINE_DEFAULT


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
    [
        ((), False, False),
        ((SIMILARITY,), True, False),
        ((SIMILARITY, HNSW), True, True),
    ],
)
def test_cache_config_struct_selects_the_negotiated_layout(features, has_similarity, has_hnsw_params):
    struct = get_cache_config_struct(context(*features))
    assert dict(struct.fields)['query_entities'] is query_entities_struct(has_similarity, has_hnsw_params)


def test_property_layout_is_unchanged_without_the_new_feature():
    # Guards the compatibility promise: talking to a cluster that predates bit 38 must
    # put exactly the same bytes on the wire as before this change.
    ctx = context(SIMILARITY)
    assert index_field_names(True, False) == BASE_INDEX_FIELDS + ['similarity_function']
    assert prop_map(PROP_QUERY_ENTITIES, ctx).prop_data_class is query_entities_struct(True, False)


def test_prop_map_without_context_keeps_the_legacy_default():
    from pygridgain.datatypes.cache_properties import PropQueryEntities

    assert prop_map(PROP_QUERY_ENTITIES) is PropQueryEntities
