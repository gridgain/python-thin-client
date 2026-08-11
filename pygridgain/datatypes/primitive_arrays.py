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
import ctypes
import struct
import sys
from io import SEEK_CUR

from pygridgain.constants import *
from .base import GridGainDataType
from .null_object import Nullable
from .primitive import *
from .type_codes import *
from .type_ids import *
from .type_names import *


__all__ = [
    'ByteArray', 'ByteArrayObject', 'ShortArray', 'ShortArrayObject',
    'IntArray', 'IntArrayObject', 'LongArray', 'LongArrayObject',
    'FloatArray', 'FloatArrayObject', 'DoubleArray', 'DoubleArrayObject',
    'CharArray', 'CharArrayObject', 'BoolArray', 'BoolArrayObject',
]


def _bulk_to_python(ctypes_object):
    """
    Decode a ctypes primitive array into a Python list in a single C-level pass.

    Replaces the element-wise ``[data[i] for i in range(length)]`` comprehension,
    which is the dominant client cost for large primitive arrays (e.g. the 1536-d
    float vector returned per vector-query result row): ``memoryview.tolist()``
    unpacks the whole buffer in one C loop instead of one ctypes ``__getitem__``
    (offset + bounds-check + box) per element.

    ``memoryview.cast()`` only accepts a native byte-order format, while the array
    is a ``LittleEndianStructure`` that reports an explicit prefix (e.g. ``'<f'``).
    On a little-endian host the reinterpret is a no-op, so we strip the prefix and
    bulk-decode; on a big-endian host that would misread the bytes, so we keep the
    correct (and there, equally cheap relative to the byte-swap) element-wise path.
    """
    if sys.byteorder == 'little':
        mv = memoryview(ctypes_object.data)
        return mv.cast('B').cast(mv.format.lstrip('<>=!@')).tolist()
    return [ctypes_object.data[i] for i in range(ctypes_object.length)]


def _bulk_from_python(cls, stream, value):
    """
    Encode a primitive array in one pass, or return False to use the element-wise path.

    Encoding element by element costs one Python-level call per element. That is invisible for a
    handful of values and dominant for a large one: a 1536-dimension embedding sent as a
    vector-search clause spent ~1536 calls per query, which measured as the single largest component
    of client-side CPU.

    Both paths below are byte-for-byte identical to the element-wise one, on little- and big-endian
    hosts alike: the ``struct`` formats are explicitly little-endian, matching
    ``Primitive.from_python``, and the zero-copy path only triggers when the value's own dtype
    already states little-endian.
    """
    # 1. zero copy — the buffer is already in wire layout (e.g. a numpy '<f4' array)
    if cls._wire_dtype is not None:
        dtype = getattr(value, 'dtype', None)
        if dtype is not None and getattr(dtype, 'str', None) == cls._wire_dtype:
            stream.write(value.tobytes())
            return True

    # 2. one pack call for the whole array
    if cls._struct_format is not None:
        try:
            stream.write(struct.pack('<%d%s' % (len(value), cls._struct_format), *value))
            return True
        except (struct.error, TypeError, OverflowError):
            # Not a plain sequence of in-range scalars. Fall back so the element-wise path raises
            # the specific, familiar error rather than a bulk one.
            pass

    return False


class PrimitiveArray(GridGainDataType):
    """
    Base class for array of primitives. Payload-only.
    """
    _type_name = None
    _type_id = None
    primitive_type = None

    #: ``struct`` format character used to encode the whole array in one call. ``None`` keeps the
    #: element-by-element path (types whose element encoding is not a plain little-endian scalar).
    _struct_format = None

    #: Buffer dtype string that already matches the wire layout exactly. ``None`` disables that path.
    _wire_dtype = None

    @classmethod
    def build_c_type(cls, stream):
        length = int.from_bytes(
            stream.slice(stream.tell(), ctypes.sizeof(ctypes.c_int)),
            byteorder=PROTOCOL_BYTE_ORDER
        )

        return type(
            cls.__name__,
            (ctypes.LittleEndianStructure, ),
            {
                '_pack_': 1,
                '_fields_': [
                    ('length', ctypes.c_int),
                    ('data', cls.primitive_type.c_type * length),
                ],
            }
        )

    @classmethod
    def parse(cls, stream):
        c_type = cls.build_c_type(stream)
        stream.seek(ctypes.sizeof(c_type), SEEK_CUR)
        return c_type

    @classmethod
    def to_python(cls, ctypes_object, **kwargs):
        return _bulk_to_python(ctypes_object)

    @classmethod
    def _write_header(cls, stream, value):
        stream.write(len(value).to_bytes(ctypes.sizeof(ctypes.c_int), byteorder=PROTOCOL_BYTE_ORDER))

    @classmethod
    def from_python(cls, stream, value, **kwargs):
        cls._write_header(stream, value)

        if _bulk_from_python(cls, stream, value):
            return

        for x in value:
            cls.primitive_type.from_python(stream, x)


