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
A complex key must reach the cluster with its binary type registered.

A partition-aware client hashes the key to pick a node, and that hashing serializes the key and
stores the bytes on the object. Writing the request from those stored bytes used to skip the
type registration that the normal serialization path does, so the cluster held keys under a type
ID it could not resolve. These tests need a loaded partition mapping, which is why they live
under ``affinity``: without one, the routing code returns before it hashes the key.
"""
from collections import OrderedDict
from uuid import uuid4

import pytest

from pygridgain import AioClient, GenericObjectMeta
from pygridgain.api import cache_get_node_partitions, cache_get_node_partitions_async
from pygridgain.datatypes import IntObject, String
from tests.util import wait_for_condition, wait_for_condition_async


@pytest.fixture
def key_class():
    """A type name no earlier run has registered, so ``type_exists`` reflects only this test."""
    type_name = f'test.model.AffinityKey_{uuid4().hex}'
    return GenericObjectMeta(
        'AffinityKey', (), {},
        type_name=type_name,
        schema=OrderedDict([('ID', IntObject), ('DEPT', String)])
    )


@pytest.fixture
def cache(client):
    yield from __cache_fixture(client)


@pytest.fixture
async def async_cache(async_client):
    async for c in __cache_fixture(async_client):
        yield c


def __cache_fixture(client):
    """A cache whose partition mapping is loaded, so key hashing is on the path."""
    name = f'test_affinity_key_binary_type_{uuid4().hex}'

    def inner():
        cache = client.get_or_create_cache(name)
        try:
            __wait_for_ready_affinity(client, cache.cache_id)
            yield cache
        finally:
            cache.destroy()

    async def inner_async():
        cache = await client.get_or_create_cache(name)
        try:
            await __wait_for_ready_affinity(client, cache.cache_id)
            yield cache
        finally:
            await cache.destroy()

    return inner_async() if isinstance(client, AioClient) else inner()


def __wait_for_ready_affinity(client, cache_id):
    def inner():
        def condition():
            conn = client.random_node
            result = cache_get_node_partitions(conn, [cache_id])
            assert result.status == 0, result.message
            return len(result.value['partition_mapping']) == 1

        wait_for_condition(condition)

    async def inner_async():
        async def condition():
            conn = await client.random_node()
            result = await cache_get_node_partitions_async(conn, [cache_id])
            assert result.status == 0, result.message
            return len(result.value['partition_mapping']) == 1

        await wait_for_condition_async(condition)

    return inner_async() if isinstance(client, AioClient) else inner()


def test_complex_key_binary_type_is_registered(client, cache, key_class):
    key = key_class(2, 'Business')
    cache.put(key, 'Abe')

    assert cache.get(key) == 'Abe'
    assert client.get_binary_type(key_class.type_id)['type_exists'], \
        f'{key_class.type_name} was stored without its binary metadata'


@pytest.mark.asyncio
async def test_complex_key_binary_type_is_registered_async(async_client, async_cache, key_class):
    key = key_class(2, 'Business')
    await async_cache.put(key, 'Abe')

    assert await async_cache.get(key) == 'Abe'
    assert (await async_client.get_binary_type(key_class.type_id))['type_exists'], \
        f'{key_class.type_name} was stored without its binary metadata'

