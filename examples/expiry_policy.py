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
import asyncio
import time

from pygridgain import Client, AioClient
from pygridgain.datatypes import ExpiryPolicy
from pygridgain.datatypes.prop_codes import PROP_NAME, PROP_EXPIRY_POLICY
from pygridgain.exceptions import NotSupportedByClusterError


def main():
    print("Running sync ExpiryPolicy example.")

    client = Client()
    with client.connect('127.0.0.1', 10800):
        print("Create cache with expiry policy.")
        try:
            ttl_cache = client.create_cache({
                PROP_NAME: 'test',
                PROP_EXPIRY_POLICY: ExpiryPolicy(create=1.0)
            })
        except NotSupportedByClusterError:
            print("'ExpiryPolicy' API is not supported by cluster. Finishing...")
            return

        try:
            ttl_cache.put(1, 1)
            time.sleep(0.5)
            print(f"key = {1}, value = {ttl_cache.get(1)}")
            # key = 1, value = 1
            time.sleep(1.2)
            print(f"key = {1}, value = {ttl_cache.get(1)}")
            # key = 1, value = None
        finally:
            ttl_cache.destroy()

        print("Create simple Cache and set TTL through `with_expire_policy`")
        simple_cache = client.create_cache('test')
        try:
            ttl_cache = simple_cache.with_expire_policy(access=1.0)
            ttl_cache.put(1, 1)
            time.sleep(0.5)
            print(f"key = {1}, value = {ttl_cache.get(1)}")
            # key = 1, value = 1
            time.sleep(1.7)
            print(f"key = {1}, value = {ttl_cache.get(1)}")
            # key = 1, value = None
        finally:
            simple_cache.destroy()


async def async_main():
    print("Running async ExpiryPolicy example.")

    client = AioClient()
    async with client.connect('127.0.0.1', 10800):
        print("Create cache with expiry policy.")
        try:
            ttl_cache = await client.create_cache({
                PROP_NAME: 'test',
                PROP_EXPIRY_POLICY: ExpiryPolicy(create=1.0)
            })
        except NotSupportedByClusterError:
            print("'ExpiryPolicy' API is not supported by cluster. Finishing...")
            return

        try:
            await ttl_cache.put(1, 1)
            await asyncio.sleep(0.5)
            value = await ttl_cache.get(1)
            print(f"key = {1}, value = {value}")
            # key = 1, value = 1
            await asyncio.sleep(1.2)
            value = await ttl_cache.get(1)
            print(f"key = {1}, value = {value}")
            # key = 1, value = None
        finally:
            await ttl_cache.destroy()

        print("Create simple Cache and set TTL through `with_expire_policy`")
        simple_cache = await client.create_cache('test')
        try:
            ttl_cache = simple_cache.with_expire_policy(access=1.0)
            await ttl_cache.put(1, 1)
            await asyncio.sleep(0.5)
            value = await ttl_cache.get(1)
            print(f"key = {1}, value = {value}")
            # key = 1, value = 1
            await asyncio.sleep(1.7)
            value = await ttl_cache.get(1)
            print(f"key = {1}, value = {value}")
            # key = 1, value = None
        finally:
            await simple_cache.destroy()

if __name__ == '__main__':
    main()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(async_main())