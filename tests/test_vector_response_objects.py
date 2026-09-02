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
Server-free differential coverage for ``VectorResponse`` on binary-object values.

The one-pass decoder has direct readers for the field types a vector row usually carries and
falls back to the generic machinery, per field, for everything else. This file proves the two
paths agree on values richer than the benchmark's ``Article{vec}``: many field types, a ``None``
field, a nested object, two value types in one page, and both schema-footer encodings. Every
value is written by the client's own object writer, decoded once by ``VectorResponse`` and once
by the generic path the cursor used before (page parse, then ``unwrap_binary``), and both
results must equal each other and the object that was written.
"""
import asyncio
import ctypes
import struct
from collections import OrderedDict
from datetime import datetime

import pytest

from pygridgain import GenericObjectMeta
from pygridgain.aio_client import AioClient
from pygridgain.client import Client
from pygridgain.datatypes import (
    AnyDataObject, BinaryObject, Bool, BoolObject, DoubleObject, Float, FloatArrayObject, IntObject, Long,
    LongObject, Map, String, StringArrayObject, StructArray, TimestampObject
)
from pygridgain.queries.response import Response, VectorResponse
from pygridgain.stream import AioBinaryStream, BinaryStream, READ_BACKWARD


class _Ctx:
    @staticmethod
    def is_status_flags_supported():
        return True


class _Registry:
    """A client stand-in: the complex-types registry, the footer flag, and the real unwrap."""

    def __init__(self, compact_footer):
        self.compact_footer = compact_footer
        self._classes = {}

    def register_binary_type(self, data_class, affinity_key_field=None):
        self._classes[(data_class.type_id, data_class.schema_id)] = data_class

    def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))

    def unwrap_binary(self, value):
        # The real Client.unwrap_binary, bound to this registry: this is the reference path.
        return Client.unwrap_binary(self, value)


class Inner(metaclass=GenericObjectMeta, type_name='Inner',
            schema=OrderedDict([('label', String), ('n', IntObject)])):
    pass


class Rich(metaclass=GenericObjectMeta, type_name='Rich', schema=OrderedDict([
    ('title', String),              # direct reader
    ('vec', FloatArrayObject),      # direct reader
    ('count', IntObject),           # direct reader
    ('weight', DoubleObject),       # direct reader
    ('big', LongObject),            # direct reader
    ('flag', BoolObject),           # no direct reader: per-field generic fallback
    ('tags', StringArrayObject),    # fallback
    ('when', TimestampObject),      # fallback
    ('note', String),               # written as None: the TC_NULL branch
    ('inner', BinaryObject),        # nested object: fallback through BinaryObject.parse
])):
    pass


class Article(metaclass=GenericObjectMeta, type_name='Article',
              schema=OrderedDict([('vec', FloatArrayObject)])):
    pass


def rich(i):
    return Rich(title=f'row {i}', vec=[0.5 * i, -1.25, 3.0], count=i, weight=i / 8.0, big=1 << (40 + i),
                flag=bool(i % 2), tags=['a', f'tag{i}'], when=(datetime(2026, 9, 2, 12, 0, i), 0),
                note=None, inner=Inner(label=f'inner {i}', n=10 * i))


def wrapped(registry, obj):
    """A cache value the way the server ships it: TC_ARRAY_WRAPPED_OBJECTS around the object."""
    with BinaryStream(registry) as stream:
        registry.register_binary_type(type(obj))
        obj._from_python(stream)
        payload = stream.getvalue()
    return b''.join((b'\x1b', struct.pack('<i', len(payload)), payload, struct.pack('<i', 0)))


def key(registry, value):
    with BinaryStream(registry) as stream:
        LongObject.from_python(stream, value)
        return stream.getvalue()


def frame(payload):
    return bytearray(struct.pack('<iqh', 8 + 2 + len(payload), 7, 0) + payload)


def decode_fast(registry, buf, **kwargs):
    response = VectorResponse(protocol_context=_Ctx(), following=None, has_cursor=True, **kwargs)
    with BinaryStream(registry, buf) as stream:
        response_class = response.parse(stream)
        assert ctypes.sizeof(response_class) == len(buf)
        parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
    return response.to_python(parsed)['data']


def decode_generic(registry, buf, legacy):
    """The path the client took before: generic page parse, then unwrap_binary per element."""
    if legacy:
        rows_type = Map
    else:
        rows_type = StructArray([('key', AnyDataObject), ('value', AnyDataObject), ('score', Float)])
    response = Response(protocol_context=_Ctx(), following=[('cursor', Long), ('data', rows_type), ('more', Bool)])
    with BinaryStream(registry, buf) as stream:
        response_class = response.parse(stream)
        parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
    data = response.to_python(parsed)['data']
    if legacy:
        return [(registry.unwrap_binary(k), registry.unwrap_binary(v)) for k, v in data.items()]
    return [(registry.unwrap_binary(r['key']), registry.unwrap_binary(r['value']), r['score']) for r in data]


@pytest.mark.parametrize('compact_footer', [False, True])
def test_rich_objects_legacy_rows_match_the_generic_path(compact_footer):
    registry = _Registry(compact_footer)
    objects = [rich(1), Article(vec=[1.0, 2.0, 3.0, 4.0]), rich(2)]
    payload = b''.join((
        struct.pack('<q', 11), struct.pack('<i', len(objects)),
        *(key(registry, i) + wrapped(registry, obj) for i, obj in enumerate(objects)),
        b'\x00'))
    buf = frame(payload)

    fast = decode_fast(registry, buf, legacy=True)
    generic = decode_generic(registry, buf, legacy=True)

    assert fast == generic
    assert fast == [(i, obj) for i, obj in enumerate(objects)]
    decoded = fast[0][1]
    assert decoded.note is None
    assert decoded.inner == Inner(label='inner 1', n=10)
    assert decoded.when == (datetime(2026, 9, 2, 12, 0, 1), 0)
    assert isinstance(decoded.vec, list) and isinstance(generic[0][1].vec, list)


@pytest.mark.parametrize('compact_footer', [False, True])
def test_rich_objects_flagged_rows_with_scores_match_the_generic_path(compact_footer):
    registry = _Registry(compact_footer)
    objects = [rich(3), rich(4)]
    payload = b''.join((
        struct.pack('<q', 12), struct.pack('<i', len(objects)),
        *(key(registry, i) + wrapped(registry, obj) + struct.pack('<f', 0.5 + i) for i, obj in enumerate(objects)),
        b'\x01'))
    buf = frame(payload)

    fast = decode_fast(registry, buf, with_scores=True)
    generic = decode_generic(registry, buf, legacy=False)

    assert fast == generic
    assert [row[1] for row in fast] == objects
    assert [row[2] for row in fast] == [0.5, 1.5]


def test_two_value_types_resolve_their_own_classes():
    registry = _Registry(False)
    objects = [Article(vec=[9.0]), rich(5), Article(vec=[8.0, 7.0])]
    payload = b''.join((
        struct.pack('<q', 13), struct.pack('<i', len(objects)),
        *(key(registry, i) + wrapped(registry, obj) for i, obj in enumerate(objects)),
        b'\x00'))
    fast = decode_fast(registry, frame(payload), legacy=True)
    assert [type(row[1]).__name__ for row in fast] == ['Article', 'Rich', 'Article']
    assert fast == [(i, obj) for i, obj in enumerate(objects)]


class _AioRegistry(_Registry):
    """The asyncio client's face of the registry: coroutine lookups, the real async unwrap."""

    async def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))

    def register_binary_type(self, data_class, affinity_key_field=None):
        self._classes[(data_class.type_id, data_class.schema_id)] = data_class

    async def unwrap_binary(self, value):
        return await AioClient.unwrap_binary(self, value)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.mark.parametrize('compact_footer', [False, True])
