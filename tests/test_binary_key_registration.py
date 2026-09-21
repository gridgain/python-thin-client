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
Server-free coverage for binary type registration of objects written from the serialization
buffer.

Computing a complex key's hashcode serializes the object and stores the bytes in ``_buffer``
(``GenericObjectMeta.write_footer``), so partition-aware routing serializes the key only once.
Writing from that buffer must still register the object's type with the cluster: the bytes
carry a type ID, and nothing else in the request tells the server which fields that ID means.
"""
from collections import OrderedDict

import pytest

from pygridgain import GenericObjectMeta
from pygridgain.datatypes import BinaryObject, IntObject, String
from pygridgain.stream import AioBinaryStream, BinaryStream


class StudentKey(metaclass=GenericObjectMeta, type_name='test.model.StudentKey', schema=OrderedDict([
    ('ID', IntObject),
    ('DEPT', String),
])):
    pass


class Inner(metaclass=GenericObjectMeta, type_name='test.model.Inner', schema=OrderedDict([
    ('label', String),
])):
    pass


class NestedKey(metaclass=GenericObjectMeta, type_name='test.model.NestedKey', schema=OrderedDict([
    ('ID', IntObject),
    ('inner', BinaryObject),
])):
    pass


class _Registry:
    """A client stand-in: the complex-types registry, the footer flag, and a log of registrations."""

    def __init__(self, compact_footer=True):
        self.compact_footer = compact_footer
        self.registered = []
        self._classes = {}

    def register_binary_type(self, data_class, affinity_key_field=None):
        self.registered.append(data_class)
        self._classes[(data_class.type_id, data_class.schema_id)] = data_class

    def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))

    @property
    def registered_names(self):
        return [c.type_name for c in self.registered]


class _AioRegistry(_Registry):
    async def register_binary_type(self, data_class, affinity_key_field=None):
        super().register_binary_type(data_class)

    async def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))


# Factories, not instances: a written object caches its hashcode and its bytes, so every case
# needs objects of its own.
KEYS = [
    pytest.param(lambda: StudentKey(2, 'Business'), id='flat'),
    pytest.param(lambda: NestedKey(3, Inner('lorem')), id='nested'),
]


@pytest.mark.parametrize('make_key', KEYS)
def test_type_registered_when_written_from_buffer(make_key):
    key, registry = make_key(), _Registry()

    # Partition-aware routing does this before the key reaches the request stream.
    BinaryObject.hashcode(key, client=registry)
    assert key._buffer, 'precondition: hashcode must arm the buffer fast path'

    with BinaryStream(registry) as stream:
        BinaryObject.from_python(stream, key)

    assert key.type_name in registry.registered_names


@pytest.mark.parametrize('make_key', KEYS)
@pytest.mark.asyncio
async def test_type_registered_when_written_from_buffer_async(make_key):
    key, registry = make_key(), _AioRegistry()

    await BinaryObject.hashcode_async(key, client=registry)
    assert key._buffer, 'precondition: hashcode must arm the buffer fast path'

    with AioBinaryStream(registry) as stream:
        await BinaryObject.from_python_async(stream, key)

    assert key.type_name in registry.registered_names


@pytest.mark.parametrize('make_key', KEYS)
def test_buffer_fast_path_writes_same_bytes(make_key):
    """The buffer is an optimization only: it must not change what goes on the wire."""
    registry = _Registry()

    with BinaryStream(registry) as stream:
        BinaryObject.from_python(stream, make_key())
        slow_path = stream.getvalue()

    key = make_key()
    BinaryObject.hashcode(key, client=registry)
    assert key._buffer, 'precondition: hashcode must arm the buffer fast path'

    with BinaryStream(registry) as stream:
        BinaryObject.from_python(stream, key)
        fast_path = stream.getvalue()

    assert fast_path == slow_path