class ByteArray(PrimitiveArray):
    _type_name = NAME_BYTE_ARR
    _type_id = TYPE_BYTE_ARR
    primitive_type = Byte
    type_code = TC_BYTE_ARRAY

    @classmethod
    def to_python(cls, ctypes_object, **kwargs):
        return bytes(ctypes_object.data)

    @classmethod
    def from_python(cls, stream, value, **kwargs):
        cls._write_header(stream, value)
        stream.write(bytearray(value))


class ShortArray(PrimitiveArray):
    _type_name = NAME_SHORT_ARR
    _type_id = TYPE_SHORT_ARR
    primitive_type = Short
    type_code = TC_SHORT_ARRAY
    _struct_format = 'h'
    _wire_dtype = '<i2'


class IntArray(PrimitiveArray):
    _type_name = NAME_INT_ARR
    _type_id = TYPE_INT_ARR
    primitive_type = Int
    type_code = TC_INT_ARRAY
    _struct_format = 'i'
    _wire_dtype = '<i4'


class LongArray(PrimitiveArray):
    _type_name = NAME_LONG_ARR
    _type_id = TYPE_LONG_ARR
    primitive_type = Long
    type_code = TC_LONG_ARRAY
    _struct_format = 'q'
    _wire_dtype = '<i8'


class FloatArray(PrimitiveArray):
    _type_name = NAME_FLOAT_ARR
    _type_id = TYPE_FLOAT_ARR
    primitive_type = Float
    type_code = TC_FLOAT_ARRAY
    _struct_format = 'f'
    _wire_dtype = '<f4'


class DoubleArray(PrimitiveArray):
    _type_name = NAME_DOUBLE_ARR
    _type_id = TYPE_DOUBLE_ARR
    primitive_type = Double
    type_code = TC_DOUBLE_ARRAY
    _struct_format = 'd'
    _wire_dtype = '<f8'


class CharArray(PrimitiveArray):
    _type_name = NAME_CHAR_ARR
    _type_id = TYPE_CHAR_ARR
    primitive_type = Char
    type_code = TC_CHAR_ARRAY


class BoolArray(PrimitiveArray):
    _type_name = NAME_BOOLEAN_ARR
    _type_id = TYPE_BOOLEAN_ARR
    primitive_type = Bool
    type_code = TC_BOOL_ARRAY


class PrimitiveArrayObject(Nullable):
    """
    Base class for primitive array object. Type code plus payload.
    """
    _type_name = None
    _type_id = None
    primitive_type = None
    type_code = None
    pythonic = list
    default = []

    #: ``struct`` format character used to encode the whole array in one call. ``None`` keeps the
    #: element-by-element path (types whose element encoding is not a plain little-endian scalar).
    _struct_format = None

    #: Buffer dtype string that already matches the wire layout exactly. When the value reports this
    #: dtype, its bytes are written straight through with no per-element work at all. ``None``
    #: disables that path.
    _wire_dtype = None

    @classmethod
    def build_c_type(cls, stream):
        length = int.from_bytes(
            stream.slice(stream.tell() + ctypes.sizeof(ctypes.c_byte), ctypes.sizeof(ctypes.c_int)),
            byteorder=PROTOCOL_BYTE_ORDER
        )

        return type(
            cls.__name__,
            (ctypes.LittleEndianStructure,),
            {
                '_pack_': 1,
                '_fields_': [
                    ('type_code', ctypes.c_byte),
                    ('length', ctypes.c_int),
                    ('data', cls.primitive_type.c_type * length),
                ],
            }
        )

    @classmethod
    def parse_not_null(cls, stream):
        c_type = cls.build_c_type(stream)
        stream.seek(ctypes.sizeof(c_type), SEEK_CUR)
        return c_type

    @classmethod
    def to_python_not_null(cls, ctypes_object, **kwargs):
        return _bulk_to_python(ctypes_object)

    @classmethod
    def from_python_not_null(cls, stream, value, **kwargs):
        cls._write_header(stream, value)

        if _bulk_from_python(cls, stream, value):
            return

        for x in value:
            cls.primitive_type.from_python(stream, x)

    @classmethod
    def _write_header(cls, stream, value):
        stream.write(cls.type_code)
        stream.write(len(value).to_bytes(ctypes.sizeof(ctypes.c_int), byteorder=PROTOCOL_BYTE_ORDER))


