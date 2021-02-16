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

from pygridgain.exceptions import AuthenticationError
from tests.util import kill_process_tree, clear_workdir


def test_auth_success(start_ignite_server, start_client):
    clear_workdir()

    server_id = 10
    server = start_ignite_server(idx=server_id, cluster_idx=2, enable_auth=True)
    try:
        client = start_client(username='ignite', password='ignite')
        client.connect('127.0.0.1', 10800 + server_id)
    finally:
        kill_process_tree(server.pid)


def test_auth_failure(start_ignite_server, start_client):
    clear_workdir()

    server_id = 10
    server = start_ignite_server(idx=server_id, cluster_idx=2, enable_auth=True, debug=True)
    try:
        client = start_client(username='incorrect-user-name', password='incorrect-password')
        with pytest.raises(AuthenticationError) as auth_error:
            client.connect('127.0.0.1', 10800 + server_id)
            assert auth_error.match('Handshake error: The user name or password is incorrect')
    finally:
        kill_process_tree(server.pid)
