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


# ---------------------------------------------------------------------------
# Bulk SERIALIZATION fast path (_bulk_from_python) — the encode counterpart of
# the decode coverage above. The element-wise path is the reference: every fast
# path must be byte-for-byte identical to it, because these bytes go on the wire.
# ---------------------------------------------------------------------------

BULK_ENCODE_TYPES = [
    ShortArrayObject, IntArrayObject, LongArrayObject, FloatArrayObject, DoubleArrayObject,
    ShortArray, IntArray, LongArray, FloatArray, DoubleArray,
]


def _serialize_elementwise(datatype, value, monkeypatch):
    """Serialize with both fast paths disabled, i.e. one call per element."""
    monkeypatch.setattr(datatype, '_struct_format', None)
    monkeypatch.setattr(datatype, '_wire_dtype', None)
    try:
        return _serialize(datatype, value)
    finally:
        monkeypatch.undo()


# Deliberately includes the values most likely to expose an encoding difference:
# type extremes, signed zero, subnormals, and the non-finite floats.
EDGE_CASES = [
    (ShortArrayObject, [0, 1, -1, 32767, -32768]),
    (IntArrayObject, [0, 1, -1, 2 ** 31 - 1, -2 ** 31]),
    (LongArrayObject, [0, 1, -1, 2 ** 63 - 1, -2 ** 63]),
    (FloatArrayObject, [0.0, -0.0, 1.5, -1.5, 3.4e38, -3.4e38, 1e-45,
                        float('inf'), float('-inf'), float('nan')]),
    (DoubleArrayObject, [0.0, -0.0, 1.5, -1.5, 1.7e308, 5e-324,
                         float('inf'), float('-inf'), float('nan')]),
]


@pytest.mark.parametrize('datatype,value', EDGE_CASES)
def test_bulk_encode_is_byte_identical(datatype, value, monkeypatch):
    assert _serialize(datatype, value) == _serialize_elementwise(datatype, value, monkeypatch)


@pytest.mark.parametrize('datatype,value', EDGE_CASES)
def test_bulk_encode_accepts_tuples(datatype, value, monkeypatch):
    assert _serialize(datatype, tuple(value)) == _serialize_elementwise(datatype, value, monkeypatch)


@pytest.mark.parametrize('datatype', BULK_ENCODE_TYPES)
def test_bulk_encode_empty(datatype, monkeypatch):
    assert _serialize(datatype, []) == _serialize_elementwise(datatype, [], monkeypatch)


def test_bulk_encode_large_vector_is_byte_identical(monkeypatch):
    """The motivating case: a 1536-d embedding sent as a vector-search clause."""
    value = [i * 0.5 for i in range(1536)]
    assert _serialize(FloatArrayObject, value) == _serialize_elementwise(FloatArrayObject, value, monkeypatch)


def test_char_and_bool_keep_the_elementwise_path():
    """Char encodes through a text codec and Bool has its own byte semantics."""
    for datatype in (CharArrayObject, BoolArrayObject):
        assert datatype._struct_format is None
        assert datatype._wire_dtype is None


def test_bad_element_still_raises():
    """A non-numeric element must fail, not be silently coerced by the bulk path."""
    with pytest.raises(Exception):
        _serialize(IntArrayObject, [1, 'not a number', 3])


def test_zero_copy_path_matches_and_only_takes_matching_dtype(monkeypatch):
    """A buffer already in wire layout is written straight through; anything else is not."""
    numpy = pytest.importorskip('numpy')
    value = [0.0, 1.5, -2.25, 1024.0, float('nan')]

    reference = _serialize_elementwise(FloatArrayObject, value, monkeypatch)

    little = numpy.asarray(value, dtype='<f4')
    assert little.dtype.str == FloatArrayObject._wire_dtype
    assert _serialize(FloatArrayObject, little) == reference

    # A byte-swapped buffer must NOT take the zero-copy path, or the wire bytes would be reversed.
    big = numpy.asarray(value, dtype='>f4')
    assert big.dtype.str != FloatArrayObject._wire_dtype
    assert _serialize(FloatArrayObject, big) == reference

    # float64 input to a float32 field must still narrow correctly rather than copy raw bytes.
    wide = numpy.asarray(value, dtype='<f8')
    assert _serialize(FloatArrayObject, wide) == reference
