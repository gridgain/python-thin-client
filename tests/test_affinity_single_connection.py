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


def test_all_cache_operations_with_affinity_aware_client_on_single_server(request, client_affinity_aware_single_server):
    cache = client_affinity_aware_single_server.get_or_create_cache(request.node.name)
    key = 1
    key2 = 2

    # Put/Get
    cache.put(key, key)
    assert cache.get(key) == key

    # Replace
    res = cache.replace(key, key2)
    assert res
    assert cache.get(key) == key2

    # Clear
    cache.put(key2, key2)
    cache.clear_key(key2)
    assert cache.get(key2) is None

    # ContainsKey
    assert cache.contains_key(key)
    assert not cache.contains_key(key2)

    # GetAndPut
    cache.put(key, key)
    res = cache.get_and_put(key, key2)
    assert res == key
    assert cache.get(key) == key2

    # GetAndPutIfAbsent
    cache.get_and_put_if_absent(key, 4)

    # PutIfAbsent
    cache.put_if_absent(key, 5)

    # GetAndRemove
    cache.get_and_remove(key)

    # GetAndReplace
    cache.get_and_replace(key, 6)

    # RemoveKey
    cache.remove_key(key)

    # RemoveIfEquals
    cache.remove_if_equals(key, -1)

    # Replace
    cache.replace(key, -1)

    # ReplaceIfEquals
    cache.replace_if_equals(key, 10, -10)
