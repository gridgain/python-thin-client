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
from tests.util import start_ignite


@pytest.fixture(scope='module')
def start_ignite_server():
    def start(idx=1, debug=False, use_ssl=False, use_auth=False, jvm_opts=''):
        return start_ignite(
            idx=idx,
            debug=debug,
            use_ssl=use_ssl,
            use_auth=use_auth,
            jvm_opts=jvm_opts
        )

    return start


@pytest.fixture(scope='module')
def start_client():
    def start(**kwargs):
        return Client(**kwargs)

    return start


@pytest.fixture(scope='module')
def start_async_client():
    def start(**kwargs):
        return AioClient(**kwargs)

    return start
