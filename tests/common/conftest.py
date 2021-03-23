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


@pytest.fixture(scope='module')
def client():
    client = Client()

    client.connect('127.0.0.1', 10801)

    yield client

    client.close()


@pytest.fixture
def cache(client):
    cache_name = 'my_bucket'
    conn = client.random_node

    cache_create(conn, cache_name)
    yield cache_name
    cache_destroy(conn, cache_name)
