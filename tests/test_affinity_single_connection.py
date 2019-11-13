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
    cache.clear_key(key)
    res = cache.get_and_put_if_absent(key, key)
    res2 = cache.get_and_put_if_absent(key, key2)
    assert res is None
    assert res2 == key
    assert cache.get(key) == key

    # PutIfAbsent
    cache.clear_key(key)
    res = cache.put_if_absent(key, key)
    res2 = cache.put_if_absent(key, key2)
    assert res
    assert not res2
    assert cache.get(key) == key

    # GetAndRemove
    cache.put(key, key)
    res = cache.get_and_remove(key)
    assert res == key
    assert cache.get(key) is None

    # GetAndReplace
    cache.put(key, key)
    res = cache.get_and_replace(key, key2)
    assert res == key
    assert cache.get(key) == key2

    # RemoveKey
    cache.put(key, key)
    cache.remove_key(key)
    assert cache.get(key) is None

    # RemoveIfEquals
    cache.put(key, key)
    res = cache.remove_if_equals(key, key2)
    res2 = cache.remove_if_equals(key, key)
    assert not res
    assert res2
    assert cache.get(key) is None

    # Replace
    cache.put(key, key)
    cache.replace(key, key2)
    assert cache.get(key) == key2

    # ReplaceIfEquals
    cache.put(key, key)
    res = cache.replace_if_equals(key, key2, key2)
    res2 = cache.replace_if_equals(key, key, key2)
    assert not res
    assert res2
    assert cache.get(key) == key2