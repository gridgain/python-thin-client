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
Client stand-ins for the server-free tests.

A binary stream asks its client for three things only: the compact-footer flag, the
complex-types registry, and ``unwrap_binary``. These stubs answer all three in process, and
keep a log of the types that were registered so a test can assert on registration without a
cluster. ``unwrap_binary`` is the client's own method bound to the stub, so a test that uses
it compares against the real code path.
"""
from pygridgain.aio_client import AioClient
from pygridgain.client import Client


class BinaryRegistryStub:
    """A client stand-in: the complex-types registry, the footer flag, and the real unwrap."""

    def __init__(self, compact_footer=True):
        self.compact_footer = compact_footer
        self.registered = []
        self._classes = {}

    def register_binary_type(self, data_class, affinity_key_field=None):
        self.registered.append(data_class)
        self._classes[(data_class.type_id, data_class.schema_id)] = data_class

    def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))

    def unwrap_binary(self, value):
        return Client.unwrap_binary(self, value)

    @property
    def registered_names(self):
        return [data_class.type_name for data_class in self.registered]


class AioBinaryRegistryStub(BinaryRegistryStub):
    """The asyncio client's face of the same stand-in: coroutine registration and lookups."""

    async def register_binary_type(self, data_class, affinity_key_field=None):
        super().register_binary_type(data_class, affinity_key_field)

    async def query_binary_type(self, type_id, schema=None):
        return self._classes.get((type_id, schema))

    async def unwrap_binary(self, value):
        return await AioClient.unwrap_binary(self, value)
