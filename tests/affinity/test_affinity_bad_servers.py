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
import pytest

from pygridgain.exceptions import ReconnectError
from tests.util import start_ignite, kill_process_tree


def test_client_with_multiple_bad_servers(client_not_connected):
    with pytest.raises(ReconnectError) as e_info:
        client_not_connected.connect([("127.0.0.1", 10900), ("127.0.0.1", 10901)])
    assert str(e_info.value) == "Can not connect."


def test_client_with_failed_server(request, client_not_connected):
    srv = start_ignite(idx=4)
    try:
        client_not_connected.connect([("127.0.0.1", 10804)])
        cache = client_not_connected.get_or_create_cache(request.node.name)
        cache.put(1, 1)
        kill_process_tree(srv.pid)
        with pytest.raises(ConnectionResetError):
            cache.get(1)
    finally:
        kill_process_tree(srv.pid)


def test_client_with_recovered_server(request, client_not_connected):
    srv = start_ignite(idx=4)
    try:
        client_not_connected.connect([("127.0.0.1", 10804)])
        cache = client_not_connected.get_or_create_cache(request.node.name)
        cache.put(1, 1)

        # Kill and restart server
        kill_process_tree(srv.pid)
        srv = start_ignite(idx=4)

        # First request fails
        with pytest.raises(Exception):
            cache.put(1, 2)

        # Retry succeeds
        cache.put(1, 2)
        assert cache.get(1) == 2
    finally:
        kill_process_tree(srv.pid)
