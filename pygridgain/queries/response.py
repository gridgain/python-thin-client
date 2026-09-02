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
import struct
import sys
from io import SEEK_CUR

import attr
from collections import OrderedDict
import ctypes

from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.constants import RHF_TOPOLOGY_CHANGED, RHF_ERROR
from pygridgain.datatypes import (
    AnyDataObject, Bool, DoubleObject, FloatArrayObject, Int, IntObject, Long, LongObject, String, StringArray, Struct
)
from pygridgain.datatypes.binary import body_struct, enum_struct, schema_struct
from pygridgain.datatypes.internal import cached_c_type
from pygridgain.queries.op_codes import OP_SUCCESS
from pygridgain.stream import READ_BACKWARD


class StatusFlagResponseHeader(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('length', ctypes.c_int),
        ('query_id', ctypes.c_longlong),
        ('flags', ctypes.c_short)
    ]


class ResponseHeader(ctypes.LittleEndianStructure):
    _pack_ = 1
    _fields_ = [
        ('length', ctypes.c_int),
        ('query_id', ctypes.c_longlong),
        ('status_code', ctypes.c_int)
    ]


@attr.s
class Response:
    following = attr.ib(type=list, factory=list)
    protocol_context = attr.ib(type=type(ProtocolContext), default=None)
    _response_class_name = 'Response'

    def __attrs_post_init__(self):
        # replace None with empty list
        self.following = self.following or []

    def __parse_header(self, stream):
        init_pos = stream.tell()

        if self.protocol_context.is_status_flags_supported():
            header_class = StatusFlagResponseHeader
        else:
            header_class = ResponseHeader

        header_len = ctypes.sizeof(header_class)
        header = stream.read_ctype(header_class)
        stream.seek(header_len, SEEK_CUR)

        fields = []
        has_error = False
        if self.protocol_context.is_status_flags_supported():
            if header.flags & RHF_TOPOLOGY_CHANGED:
                fields = [
                    ('affinity_version', ctypes.c_longlong),
                    ('affinity_minor', ctypes.c_int),
                ]

            if header.flags & RHF_ERROR:
                fields.append(('status_code', ctypes.c_int))
                has_error = True
        else:
            has_error = header.status_code != OP_SUCCESS

        if fields:
            stream.seek(sum(ctypes.sizeof(c_type) for _, c_type in fields), SEEK_CUR)

        if has_error:
            msg_type = String.parse(stream)
            fields.append(('error_message', msg_type))

        return not has_error, init_pos, header_class, fields

    def __build_response_class(self, stream, init_pos, header_class, fields):
        # One shared class per response shape: the hot responses (cache ops, query pages) repeat
        # a handful of shapes, and their field classes come from shared-per-shape caches.
        response_class = cached_c_type(self._response_class_name, (header_class,), fields)

        stream.seek(init_pos + ctypes.sizeof(response_class))
        return response_class

    def parse(self, stream):
        success, init_pos, header_class, fields = self.__parse_header(stream)
        if success:
            self._parse_success(stream, fields)

        return self.__build_response_class(stream, init_pos, header_class, fields)

    async def parse_async(self, stream):
        success, init_pos, header_class, fields = self.__parse_header(stream)
        if success:
            await self._parse_success_async(stream, fields)

        return self.__build_response_class(stream, init_pos, header_class, fields)

    def _parse_success(self, stream, fields: list):
        for name, ignite_type in self.following:
            c_type = ignite_type.parse(stream)
            fields.append((name, c_type))

    async def _parse_success_async(self, stream, fields: list):
        for name, ignite_type in self.following:
            c_type = await ignite_type.parse_async(stream)
            fields.append((name, c_type))

    def to_python(self, ctypes_object, **kwargs):
        if not self.following:
            return None

        result = OrderedDict()
        for name, c_type in self.following:
            result[name] = c_type.to_python(getattr(ctypes_object, name), **kwargs)

        return result

    async def to_python_async(self, ctypes_object, **kwargs):
        if not self.following:
            return None

        values = await asyncio.gather(
            *[c_type.to_python_async(getattr(ctypes_object, name), **kwargs) for name, c_type in self.following]
        )

        return OrderedDict([(name, values[i]) for i, (name, _) in enumerate(self.following)])


