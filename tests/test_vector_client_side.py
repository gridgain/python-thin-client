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
Server-free coverage for the client-side vector query behaviour: the k guard, the page_size
default, and the shared-class cache behind the response fast path.
"""
import asyncio
import ctypes
from unittest import mock

import pytest

from pygridgain import AioClient, Client
from pygridgain.datatypes.internal import cached_c_type


def test_same_shape_and_name_share_a_class():
    fields = (('length', ctypes.c_int), ('payload', ctypes.c_byte * 24), ('offset', ctypes.c_int))
    a = cached_c_type('WrappedDataObject', (ctypes.LittleEndianStructure,), fields)
    b = cached_c_type('WrappedDataObject', (ctypes.LittleEndianStructure,), list(fields))
    assert a is b
    assert ctypes.sizeof(a) == 4 + 24 + 4
    assert [n for n, _ in a._fields_] == ['length', 'payload', 'offset']


def test_names_and_shapes_do_not_collide():
    fields = (('length', ctypes.c_int),)
    assert cached_c_type('A', (ctypes.LittleEndianStructure,), fields) \
        is not cached_c_type('B', (ctypes.LittleEndianStructure,), fields)
    assert cached_c_type('A', (ctypes.LittleEndianStructure,), fields) \
        is not cached_c_type('A', (ctypes.LittleEndianStructure,), (('length', ctypes.c_longlong),))


def test_unusable_spec_still_raises():
    """An unhashable spec skips the cache and still fails loudly in the direct build."""
    with pytest.raises(TypeError):
        cached_c_type('C', (ctypes.LittleEndianStructure,), [('x', ctypes.c_int), ('bad', [1, 2, 3])])


def test_vector_rejects_non_positive_k():
    cache = Client().get_cache('vec')
    for bad_k in (0, -1):
        with pytest.raises(ValueError, match='k must be positive'):
            cache.vector('T', 'vec', [0.0], k=bad_k, threshold=0.0)


def test_vector_page_size_defaults_to_k():
    cache = Client().get_cache('vec')
    with mock.patch('pygridgain.cache.VectorCursor') as cursor:
        cache.vector('T', 'vec', [0.0], k=7, threshold=0.0)
    page_size = cursor.call_args.args[2]
    assert page_size == 7


def test_vector_explicit_page_size_is_kept():
    cache = Client().get_cache('vec')
    with mock.patch('pygridgain.cache.VectorCursor') as cursor:
        cache.vector('T', 'vec', [0.0], k=7, threshold=0.0, page_size=2)
    assert cursor.call_args.args[2] == 2


def test_aio_vector_rejects_non_positive_k():
    async def run():
        cache = await AioClient().get_cache('vec')
        with pytest.raises(ValueError, match='k must be positive'):
            cache.vector('T', 'vec', [0.0], k=0, threshold=0.0)
    asyncio.new_event_loop().run_until_complete(run())


def test_aio_vector_page_size_defaults_to_k():
    async def run():
        cache = await AioClient().get_cache('vec')
        with mock.patch('pygridgain.aio_cache.AioVectorCursor') as cursor:
            cache.vector('T', 'vec', [0.0], k=5, threshold=0.0)
        assert cursor.call_args.args[2] == 5
    asyncio.new_event_loop().run_until_complete(run())


# ---- the cache must HIT at the real parse sites, not only in isolation ----------------------------

def _parse_twice(datatype, payload):
    from pygridgain.stream import BinaryStream
    classes = []
    for _ in range(2):
        with BinaryStream(None, bytearray(payload)) as stream:
            classes.append(datatype.parse(stream))
    return classes


def test_wrapped_payload_class_is_shared_across_parses():
    from pygridgain.datatypes import WrappedDataObject
    import struct
    payload = b'\x1b' + struct.pack('<i', 24) + bytes(24) + struct.pack('<i', 0)
    first, second = _parse_twice(WrappedDataObject, payload)
    assert first is second
    assert ctypes.sizeof(first) == len(payload)


def test_float_array_class_is_shared_across_parses():
    from pygridgain.datatypes import FloatArrayObject
    import struct
    payload = b'\x10' + struct.pack('<i', 4) + struct.pack('<4f', 1.0, 2.0, 3.0, 4.0)
    first, second = _parse_twice(FloatArrayObject, payload)
    assert first is second
    assert ctypes.sizeof(first) == len(payload)


def test_map_class_is_shared_across_parses():
    """The container key holds the element classes, so it repeats only if the leaves do."""
    from pygridgain.datatypes import Map
    import struct
    entry = b'\x04' + struct.pack('<q', 7) + b'\x09' + struct.pack('<i', 2) + b'hi'
    payload = struct.pack('<i', 2) + entry + entry
    first, second = _parse_twice(Map, payload)
    assert first is second
    assert ctypes.sizeof(first) == len(payload)


def test_different_payload_lengths_do_not_share():
    from pygridgain.datatypes import WrappedDataObject
    import struct
    short = b'\x1b' + struct.pack('<i', 8) + bytes(8) + struct.pack('<i', 0)
    longer = b'\x1b' + struct.pack('<i', 16) + bytes(16) + struct.pack('<i', 0)
    assert _parse_twice(WrappedDataObject, short)[0] is not _parse_twice(WrappedDataObject, longer)[0]


# ---- review findings (af Round 1): one-shot iterables, the admission bound, remaining leaf classes ----

def test_one_shot_iterable_builds_the_full_class():
    """tuple(fields) must run once: a generator must not be exhausted before the fallback build."""
    fields = iter((('a', ctypes.c_int), ('b', ctypes.c_byte)))
    c = cached_c_type('OneShot', (ctypes.LittleEndianStructure,), fields)
    assert [n for n, _ in c._fields_] == ['a', 'b']
    assert ctypes.sizeof(c) == 5


def test_one_shot_iterable_with_a_bad_spec_still_raises():
    """An exhausted iterator must never turn an invalid spec into a silent zero-field class."""
    fields = iter((('ok', ctypes.c_int), ('bad', [1, 2, 3])))
    with pytest.raises(TypeError):
        cached_c_type('OneShotBad', (ctypes.LittleEndianStructure,), fields)


def test_shapes_above_the_field_budget_are_not_cached():
    from pygridgain.datatypes.internal import CACHED_C_TYPE_MAX_FIELDS, _cached_c_type
    wide = tuple((f'f{i}', ctypes.c_byte) for i in range(CACHED_C_TYPE_MAX_FIELDS + 1))
    before = _cached_c_type.cache_info()
    a = cached_c_type('Wide', (ctypes.LittleEndianStructure,), wide)
    b = cached_c_type('Wide', (ctypes.LittleEndianStructure,), wide)
    after = _cached_c_type.cache_info()
    assert a is not b                      # built per call, like before the cache existed
    assert ctypes.sizeof(a) == CACHED_C_TYPE_MAX_FIELDS + 1
    assert after.currsize == before.currsize and after.misses == before.misses


def test_decimal_leaf_class_is_shared_across_parses():
    """A parent that holds a Decimal can only hit the cache if the Decimal leaf itself is shared."""
    from pygridgain.datatypes import DecimalObject
    import struct
    payload = b'\x1e' + struct.pack('<i', 2) + struct.pack('<i', 3) + b'\x01\x02\x03'
    first, second = _parse_twice(DecimalObject, payload)
    assert first is second


def test_object_array_class_is_shared_across_parses():
    from pygridgain.datatypes import ObjectArrayObject
    import struct
    # type code, type id, length, then two Long elements
    element = b'\x04' + struct.pack('<q', 5)
    payload = b'\x17' + struct.pack('<i', -1) + struct.pack('<i', 2) + element + element
    first, second = _parse_twice(ObjectArrayObject, payload)
    assert first is second


def test_parsing_identical_frames_creates_no_new_classes():
    """The demand behind the cache: after warm-up, parsing the same shape creates zero classes."""
    import gc
    import struct
    from pygridgain.datatypes import Map
    entry = b'\x04' + struct.pack('<q', 7) + b'\x1b' + struct.pack('<i', 32) + bytes(32) + struct.pack('<i', 0)
    payload = struct.pack('<i', 3) + entry * 3
    _parse_twice(Map, payload)                      # warm-up
    gc.collect()
    classes_before = sum(1 for o in gc.get_objects() if isinstance(o, type))
    for _ in range(50):
        _parse_twice(Map, payload)
    gc.collect()
    classes_after = sum(1 for o in gc.get_objects() if isinstance(o, type))
    assert classes_after == classes_before
