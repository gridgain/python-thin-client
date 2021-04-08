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
from pygridgain import Client
from pygridgain.datatypes import CharObject, ShortObject

client = Client()
with client.connect('127.0.0.1', 10800):

    my_cache = client.get_or_create_cache('my cache')

    my_cache.put('my key', 42)
    # value ‘42’ takes 9 bytes of memory as a LongObject

    my_cache.put('my key', 42, value_hint=ShortObject)
    # value ‘42’ takes only 3 bytes as a ShortObject

    my_cache.put('a', 1)
    # ‘a’ is a key of type String

    my_cache.put('a', 2, key_hint=CharObject)
    # another key ‘a’ of type CharObject was created

    value = my_cache.get('a')
    print(value)
    # 1

    value = my_cache.get('a', key_hint=CharObject)
    print(value)
    # 2

    # now let us delete both keys at once
    my_cache.remove_keys([
        'a',                # a default type key
        ('a', CharObject),  # a key of type CharObject
    ])

    my_cache.destroy()