def test_rich_objects_on_the_asyncio_stream_match_the_generic_async_path(compact_footer):
    """Nested objects and other fallback fields must not run a sync parse on an async stream."""
    sync_registry = _Registry(compact_footer)          # objects are written with the sync writer
    objects = [rich(6), Article(vec=[2.0]), rich(7)]
    payload = b''.join((
        struct.pack('<q', 14), struct.pack('<i', len(objects)),
        *(key(sync_registry, i) + wrapped(sync_registry, obj) + struct.pack('<f', 0.25 * i)
          for i, obj in enumerate(objects)),
        b'\x00'))
    buf = frame(payload)
    registry = _AioRegistry(compact_footer)
    registry._classes = dict(sync_registry._classes)

    async def fast():
        response = VectorResponse(protocol_context=_Ctx(), following=None, has_cursor=True, with_scores=True)
        with AioBinaryStream(registry, buf) as stream:
            response_class = await response.parse_async(stream)
            assert ctypes.sizeof(response_class) == len(buf)
            parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
        return (await response.to_python_async(parsed))['data']

    async def generic():
        rows_type = StructArray([('key', AnyDataObject), ('value', AnyDataObject), ('score', Float)])
        response = Response(protocol_context=_Ctx(),
                            following=[('cursor', Long), ('data', rows_type), ('more', Bool)])
        with AioBinaryStream(registry, buf) as stream:
            response_class = await response.parse_async(stream)
            parsed = stream.read_ctype(response_class, direction=READ_BACKWARD)
        data = (await response.to_python_async(parsed))['data']
        return [(await registry.unwrap_binary(r['key']), await registry.unwrap_binary(r['value']), r['score'])
                for r in data]

    fast_rows = _run(fast())
    generic_rows = _run(generic())
    assert fast_rows == generic_rows
    assert [row[1] for row in fast_rows] == objects
    assert fast_rows[0][1].inner == Inner(label='inner 6', n=60)
