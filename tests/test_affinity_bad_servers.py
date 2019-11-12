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

from pygridgain import Client
from pygridgain.exceptions import ReconnectError


def test_client_with_multiple_bad_servers():
    client = Client(affinity_aware=True)
    with pytest.raises(ReconnectError) as e_info:
        client.connect([("127.0.0.1", 10900), ("127.0.0.1", 10901)])
    assert str(e_info.value) == "Can not connect."

