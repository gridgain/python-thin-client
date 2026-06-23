#
# Copyright 2021 GridGain Systems, Inc. and Contributors.
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
Server-free coverage for the bulk primitive-array deserialization fast path
(:func:`pygridgain.datatypes.primitive_arrays._bulk_to_python`, GG-49287).

These exercise the real serialize -> parse -> read_ctype -> to_python codec
without a running node, so the decode path is checked in CI's unit run rather
than only via the live put/get round-trips in ``tests/common/test_datatypes.py``.
"""
import sys

import pytest

from pygridgain.datatypes.primitive_arrays import (
    _bulk_to_python,
    ByteArrayObject, ShortArrayObject, IntArrayObject, LongArrayObject,
    FloatArrayObject, DoubleArrayObject, CharArrayObject, BoolArrayObject,
    FloatArray, IntArray, ShortArray, LongArray, DoubleArray,
)
from pygridgain.stream.binary_stream import BinaryStream


def _serialize(datatype, value):
    stream = BinaryStream(None)
    datatype.from_python(stream, value)
    return stream.getvalue()


def _to_ctypes_object(datatype, value):
    stream = BinaryStream(None, _serialize(datatype, value))
    c_type = datatype.parse(stream)
    return stream.read_ctype(c_type, position=0)


def _roundtrip(datatype, value):
    return datatype.to_python(_to_ctypes_object(datatype, value))


# Values chosen to be exactly representable (incl. float32 for FloatArray*) so
# equality holds after a real serialize/deserialize round-trip.
NUMERIC_CASES = [
    (ShortArrayObject, [-32768, -1, 0, 1, 32767, 12345]),
    (IntArrayObject, [-2 ** 31, -1, 0, 1, 2 ** 31 - 1, 987654321]),
    (LongArrayObject, [-2 ** 63, -1, 0, 1, 2 ** 63 - 1, 10 ** 18]),
    (FloatArrayObject, [0.0, 1.0, -1.0, 1.5, -2.25, 0.5, 1024.0, -4096.0]),
    (DoubleArrayObject, [0.0, 1.0, -1.0, 1.5, -2.25, 3.141592653589793, 1e308, -1e-308]),
    # Payload-only variants (no type code) — exercise PrimitiveArray.to_python.
    (ShortArray, [-1, 0, 7, 32767]),
    (IntArray, [-1, 0, 7, 2 ** 31 - 1]),
    (LongArray, [-1, 0, 7, 2 ** 63 - 1]),
    (FloatArray, [0.0, 1.5, -2.25, 1024.0]),
    (DoubleArray, [0.0, 1.5, -2.25, 1e300]),
]


@pytest.mark.parametrize('datatype,value', NUMERIC_CASES)
def test_numeric_array_roundtrip(datatype, value):
    assert _roundtrip(datatype, value) == value


@pytest.mark.parametrize('datatype', [
    ShortArrayObject, IntArrayObject, LongArrayObject, FloatArrayObject,
    DoubleArrayObject, CharArrayObject, BoolArrayObject,
    ShortArray, IntArray, LongArray, FloatArray, DoubleArray,
])
def test_empty_array_roundtrip(datatype):
    assert _roundtrip(datatype, []) == []


def test_byte_array_roundtrip():
    # ByteArrayObject decodes to ``bytes`` (its own override, not the bulk helper).
    assert _roundtrip(ByteArrayObject, [0, 1, 127, 255]) == bytes([0, 1, 127, 255])
    assert _roundtrip(ByteArrayObject, []) == b''


def test_bool_array_roundtrip():
    value = [True, False, True, True, False]
    assert _roundtrip(BoolArrayObject, value) == value


def test_char_array_roundtrip():
    # BMP characters (same alphabet as the live suite's CharArrayObject case).
    value = ['A', 'я', 'カ', '好', '€']
    assert _roundtrip(CharArrayObject, value) == value


def test_large_float_vector_is_identical():
    # The motivating case: a 1536-d float vector returned per query-result row.
    # Integers < 2**24 are exact in float32, so the decoded list must match.
    value = [float(i) for i in range(1536)]
    assert _roundtrip(FloatArrayObject, value) == value


def test_bulk_decode_matches_elementwise_and_big_endian_fallback(monkeypatch):
    """The fast path and the big-endian element-wise fallback agree element-for-element."""
    value = [0.0, 1.0, -1.0, 1.5, -2.25, 0.5, 1024.0, -4096.0]
    ctypes_object = _to_ctypes_object(FloatArrayObject, value)
    reference = [ctypes_object.data[i] for i in range(ctypes_object.length)]

    assert sys.byteorder == 'little'
    fast = _bulk_to_python(ctypes_object)          # little-endian: memoryview bulk decode
    assert fast == reference == value

    monkeypatch.setattr(sys, 'byteorder', 'big')   # force the element-wise fallback branch
    fallback = _bulk_to_python(ctypes_object)
    assert fallback == reference == value
