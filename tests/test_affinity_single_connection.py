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

from tests.util import get_request_grid_idx


def test_all_cache_operations_with_affinity_aware_client_on_single_server(client_affinity_aware_single_server):
    cache = client_affinity_aware_single_server.get_or_create_cache('test_cache_1')
    key = 1

    cache.put(key, key)
    assert cache.get(key) == key

    res = cache.replace(key, key + 1)
    assert res

    cache.clear_key(key)
    assert cache.get(key) is None

    cache.contains_key(key)

    cache.get_and_put(key, 3)

    cache.get_and_put_if_absent(key, 4)

    cache.put_if_absent(key, 5)

    cache.get_and_remove(key)

    cache.get_and_replace(key, 6)

    cache.remove_key(key)

    cache.remove_if_equals(key, -1)

    cache.replace(key, -1)

    cache.replace_if_equals(key, 10, -10)
