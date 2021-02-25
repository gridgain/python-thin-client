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

from pygridgain import Client
from pygridgain.api import cache_create, cache_destroy
from tests.util import start_ignite_gen


@pytest.fixture(scope='module', autouse=True)
def server1():
    yield from start_ignite_gen(1)


@pytest.fixture(scope='module', autouse=True)
def server2():
    yield from start_ignite_gen(2)


@pytest.fixture(scope='module', autouse=True)
def server3():
    yield from start_ignite_gen(3)


@pytest.fixture
def client():
    client = Client(partition_aware=True)

    client.connect([('127.0.0.1', 10800 + i) for i in range(1, 4)])

    yield client

    client.close()


@pytest.fixture
def client_not_connected():
    client = Client(partition_aware=True)
    yield client
    client.close()


@pytest.fixture
def cache(connected_client):
    cache_name = 'my_bucket'
    conn = connected_client.random_node

    cache_create(conn, cache_name)
    yield cache_name
    cache_destroy(conn, cache_name)


@pytest.fixture(scope='module', autouse=True)
def skip_if_no_affinity(request, server1):
    client = Client(partition_aware=True)
    client.connect('127.0.0.1', 10801)

    if not client.partition_awareness_supported_by_protocol:
        pytest.skip(f'skipped {request.node.name}, partition awareness is not supported.')