class ByteArrayObject(PrimitiveArrayObject):
    _type_name = NAME_BYTE_ARR
    _type_id = TYPE_BYTE_ARR
    primitive_type = Byte
    type_code = TC_BYTE_ARRAY

    @classmethod
    def to_python_not_null(cls, ctypes_object, **kwargs):
        return bytes(ctypes_object.data)

    @classmethod
    def from_python_not_null(cls, stream, value, **kwargs):
        cls._write_header(stream, value)

        if isinstance(value, (bytes, bytearray)):
            stream.write(value)
            return

        try:
            # `value` is a `bytearray` or a sequence of integer values
            # in range 0 to 255
            value_buffer = bytearray(value)
        except ValueError:
            # `value` is a sequence of integers in range -128 to 127
            value_buffer = bytearray()
            for ch in value:
                if -128 <= ch <= 255:
                    value_buffer.append(ctypes.c_ubyte(ch).value)
                else:
                    raise ValueError(
                        'byte must be in range(-128, 256)!'
                    ) from None

        stream.write(value_buffer)


class ShortArrayObject(PrimitiveArrayObject):
    _type_name = NAME_SHORT_ARR
    _type_id = TYPE_SHORT_ARR
    primitive_type = Short
    type_code = TC_SHORT_ARRAY
    _struct_format = 'h'
    _wire_dtype = '<i2'


class IntArrayObject(PrimitiveArrayObject):
    _type_name = NAME_INT_ARR
    _type_id = TYPE_INT_ARR
    primitive_type = Int
    type_code = TC_INT_ARRAY
    _struct_format = 'i'
    _wire_dtype = '<i4'


class LongArrayObject(PrimitiveArrayObject):
    _type_name = NAME_LONG_ARR
    _type_id = TYPE_LONG_ARR
    primitive_type = Long
    type_code = TC_LONG_ARRAY
    _struct_format = 'q'
    _wire_dtype = '<i8'


class FloatArrayObject(PrimitiveArrayObject):
    _type_name = NAME_FLOAT_ARR
    _type_id = TYPE_FLOAT_ARR
    primitive_type = Float
    type_code = TC_FLOAT_ARRAY
    _struct_format = 'f'
    _wire_dtype = '<f4'


class DoubleArrayObject(PrimitiveArrayObject):
    _type_name = NAME_DOUBLE_ARR
    _type_id = TYPE_DOUBLE_ARR
    primitive_type = Double
    type_code = TC_DOUBLE_ARRAY
    _struct_format = 'd'
    _wire_dtype = '<f8'


class CharArrayObject(PrimitiveArrayObject):
    _type_name = NAME_CHAR_ARR
    _type_id = TYPE_CHAR_ARR
    primitive_type = Char
    type_code = TC_CHAR_ARRAY

    @classmethod
    def to_python_not_null(cls, ctypes_object, **kwargs):
        values = super().to_python_not_null(ctypes_object, **kwargs)
        return [
            v.to_bytes(
                ctypes.sizeof(cls.primitive_type.c_type),
                byteorder=PROTOCOL_BYTE_ORDER
            ).decode(
                PROTOCOL_CHAR_ENCODING
            ) for v in values
        ]


class BoolArrayObject(PrimitiveArrayObject):
    _type_name = NAME_BOOLEAN_ARR
    _type_id = TYPE_BOOLEAN_ARR
    primitive_type = Bool
    type_code = TC_BOOL_ARRAY

    @classmethod
    def to_python_not_null(cls, ctypes_object, **kwargs):
        return [ctypes_object.data[i] != 0 for i in range(ctypes_object.length)]
