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
def test_cache_operation_on_primitive_key_routes_request_to_primary_node(key, grid_idx, client_affinity_aware):
    cache_1 = client_affinity_aware.get_or_create_cache('test_cache_1')

    # Warm up affinity map
    cache_1.put(key, key)
    get_request_grid_idx()

    # Test
    cache_1.get(key)
    assert get_request_grid_idx() == grid_idx

    cache_1.put(key, key)
    assert get_request_grid_idx("Put") == grid_idx

    cache_1.replace(key, key + 1)
    assert get_request_grid_idx("Replace") == grid_idx

    cache_1.clear_key(key)
    assert get_request_grid_idx("ClearKey") == grid_idx

    cache_1.contains_key(key)
    assert get_request_grid_idx("ContainsKey") == grid_idx

    cache_1.get_and_put(key, 3)
    assert get_request_grid_idx("GetAndPut") == grid_idx

    cache_1.get_and_put_if_absent(key, 4)
    assert get_request_grid_idx("GetAndPutIfAbsent") == grid_idx

    cache_1.put_if_absent(key, 5)
    assert get_request_grid_idx("PutIfAbsent") == grid_idx

    cache_1.get_and_remove(key)
    assert get_request_grid_idx("GetAndRemove") == grid_idx

    cache_1.get_and_replace(key, 6)
    assert get_request_grid_idx("GetAndReplace") == grid_idx

    cache_1.remove_key(key)
    assert get_request_grid_idx("RemoveKey") == grid_idx

    cache_1.remove_if_equals(key, -1)
    assert get_request_grid_idx("RemoveIfEquals") == grid_idx

    cache_1.replace(key, -1)
    assert get_request_grid_idx("Replace") == grid_idx

    cache_1.replace_if_equals(key, 10, -10)
    assert get_request_grid_idx("ReplaceIfEquals") == grid_idx