@attr.s
class SQLResponse(Response):
    """
    The response class of SQL functions is special in the way the row-column
    data is counted in it. Basically, GridGain thin client API is following a
    “counter right before the counted objects” rule in most of its parts.
    SQL ops are breaking this rule.
    """
    include_field_names = attr.ib(type=bool, default=False)
    has_cursor = attr.ib(type=bool, default=False)
    _response_class_name = 'SQLResponse'

    def fields_or_field_count(self):
        if self.include_field_names:
            return 'fields', StringArray
        return 'field_count', Int

    def _parse_success(self, stream, fields: list):
        body_struct = self.__create_body_struct()
        body_class = body_struct.parse(stream)
        body = stream.read_ctype(body_class, direction=READ_BACKWARD)

        data_fields, field_count = [], self.__get_fields_count(body)
        for i in range(body.row_count):
            row_fields = []
            for j in range(field_count):
                field_class = AnyDataObject.parse(stream)
                row_fields.append(('column_{}'.format(j), field_class))

            self.__row_post_process(i, row_fields, data_fields)

        self.__body_class_post_process(body_class, fields, data_fields)

    async def _parse_success_async(self, stream, fields: list):
        body_struct = self.__create_body_struct()
        body_class = await body_struct.parse_async(stream)
        body = stream.read_ctype(body_class, direction=READ_BACKWARD)

        data_fields, field_count = [], self.__get_fields_count(body)
        for i in range(body.row_count):
            row_fields = []
            for j in range(field_count):
                field_class = await AnyDataObject.parse_async(stream)
                row_fields.append(('column_{}'.format(j), field_class))

            self.__row_post_process(i, row_fields, data_fields)

        self.__body_class_post_process(body_class, fields, data_fields)

    def __create_body_struct(self):
        following = [self.fields_or_field_count(), ('row_count', Int)]
        if self.has_cursor:
            following.insert(0, ('cursor', Long))
        return Struct(following)

    def __get_fields_count(self, body):
        if self.include_field_names:
            return body.fields.length
        return body.field_count

    @staticmethod
    def __row_post_process(idx, row_fields, data_fields):
        row_class = type(
            'SQLResponseRow',
            (ctypes.LittleEndianStructure,),
            {
                '_pack_': 1,
                '_fields_': row_fields,
            }
        )
        data_fields.append((f'row_{idx}', row_class))

    @staticmethod
    def __body_class_post_process(body_class, fields, data_fields):
        data_class = type(
            'SQLResponseData',
            (ctypes.LittleEndianStructure,),
            {
                '_pack_': 1,
                '_fields_': data_fields,
            }
        )
        fields += body_class._fields_ + [
            ('data', data_class),
            ('more', ctypes.c_byte),
        ]

    def to_python(self, ctypes_object, **kwargs):
        if getattr(ctypes_object, 'status_code', 0) == 0:
            result = self.__to_python_result_header(ctypes_object, **kwargs)

            for row_item in ctypes_object.data._fields_:
                row_name = row_item[0]
                row_object = getattr(ctypes_object.data, row_name)
                row = []
                for col_item in row_object._fields_:
                    col_name = col_item[0]
                    col_object = getattr(row_object, col_name)
                    row.append(AnyDataObject.to_python(col_object, **kwargs))
                result['data'].append(row)
            return result

    async def to_python_async(self, ctypes_object, **kwargs):
        if getattr(ctypes_object, 'status_code', 0) == 0:
            result = self.__to_python_result_header(ctypes_object, **kwargs)

            data_coro = []
            for row_item in ctypes_object.data._fields_:
                row_name = row_item[0]
                row_object = getattr(ctypes_object.data, row_name)
                row_coro = []
                for col_item in row_object._fields_:
                    col_name = col_item[0]
                    col_object = getattr(row_object, col_name)
                    row_coro.append(AnyDataObject.to_python_async(col_object, **kwargs))

                data_coro.append(asyncio.gather(*row_coro))

            result['data'] = await asyncio.gather(*data_coro)
            return result

    @staticmethod
    def __to_python_result_header(ctypes_object, *args, **kwargs):
        result = {
            'more': Bool.to_python(ctypes_object.more, *args, **kwargs),
            'data': [],
        }
        if hasattr(ctypes_object, 'fields'):
            result['fields'] = StringArray.to_python(ctypes_object.fields, *args, **kwargs)
        else:
            result['field_count'] = Int.to_python(ctypes_object.field_count, *args, **kwargs)

        if hasattr(ctypes_object, 'cursor'):
            result['cursor'] = Long.to_python(ctypes_object.cursor, *args, **kwargs)
        return result


#: Sentinel: the direct reader cannot decode this element, use the generic machinery.
_FALLBACK = object()


def _is_async_stream(stream):
    """True for AioBinaryStream: its registry lookup is a coroutine, so no sync parse may run on it."""
    return asyncio.iscoroutinefunction(getattr(stream, 'get_dataclass', None))


