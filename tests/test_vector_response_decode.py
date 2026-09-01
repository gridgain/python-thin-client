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
Server-free coverage for ``VectorResponse``, the one-pass vector response decoder.

The frames are assembled with the client's own element writers, so the bytes are valid by
construction. Beyond the row values, every case asserts the layout contract the decoder must
keep for ``Query.perform``: the ctypes class it returns spans the response exactly, so the
backward ``read_ctype`` lines up and the header fields stay addressable.
"""
import asyncio
import ctypes
import struct
import uuid

from pygridgain.datatypes import LongObject, String, UUIDObject
from pygridgain.queries.response import VectorResponse
from pygridgain.stream import AioBinaryStream, BinaryStream, READ_BACKWARD


class _Ctx:
    @staticmethod
    def is_status_flags_supported():
        return True


class _Client:
    """What the decoder touches on a client for rows without binary objects."""
    compact_footer = False

    @staticmethod
    def unwrap_binary(value):
        return value


def elements(*writer_value_pairs):
    with BinaryStream(_Client()) as stream:
        for writer, value in writer_value_pairs:
            writer.from_python(stream, value)
        return stream.getvalue()


def frame(payload):
    # StatusFlagResponseHeader: length counts everything after the length int itself.
    return bytearray(struct.pack('<iqh', 8 + 2 + len(payload), 42, 0) + payload)


def parse(payload, **kwargs):
    buf = frame(payload)
    response = VectorResponse(protocol_context=_Ctx(), following=None, **kwargs)
    with BinaryStream(_Client(), buf) as stream:
        response_class = response.parse(stream)
        assert ctypes.sizeof(response_class) == len(buf), 'decoder must span the exact response'
        parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
    return response.to_python(parsed)


def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]


def test_keys_and_scores_with_cursor():
    payload = b''.join((
        struct.pack('<q', 77), struct.pack('<i', 3),
        elements((LongObject, 10)), struct.pack('<f', 1.5),
        elements((LongObject, 11)), struct.pack('<f', 0.25),
        elements((LongObject, 12)), struct.pack('<f', -2.0),
        b'\x01'))
    result = parse(payload, with_scores=True, no_content=True, has_cursor=True)
    assert result['cursor'] == 77
    assert result['more'] is True
    assert result['data'] == [(10, f32(1.5)), (11, f32(0.25)), (12, f32(-2.0))]


def test_key_value_score_rows():
    payload = b''.join((
        struct.pack('<q', 1), struct.pack('<i', 2),
        elements((LongObject, 1), (String, 'alpha')), struct.pack('<f', 0.5),
        elements((LongObject, 2), (String, 'beta')), struct.pack('<f', 0.125),
        b'\x00'))
    result = parse(payload, with_scores=True, has_cursor=True)
    assert result['more'] is False
    assert result['data'] == [(1, 'alpha', f32(0.5)), (2, 'beta', f32(0.125))]


def test_bare_keys():
    payload = b''.join((
        struct.pack('<q', 5), struct.pack('<i', 2),
        elements((LongObject, 21)), elements((LongObject, 22)), b'\x00'))
    result = parse(payload, no_content=True, has_cursor=True)
    assert result['data'] == [21, 22]


def test_legacy_pairs_including_the_generic_fallback():
    """A UUID has no direct reader, so its element must route through the generic machinery."""
    key_uuid = uuid.UUID('12345678-1234-5678-1234-567812345678')
    payload = b''.join((
        struct.pack('<q', 9), struct.pack('<i', 3),
        elements((LongObject, 1), (String, 'plain')),
        elements((LongObject, 2), (UUIDObject, key_uuid)),
        elements((LongObject, 3), (String, None)),
        b'\x00'))
    result = parse(payload, legacy=True, has_cursor=True)
    assert result['data'] == [(1, 'plain'), (2, key_uuid), (3, None)]


def test_page_without_cursor():
    payload = struct.pack('<i', 1) + elements((LongObject, 8)) + b'\x00'
    result = parse(payload, no_content=True, has_cursor=False)
    assert 'cursor' not in result
    assert result['data'] == [8]


def test_empty_result():
    payload = struct.pack('<q', 3) + struct.pack('<i', 0) + b'\x00'
    result = parse(payload, with_scores=True, no_content=True, has_cursor=True)
    assert result['data'] == []
    assert result['more'] is False


def test_async_parse_matches_sync():
    payload = b''.join((
        struct.pack('<q', 4), struct.pack('<i', 2),
        elements((LongObject, 31)), struct.pack('<f', 0.75),
        elements((LongObject, 32)), struct.pack('<f', 0.5),
        b'\x00'))

    async def run():
        buf = frame(payload)
        response = VectorResponse(protocol_context=_Ctx(), following=None,
                                  with_scores=True, no_content=True, has_cursor=True)
        with AioBinaryStream(_Client(), buf) as stream:
            response_class = await response.parse_async(stream)
            assert ctypes.sizeof(response_class) == len(buf)
            parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
        return await response.to_python_async(parsed)

    result = asyncio.new_event_loop().run_until_complete(run())
    assert result['data'] == [(31, f32(0.75)), (32, f32(0.5))]
    assert result['cursor'] == 4
