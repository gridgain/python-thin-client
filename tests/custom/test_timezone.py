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
from datetime import datetime

import pytest

from tests.util import kill_process_tree


@pytest.mark.parametrize('timezone', ['UTC', 'GMT+5', 'GMT-3'])
def test_server_in_different_timezone(start_ignite_server, start_client, timezone):
    server_id = 10
    server = start_ignite_server(idx=server_id, jvm_opts=f'-Duser.timezone={timezone}')
    try:
        client = start_client()
        client.connect('127.0.0.1', 10800 + server_id)

        client.get_or_create_cache('PUBLIC')
        client.sql('create table test(key int primary key, time datetime)')

        current_time = datetime(year=2020, month=2, day=12, hour=12, minute=32, second=55)
        client.sql(f"insert into test (key, time) VALUES (1, '{current_time}')")

        with client.sql('SELECT time FROM test') as cursor:
            row = next(cursor)
            received = row[0][0]

        assert current_time == received

        client.close()
    finally:
        kill_process_tree(server.pid)


@pytest.mark.asyncio
@pytest.mark.parametrize('timezone', ['UTC', 'GMT+5', 'GMT-3'])
async def test_server_in_different_timezone_async(start_ignite_server, start_async_client, timezone):
    server_id = 10
    server = start_ignite_server(idx=server_id, jvm_opts=f'-Duser.timezone={timezone}')
    try:
        client = start_async_client()
        await client.connect('127.0.0.1', 10800 + server_id)

        await client.get_or_create_cache('PUBLIC')
        await client.sql('create table test(key int primary key, time datetime)')

        current_time = datetime(year=2020, month=2, day=12, hour=12, minute=32, second=55)
        await client.sql(f"insert into test (key, time) VALUES (1, '{current_time}')")

        async with client.sql('SELECT time FROM test') as cursor:
            row = await cursor.__anext__()
            received = row[0][0]

        assert current_time == received

        await client.close()
    finally:
        kill_process_tree(server.pid)
