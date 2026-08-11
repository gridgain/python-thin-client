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
Server-free coverage for ctypes-class memoization in the response path.

Building a ctypes Structure calls ``type()``, which allocates a class and computes a struct layout.
The parser built one per row, all identical — for a k-NN query returning 10 ids that was 10 class
creations per query. These classes are only ever read (``sizeof``, ``from_buffer_copy``,
``read_ctype``), never mutated, so one shared class per shape is safe.

What must hold, and is asserted here: identical shapes share a class, different shapes never do,
layouts are unchanged, and an unusable field spec still raises rather than being cached.
"""
import ctypes

import pytest

from pygridgain.datatypes.internal import Struct, _cached_struct_c_type
from pygridgain.datatypes.standard import String

FIELDS = [('length', ctypes.c_int), ('type_code', ctypes.c_byte), ('data', ctypes.c_byte * 16)]
OTHER = [('length', ctypes.c_int), ('data', ctypes.c_byte * 32)]


def test_same_shape_returns_the_same_class():
    # A fresh list with equal contents must still hit: the key is the shape, not the list identity.
    assert Struct.build_c_type(FIELDS) is Struct.build_c_type(list(FIELDS))


def test_different_shapes_do_not_collide():
    assert Struct.build_c_type(FIELDS) is not Struct.build_c_type(OTHER)


def test_layout_is_unchanged():
    c = Struct.build_c_type(FIELDS)
    assert ctypes.sizeof(c) == ctypes.sizeof(ctypes.c_int) + ctypes.sizeof(ctypes.c_byte) + 16
    assert [n for n, _ in c._fields_] == ['length', 'type_code', 'data']


def test_instances_are_independent_even_though_the_class_is_shared():
    """Sharing the class must not share state — the whole point is that only the type is reused."""
    c = Struct.build_c_type(FIELDS)
    a, b = c(), c()
    a.length = 7
    b.length = 9
    assert (a.length, b.length) == (7, 9)


def test_cache_actually_hits():
    Struct.build_c_type(FIELDS)
    before = _cached_struct_c_type.cache_info().hits
    for _ in range(50):
        Struct.build_c_type(list(FIELDS))
    assert _cached_struct_c_type.cache_info().hits >= before + 50


def test_unusable_field_spec_still_raises():
    """An unhashable spec must not be silently swallowed by the cache lookup."""
    with pytest.raises(TypeError):
        Struct.build_c_type([('x', ctypes.c_int), ('bad', [1, 2, 3])])


def test_string_c_type_is_memoized_per_length():
    assert String.build_c_type(12) is String.build_c_type(12)
    assert String.build_c_type(12) is not String.build_c_type(24)
    assert ctypes.sizeof(String.build_c_type(24)) - ctypes.sizeof(String.build_c_type(12)) == 12


def test_string_subclasses_do_not_share_a_class():
    """The generated class takes its name from cls, so the cache key includes the class."""
    class Derived(String):
        pass

    assert String.build_c_type(8) is not Derived.build_c_type(8)
    assert Derived.build_c_type(8).__name__ == 'Derived'
