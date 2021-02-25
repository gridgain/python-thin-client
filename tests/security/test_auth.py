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

from pygridgain.exceptions import AuthenticationError
from tests.util import start_ignite_gen, clear_ignite_work_dir, get_client

DEFAULT_IGNITE_USERNAME = 'ignite'
DEFAULT_IGNITE_PASSWORD = 'ignite'


@pytest.fixture(params=['with-ssl', 'without-ssl'])
def with_ssl(request):
    return request.param == 'with-ssl'


@pytest.fixture(autouse=True)
def server(with_ssl, cleanup):
    yield from start_ignite_gen(use_ssl=with_ssl, use_auth=True)


@pytest.fixture(scope='module', autouse=True)
def cleanup():
    clear_ignite_work_dir()
    yield None
    clear_ignite_work_dir()


def test_auth_success(with_ssl, ssl_params):
    ssl_params['use_ssl'] = with_ssl

    with get_client(username=DEFAULT_IGNITE_USERNAME, password=DEFAULT_IGNITE_PASSWORD, **ssl_params) as client:
        client.connect("127.0.0.1", 10801)

        assert all(node.alive for node in client._nodes)


@pytest.mark.parametrize(
    'username, password',
    [
        [DEFAULT_IGNITE_USERNAME, None],
        ['invalid_user', 'invalid_password'],
        [None, None]
    ]
)
def test_auth_failed(username, password, with_ssl, ssl_params):
    ssl_params['use_ssl'] = with_ssl

    with pytest.raises(AuthenticationError):
        with get_client(username=username, password=password, **ssl_params) as client:
            client.connect("127.0.0.1", 10801)
