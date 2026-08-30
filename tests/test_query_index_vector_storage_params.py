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
Wire layout of the vector storage and segment parameters (GG-50943).

Three feature bits, and they are not interchangeable:

    39  QUERY_INDEX_VECTOR_QUANTIZATION    adds one int, the storage ordinal
    41  QUERY_INDEX_VECTOR_SEGMENT_PARAMS  adds two ints, the segment target and thread count
    42  QUERY_INDEX_VECTOR_INT8_STORAGE    adds NO field: it gates a VALUE on the field bit 39 added

Bit 40 is not a vector bit. The server gave it to CONTINUOUS_QUERY_COMPACT_VALUE, so the two
newest vector bits are 41 and 42. Do not close the gap.

Bit 42 exists because INT8 was added to an enum that had already shipped behind bit 39. A peer
with bit 39 reads the ordinal and resolves the value it does not know to the engine default, so
an INT8 request against such a peer silently produces a full-precision index. The server refuses
that; so does this client.

The tests pin the bytes rather than the declared field list, because a layout that is merely
self-consistent still desynchronises the stream.
"""

import pytest

from pygridgain.connection.bitmask_feature import BitmaskFeature
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.datatypes.cache_config import (
    MAX_VECTOR_INDEX_SEGMENTS, MAX_VECTOR_QUERY_THREADS, VECTOR_SEGMENTS_ENGINE_DEFAULT,
    IndexType, VectorQuantization, query_entities_struct,
)
from pygridgain.exceptions import NotSupportedByClusterError
from pygridgain.stream.binary_stream import AioBinaryStream, BinaryStream

# Feature flags only exist from 1.7.0; ProtocolContext drops them below that.
VERSION = (1, 7, 1)

SIMILARITY = BitmaskFeature.QUERY_INDEX_VECTOR_SIMILARITY
HNSW = BitmaskFeature.QUERY_INDEX_VECTOR_HNSW_PARAMS
QUANTIZATION = BitmaskFeature.QUERY_INDEX_VECTOR_QUANTIZATION
SEGMENTS = BitmaskFeature.QUERY_INDEX_VECTOR_SEGMENT_PARAMS
INT8 = BitmaskFeature.QUERY_INDEX_VECTOR_INT8_STORAGE

NON_VECTOR_TYPES = [IndexType.SORTED, IndexType.FULLTEXT, IndexType.GEOSPATIAL]

TUNED_SEGMENTS = 4
TUNED_THREADS = 2


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


def struct_for(quantization=False, segments=False, int8=False):
    """The layout for a peer with similarity and HNSW plus the given vector-storage features."""
    return query_entities_struct(True, True, quantization, segments, int8)


def serialize(indexes, **flags):
    stream = BinaryStream(None)
    struct_for(**flags).from_python(stream, [entity(indexes)])
    return stream.getvalue()


def round_trip(indexes, **flags):
    struct = struct_for(**flags)
    stream = BinaryStream(None, serialize(indexes, **flags))
    c_type = struct.parse(stream)
    stream.seek(0)
    return struct.to_python(stream.read_ctype(c_type))[0]['query_indexes']


@pytest.mark.asyncio
async def test_async_path_matches_the_sync_path():
    """
    parse_async / from_python_async / to_python_async are hand-duplicated from the sync versions and
    are what cache_get_configuration_async runs. The new fields are written by the same _prepare and
    following, so this is parity cover rather than a second implementation test -- but the previous
    per-index ticket set the precedent, and a drift here would otherwise reach users unseen.
    """
    indexes = [vector_index(quantization=VectorQuantization.INT8, max_segments=4, query_threads=2)]
    flags = dict(quantization=True, segments=True, int8=True)

    struct = struct_for(**flags)

    stream = AioBinaryStream(None)
    await struct.from_python_async(stream, [entity(indexes)])
    written = stream.getvalue()

    assert written == serialize(indexes, **flags)

    stream = AioBinaryStream(None, written)
    c_type = await struct.parse_async(stream)
    stream.seek(0)
    parsed = (await struct.to_python_async(stream.read_ctype(c_type)))[0]['query_indexes']

    assert parsed == round_trip(indexes, **flags)


def vector_index(**overrides):
    idx = {'index_name': 'by_embedding', 'index_type': IndexType.VECTOR, 'inline_size': -1,
           'fields': [{'name': 'embedding'}], 'similarity_function': 1,
           'hnsw_m': 16, 'hnsw_ef_construction': 100}
    idx.update(overrides)
    return idx


# --- the bits themselves ---------------------------------------------------------------

def test_feature_bits_match_the_server():
    assert QUANTIZATION == 1 << 39
    assert SEGMENTS == 1 << 41
    assert INT8 == 1 << 42


def test_features_are_advertised_as_supported():
    supported = BitmaskFeature.all_supported()
    assert QUANTIZATION in supported
    assert SEGMENTS in supported
    assert INT8 in supported


@pytest.mark.parametrize('feature,method', [
    (QUANTIZATION, 'is_query_index_vector_quantization_supported'),
    (SEGMENTS, 'is_query_index_vector_segment_params_supported'),
    (INT8, 'is_query_index_vector_int8_storage_supported'),
])
def test_protocol_context_reports_each_feature_independently(feature, method):
    assert getattr(context(feature), method)()
    # and reports nothing when a DIFFERENT vector feature was negotiated: the three are not
    # interchangeable, and treating one as implying another is the bug bit 42 exists to prevent
    others = {QUANTIZATION, SEGMENTS, INT8} - {feature}
    assert not getattr(context(*others), method)()


def test_segment_bounds_match_the_server():
    assert MAX_VECTOR_INDEX_SEGMENTS == 1024
    assert MAX_VECTOR_QUERY_THREADS == 64


def test_int8_ordinal_matches_the_server_enum():
    # The wire carries the ordinal, so a drift here is a silently different storage mode.
    assert (VectorQuantization.ENGINE_DEFAULT, VectorQuantization.NONE,
            VectorQuantization.BINARY, VectorQuantization.INT8) == (0, 1, 2, 3)


# --- the client must know EVERY vector bit the server has ------------------------------

#: Every vector-search feature bit the server declares, from ClientBitmaskFeature. Kept here as a
#: literal on purpose: this client cannot read the server's enum, so the list is the contract, and
#: a server that grows a seventh bit has to be reflected here deliberately rather than by accident.
SERVER_VECTOR_BITS = {
    33: 'QUERY_INDEX_VECTOR_SIMILARITY',
    35: 'QUERY_VECTOR_EXTENDED',
    38: 'QUERY_INDEX_VECTOR_HNSW_PARAMS',
    39: 'QUERY_INDEX_VECTOR_QUANTIZATION',
    41: 'QUERY_INDEX_VECTOR_SEGMENT_PARAMS',
    42: 'QUERY_INDEX_VECTOR_INT8_STORAGE',
}


def _declared_vector_bits():
    return {f.value.bit_length() - 1: f.name for f in BitmaskFeature if 'VECTOR' in f.name}


def test_client_declares_every_vector_bit_the_server_has():
    assert _declared_vector_bits() == SERVER_VECTOR_BITS


@pytest.mark.parametrize('name', sorted(SERVER_VECTOR_BITS.values()))
def test_every_vector_bit_has_a_protocol_context_accessor(name):
    """
    A declared bit is an advertised bit: all_supported() sends it, so the server may then send a
    payload for it. Declaring one with no way to ask whether it was negotiated is a promise the
    client cannot keep, and it fails on the wire rather than here.
    """
    assert hasattr(ProtocolContext, f'is_{name.lower()}_supported')


def test_every_vector_bit_is_advertised():
    supported = BitmaskFeature.all_supported()

    for bit in SERVER_VECTOR_BITS:
        assert BitmaskFeature(1 << bit) in supported


# --- what reaches the wire -------------------------------------------------------------

@pytest.mark.parametrize('flags,extra_bytes', [
    ({}, 0),
    ({'quantization': True}, 4),
    ({'segments': True}, 8),
    ({'quantization': True, 'segments': True}, 12),
])
def test_vector_index_gains_exactly_the_negotiated_fields(flags, extra_bytes):
    base = len(serialize([vector_index()]))
    with_flags = len(serialize([vector_index()], **flags))
    assert with_flags - base == extra_bytes


def test_int8_bit_adds_no_bytes():
    # Bit 42 gates a value, not a field. If it ever changes the layout, this fails loudly.
    without = serialize([vector_index()], quantization=True)
    with_int8 = serialize([vector_index()], quantization=True, int8=True)
    assert without == with_int8


@pytest.mark.parametrize('index_type', NON_VECTOR_TYPES)
def test_non_vector_index_never_carries_the_new_fields(index_type):
    idx = {'index_name': 'by_name', 'index_type': index_type, 'inline_size': -1,
           'fields': [{'name': 'name'}]}
    assert serialize([idx]) == serialize([idx], quantization=True, segments=True, int8=True)


def test_values_round_trip():
    got = round_trip(
        [vector_index(quantization=VectorQuantization.BINARY,
                      max_segments=TUNED_SEGMENTS, query_threads=TUNED_THREADS)],
        quantization=True, segments=True, int8=True)[0]

    assert got['quantization'] == VectorQuantization.BINARY
    assert got['max_segments'] == TUNED_SEGMENTS
    assert got['query_threads'] == TUNED_THREADS


def test_unset_storage_round_trips_as_the_engine_default():
    got = round_trip([vector_index()], quantization=True, segments=True)[0]

    assert got['quantization'] == VectorQuantization.ENGINE_DEFAULT
    assert got['max_segments'] == VECTOR_SEGMENTS_ENGINE_DEFAULT
    assert got['query_threads'] == VECTOR_SEGMENTS_ENGINE_DEFAULT


# --- refusals, and the one thing that must NOT be refused ------------------------------

def test_quantization_refused_when_the_cluster_lacks_the_field():
    with pytest.raises(NotSupportedByClusterError, match='per-index vector storage'):
        serialize([vector_index(quantization=VectorQuantization.BINARY)])


def test_int8_refused_when_the_cluster_has_the_field_but_not_the_value():
    # The whole reason bit 42 exists. Sent anyway, the peer resolves ordinal 3 to the engine
    # default and builds a full-precision index without reporting anything.
    with pytest.raises(NotSupportedByClusterError, match='not the INT8 mode'):
        serialize([vector_index(quantization=VectorQuantization.INT8)], quantization=True)


def test_binary_still_reaches_a_cluster_without_the_int8_bit():
    # The negative control for the test above. BINARY shipped before INT8 existed, so gating it
    # on bit 42 would break every existing caller while passing the refusal test.
    got = round_trip([vector_index(quantization=VectorQuantization.BINARY)], quantization=True)[0]
    assert got['quantization'] == VectorQuantization.BINARY


def test_int8_accepted_once_the_bit_is_negotiated():
    got = round_trip([vector_index(quantization=VectorQuantization.INT8)],
                     quantization=True, int8=True)[0]
    assert got['quantization'] == VectorQuantization.INT8


@pytest.mark.parametrize('field,value', [('max_segments', 4), ('query_threads', 2)])
def test_segment_params_refused_when_the_cluster_lacks_them(field, value):
    with pytest.raises(NotSupportedByClusterError, match='per-index vector segment parameters'):
        serialize([vector_index(**{field: value})])


@pytest.mark.parametrize('field,value', [
    ('quantization', VectorQuantization.BINARY),
    ('max_segments', 4),
    ('query_threads', 2),
])
def test_new_params_refused_on_a_non_vector_index(field, value):
    idx = {'index_name': 'by_name', 'index_type': IndexType.SORTED, 'inline_size': -1,
           'fields': [{'name': 'name'}], field: value}
    with pytest.raises(ValueError, match='VECTOR indexes only'):
        serialize([idx], quantization=True, segments=True, int8=True)
