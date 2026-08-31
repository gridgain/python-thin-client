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