# Wire type codes the direct readers understand, as integers (buf[i] indexing yields ints).
_TC_INT = 0x03
_TC_LONG = 0x04
_TC_DOUBLE = 0x06
_TC_STRING = 0x09
_TC_FLOAT_ARRAY = 0x10
_TC_WRAPPED = 0x1b
_TC_NULL = 0x65
_TC_COMPLEX = 0x67


@attr.s
class VectorResponse(Response):
    """
    Vector query response with the rows decoded in one pass, straight off the response buffer.

    The generic path pays for a vector row three times: the page parse builds one ctypes
    structure per element and copies every wrapped binary value out as an opaque blob, and the
    cursor then re-parses each blob (``unwrap_binary``) to build the Python object. Response
    deserialization measured as the bulk of pygridgain's vector-query cost, so this class
    replaces it for the row section: keys, values and scores leave ``parse`` as final Python
    values, already shaped the way the cursor yields them, and ``to_python`` just hands them
    over.

    Only the shapes a vector row actually carries get direct readers: long/int/double/string
    keys, binary objects with primitive or float-array fields, raw float scores. Any element
    outside them falls back to the generic machinery at the same stream position, one element
    at a time, so an unusual payload costs the old price instead of failing. The ctypes layout
    the parent contract requires stays byte-exact: the row section is described as one opaque
    byte blob.
    """
    with_scores = attr.ib(type=bool, default=False)
    no_content = attr.ib(type=bool, default=False)
    #: Legacy (flags == 0) responses carry a key-value map; flagged ones a row struct.
    legacy = attr.ib(type=bool, default=False)
    has_cursor = attr.ib(type=bool, default=False)
    _response_class_name = 'VectorResponse'
    _rows = None

    def _parse_success(self, stream, fields: list):
        if self.has_cursor:
            fields.append(('cursor', ctypes.c_longlong))
            stream.seek(ctypes.sizeof(ctypes.c_longlong), SEEK_CUR)

        data_pos = stream.tell()
        buf = stream.getbuffer()
        self._rows = self._decode_rows(stream, buf)

        fields.append(('data', ctypes.c_byte * (stream.tell() - data_pos)))
        fields.append(('more', ctypes.c_byte))
        stream.seek(1, SEEK_CUR)

    async def _parse_success_async(self, stream, fields: list):
        if self.has_cursor:
            fields.append(('cursor', ctypes.c_longlong))
            stream.seek(ctypes.sizeof(ctypes.c_longlong), SEEK_CUR)

        data_pos = stream.tell()
        buf = stream.getbuffer()
        self._rows = await self._decode_rows_async(stream, buf)

        fields.append(('data', ctypes.c_byte * (stream.tell() - data_pos)))
        fields.append(('more', ctypes.c_byte))
        stream.seek(1, SEEK_CUR)

    def to_python(self, ctypes_object, **kwargs):
        result = {'data': self._rows, 'more': Bool.to_python(ctypes_object.more)}
        if self.has_cursor:
            result['cursor'] = ctypes_object.cursor
        return result

    async def to_python_async(self, ctypes_object, **kwargs):
        return self.to_python(ctypes_object, **kwargs)

    def _decode_rows(self, stream, buf):
        count = struct.unpack_from('<i', buf, stream.tell())[0]
        stream.seek(4, SEEK_CUR)

        rows = []
        # The rows of one page share the value type, so the registry is asked once per shape.
        data_classes = {}

        if self.legacy:
            for _ in range(count):
                key = self._decode_any(stream, buf, data_classes)
                value = self._decode_any(stream, buf, data_classes)
                rows.append((key, value))
            return rows

        for _ in range(count):
            key = self._decode_any(stream, buf, data_classes)
            value = None if self.no_content else self._decode_any(stream, buf, data_classes)
            if self.with_scores:
                score = struct.unpack_from('<f', buf, stream.tell())[0]
                stream.seek(4, SEEK_CUR)
                rows.append((key, score) if self.no_content else (key, value, score))
            else:
                rows.append(key if self.no_content else (key, value))
        return rows

    async def _decode_rows_async(self, stream, buf):
        # The readers are pure CPU; only the registry lookup and the generic fallback need
        # awaiting on the asyncio client, and _decode_any raises _NeedsAsync for those.
        count = struct.unpack_from('<i', buf, stream.tell())[0]
        stream.seek(4, SEEK_CUR)

        rows = []
        data_classes = {}

        async def one():
            pos = stream.tell()
            try:
                return self._decode_any(stream, buf, data_classes)
            except _NeedsAsync as need:
                stream.seek(pos)
                return await self._decode_any_async(stream, buf, data_classes, need)

        if self.legacy:
            for _ in range(count):
                key = await one()
                value = await one()
                rows.append((key, value))
            return rows

        for _ in range(count):
            key = await one()
            value = None if self.no_content else await one()
            if self.with_scores:
                score = struct.unpack_from('<f', buf, stream.tell())[0]
                stream.seek(4, SEEK_CUR)
                rows.append((key, score) if self.no_content else (key, value, score))
            else:
                rows.append(key if self.no_content else (key, value))
        return rows

    def _decode_any(self, stream, buf, data_classes):
        """Decode one element to its final Python value; the stream ends up past it."""
        pos = stream.tell()
        type_code = buf[pos]

        if type_code == _TC_LONG:
            stream.seek(9, SEEK_CUR)
            return struct.unpack_from('<q', buf, pos + 1)[0]
        if type_code == _TC_INT:
            stream.seek(5, SEEK_CUR)
            return struct.unpack_from('<i', buf, pos + 1)[0]
        if type_code == _TC_DOUBLE:
            stream.seek(9, SEEK_CUR)
            return struct.unpack_from('<d', buf, pos + 1)[0]
        if type_code == _TC_STRING:
            length = struct.unpack_from('<i', buf, pos + 1)[0]
            stream.seek(5 + length, SEEK_CUR)
            return bytes(buf[pos + 5:pos + 5 + length]).decode('utf-8')
        if type_code == _TC_NULL:
            stream.seek(1, SEEK_CUR)
            return None
        if type_code == _TC_WRAPPED and sys.byteorder == 'little':
            payload_len = struct.unpack_from('<i', buf, pos + 1)[0]
            value, _ = self._decode_binary_object(stream, buf, pos + 5, data_classes)
            if value is not _FALLBACK:
                # type code + length + payload + trailing root offset
                stream.seek(pos + 5 + payload_len + 4)
                return value
        elif type_code == _TC_COMPLEX and sys.byteorder == 'little':
            value, end = self._decode_binary_object(stream, buf, pos, data_classes)
            if value is not _FALLBACK:
                stream.seek(end)
                return value

        return self._decode_element_generic(stream, pos)

    def _decode_binary_object(self, stream, buf, start, data_classes):
        """
        Decode one binary object laid out at ``start``, or return ``_FALLBACK`` untouched.

        Follows the same contract as the generic ``BinaryObject`` path: field types and order
        come from the complex types registry for (type_id, schema_id), the footer is skipped.
        """
        version, flags, type_id, _, length, schema_id, _ = struct.unpack_from('<bhiiiii', buf, start + 1)

        # USER_TYPE off or raw data present: shapes the registry walk cannot place - old path.
        if not (flags & 0x0001) or (flags & 0x0004):
            return _FALLBACK, start

        data_class = data_classes.get((type_id, schema_id))
        if data_class is None:
            data_class = self._query_binary_type_sync(stream, type_id, schema_id)
            if data_class is None:
                return _FALLBACK, start
            data_classes[(type_id, schema_id)] = data_class

        # The side effect the generic parse has: remember how this peer encodes schema footers.
        stream.compact_footer = bool(flags & 0x0020)

        result = data_class()
        result.version = version

        pos = start + 24
        for field_name, field_type in data_class.schema.items():
            value, pos = self._decode_field(stream, buf, pos, field_type)
            setattr(result, field_name, value)

        return result, start + length

    @staticmethod
    def _query_binary_type_sync(stream, type_id, schema_id):
        client = stream.client
        query = getattr(client, 'query_binary_type', None)
        if query is None:
            return None
        if asyncio.iscoroutinefunction(query):
            raise _NeedsAsync(type_id, schema_id)
        return query(type_id, schema_id)

    def _decode_field(self, stream, buf, pos, field_type):
        """Decode one object field to (value, next position), preferring the direct readers."""
        type_code = buf[pos]

        if type_code == _TC_NULL:
            return None, pos + 1
        if field_type is FloatArrayObject and type_code == _TC_FLOAT_ARRAY:
            length = struct.unpack_from('<i', buf, pos + 1)[0]
            end = pos + 5 + length * 4
            view = buf[pos + 5:end]
            try:
                return view.cast('f').tolist(), end
            finally:
                view.release()
        if field_type is LongObject and type_code == _TC_LONG:
            return struct.unpack_from('<q', buf, pos + 1)[0], pos + 9
        if field_type is IntObject and type_code == _TC_INT:
            return struct.unpack_from('<i', buf, pos + 1)[0], pos + 5
        if field_type is DoubleObject and type_code == _TC_DOUBLE:
            return struct.unpack_from('<d', buf, pos + 1)[0], pos + 9
        if field_type is String and type_code == _TC_STRING:
            length = struct.unpack_from('<i', buf, pos + 1)[0]
            return bytes(buf[pos + 5:pos + 5 + length]).decode('utf-8'), pos + 5 + length

        # A field with no direct reader takes the generic parser. On the asyncio client that
        # parser awaits the registry, so the whole element is redone on the async path instead.
        if _is_async_stream(stream):
            raise _NeedsAsync(None, None)
        stream.seek(pos)
        c_type = field_type.parse(stream)
        value = field_type.to_python(
            stream.read_ctype(c_type, direction=READ_BACKWARD), client=stream.client)
        return value, stream.tell()

    @staticmethod
    def _decode_element_generic(stream, pos):
        """The old price for one element: generic parse, then the unwrap the cursor used to do."""
        if _is_async_stream(stream):
            raise _NeedsAsync(None, None)
        stream.seek(pos)
        c_type = AnyDataObject.parse(stream)
        value = AnyDataObject.to_python(
            stream.read_ctype(c_type, direction=READ_BACKWARD), client=stream.client)
        unwrap = stream.client.unwrap_binary
        if asyncio.iscoroutinefunction(unwrap):
            raise _NeedsAsync(None, None)
        return unwrap(value)

    async def _decode_any_async(self, stream, buf, data_classes, need):
        """Asyncio twin of one element decode, entered only when the sync path raised."""
        pos = stream.tell()
        if need.type_id is not None:
            data_class = await stream.client.query_binary_type(need.type_id, need.schema_id)
            if data_class is not None:
                data_classes[(need.type_id, need.schema_id)] = data_class
                try:
                    return self._decode_any(stream, buf, data_classes)
                except _NeedsAsync:
                    pass  # a field inside still needs the async path: decode the whole element there

        stream.seek(pos)
        c_type = await AnyDataObject.parse_async(stream)
        value = await AnyDataObject.to_python_async(
            stream.read_ctype(c_type, direction=READ_BACKWARD), client=stream.client)
        return await stream.client.unwrap_binary(value)


