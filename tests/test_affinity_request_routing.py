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

from tests.util import *


@pytest.mark.parametrize("key,grid_idx", [(1, 2), (2, 1), (3, 1), (4, 2), (5, 2), (6, 3)])
def test_cache_get_primitive_key_routes_request_to_primary_node(key, grid_idx, client_affinity_aware):
    cache_1 = client_affinity_aware.get_or_create_cache('test_cache_1')

    # Warm up affinity map
    cache_1.put(key, key)
    get_request_grid_idx()

    # Test
    cache_1.get(key)
    actual_grid_idx = get_request_grid_idx()
    assert actual_grid_idx == grid_idx
