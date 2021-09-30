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

import pytest

from pygridgain import Client, AioClient
from pygridgain.exceptions import CacheError, ClusterError
from tests.util import clear_ignite_work_dir, start_ignite_gen

from pygridgain.datatypes import ClusterState


@pytest.fixture(params=['with-persistence', 'without-persistence'])
def with_persistence(request):
    yield request.param == 'with-persistence'


@pytest.fixture(autouse=True)
def cleanup():
    clear_ignite_work_dir()
    yield None
    clear_ignite_work_dir()


@pytest.fixture(autouse=True)
def server1(with_persistence, cleanup):
    yield from start_ignite_gen(idx=1, use_persistence=with_persistence)


@pytest.fixture(autouse=True)
def server2(with_persistence, cleanup):
    yield from start_ignite_gen(idx=2, use_persistence=with_persistence)


@pytest.fixture(autouse=True)
def cluster_api_supported(request, server1):
    client = Client()
    with client.connect('127.0.0.1', 10801):
        if not client.protocol_context.is_cluster_api_supported():
            pytest.skip(f'skipped {request.node.name}, Cluster API is not supported.')


def check_cluster_state_error(cluster, state: int):
    with pytest.raises(ClusterError, match=f'Unknown cluster state \\[state={state}\\]'):
        cluster.set_state(state)


async def check_cluster_state_error_async(cluster, state: int):
    with pytest.raises(ClusterError, match=f'Unknown cluster state \\[state={state}\\]'):
        await cluster.set_state(state)


def test_cluster_set_state(with_persistence):
    key = 42
    val = 42
    start_state = ClusterState.INACTIVE if with_persistence else ClusterState.ACTIVE

    client = Client()
    with client.connect([("127.0.0.1", 10801), ("127.0.0.1", 10802)]):
        cluster = client.get_cluster()
        assert cluster.get_state() == start_state

        cluster.set_state(ClusterState.ACTIVE)
        assert cluster.get_state() == ClusterState.ACTIVE

        check_cluster_state_error(cluster, 3)
        check_cluster_state_error(cluster, 42)
        check_cluster_state_error(cluster, 1234567890987654321)
        check_cluster_state_error(cluster, -1)

        cache = client.get_or_create_cache("test_cache")
        cache.put(key, val)
        assert cache.get(key) == val

        cluster.set_state(ClusterState.ACTIVE_READ_ONLY)
        assert cluster.get_state() == ClusterState.ACTIVE_READ_ONLY

        assert cache.get(key) == val
        with pytest.raises(CacheError):
            cache.put(key, val + 1)

        cluster.set_state(ClusterState.INACTIVE)
        assert cluster.get_state() == ClusterState.INACTIVE

        with pytest.raises(CacheError):
            cache.get(key)

        with pytest.raises(CacheError):
            cache.put(key, val + 1)

        cluster.set_state(ClusterState.ACTIVE)
        assert cluster.get_state() == ClusterState.ACTIVE

        cache.put(key, val + 2)
        assert cache.get(key) == val + 2


@pytest.mark.asyncio
async def test_cluster_set_state_async(with_persistence):
    key = 42
    val = 42
    start_state = ClusterState.INACTIVE if with_persistence else ClusterState.ACTIVE

    client = AioClient()
    async with client.connect([("127.0.0.1", 10801), ("127.0.0.1", 10802)]):
        cluster = client.get_cluster()
        assert await cluster.get_state() == start_state

        await cluster.set_state(ClusterState.ACTIVE)
        assert await cluster.get_state() == ClusterState.ACTIVE

        await check_cluster_state_error_async(cluster, 3)
        await check_cluster_state_error_async(cluster, 42)
        await check_cluster_state_error_async(cluster, 1234567890987654321)
        await check_cluster_state_error_async(cluster, -1)

        cache = await client.get_or_create_cache("test_cache")
        await cache.put(key, val)
        assert await cache.get(key) == val

        await cluster.set_state(ClusterState.ACTIVE_READ_ONLY)
        assert await cluster.get_state() == ClusterState.ACTIVE_READ_ONLY

        assert await cache.get(key) == val
        with pytest.raises(CacheError):
            await cache.put(key, val + 1)

        await cluster.set_state(ClusterState.INACTIVE)
        assert await cluster.get_state() == ClusterState.INACTIVE

        with pytest.raises(CacheError):
            await cache.get(key)

        with pytest.raises(CacheError):
            await cache.put(key, val + 1)

        await cluster.set_state(ClusterState.ACTIVE)
        assert await cluster.get_state() == ClusterState.ACTIVE

        await cache.put(key, val + 2)
        assert await cache.get(key) == val + 2
