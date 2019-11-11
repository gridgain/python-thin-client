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
from tests.util import *


def test_cache_get_primitive_key_routes_request_to_primary_node(client):
    cache_1 = client.get_or_create_cache('test_cache_1')
    cache_1.put(1, 1)
    time.sleep(1)
    grid_idx = get_request_grid_idx("Put")
    assert grid_idx == 2