class _NeedsAsync(Exception):
    """The sync decode hit a point that must await on the asyncio client."""

    def __init__(self, type_id, schema_id):
        super().__init__()
        self.type_id = type_id
        self.schema_id = schema_id


class BinaryTypeResponse(Response):
    _response_class_name = 'GetBinaryTypeResponse'

    def _parse_success(self, stream, fields: list):
        type_exists = self.__process_type_exists(stream, fields)

        if type_exists.value:
            resp_body_type = body_struct.parse(stream)
            fields.append(('body', resp_body_type))
            resp_body = stream.read_ctype(resp_body_type, direction=READ_BACKWARD)
            if resp_body.is_enum:
                resp_enum = enum_struct.parse(stream)
                fields.append(('enums', resp_enum))

            resp_schema_type = schema_struct.parse(stream)
            fields.append(('schema', resp_schema_type))

    async def _parse_success_async(self, stream, fields: list):
        type_exists = self.__process_type_exists(stream, fields)

        if type_exists.value:
            resp_body_type = await body_struct.parse_async(stream)
            fields.append(('body', resp_body_type))
            resp_body = stream.read_ctype(resp_body_type, direction=READ_BACKWARD)
            if resp_body.is_enum:
                resp_enum = await enum_struct.parse_async(stream)
                fields.append(('enums', resp_enum))

            resp_schema_type = await schema_struct.parse_async(stream)
            fields.append(('schema', resp_schema_type))

    @staticmethod
    def __process_type_exists(stream, fields):
        fields.append(('type_exists', ctypes.c_byte))
        type_exists = stream.read_ctype(ctypes.c_byte)
        stream.seek(ctypes.sizeof(ctypes.c_byte), SEEK_CUR)

        return type_exists

    def to_python(self, ctypes_object, **kwargs):
        if getattr(ctypes_object, 'status_code', 0) == 0:
            result = {
                'type_exists': Bool.to_python(ctypes_object.type_exists)
            }

            if hasattr(ctypes_object, 'body'):
                result.update(body_struct.to_python(ctypes_object.body))

            if hasattr(ctypes_object, 'enums'):
                result['enums'] = enum_struct.to_python(ctypes_object.enums)

            if hasattr(ctypes_object, 'schema'):
                result['schema'] = {
                    x['schema_id']: [
                        z['schema_field_id'] for z in x['schema_fields']
                    ]
                    for x in schema_struct.to_python(ctypes_object.schema)
                }
            return result

    async def to_python_async(self, ctypes_object, **kwargs):
        return self.to_python(ctypes_object, **kwargs)
