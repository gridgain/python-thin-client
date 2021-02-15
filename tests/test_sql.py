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
from datetime import datetime

import pytest

from pygridgain.api import (
    sql_fields, sql_fields_cursor_get_page,
    sql, sql_cursor_get_page,
    cache_get_configuration,
)
from pygridgain.datatypes.prop_codes import *
from pygridgain.utils import entity_id
from pygridgain.binary import unwrap_binary
from tests.util import kill_process_tree

initial_data = [
        ('John', 'Doe', 5),
        ('Jane', 'Roe', 4),
        ('Joe', 'Bloggs', 4),
        ('Richard', 'Public', 3),
        ('Negidius', 'Numerius', 3),
    ]

create_query = '''CREATE TABLE Student (
    id INT(11) PRIMARY KEY,
    first_name CHAR(24),
    last_name CHAR(32),
    grade INT(11))'''

insert_query = '''INSERT INTO Student(id, first_name, last_name, grade)
VALUES (?, ?, ?, ?)'''

select_query = 'SELECT id, first_name, last_name, grade FROM Student'

drop_query = 'DROP TABLE Student IF EXISTS'

page_size = 4


def test_sql(client):

    conn = client.random_node

    # cleanup
    client.sql(drop_query)

    result = sql_fields(
        conn,
        'PUBLIC',
        create_query,
        page_size,
        include_field_names=True
    )
    assert result.status == 0, result.message

    for i, data_line in enumerate(initial_data, start=1):
        fname, lname, grade = data_line
        result = sql_fields(
            conn,
            'PUBLIC',
            insert_query,
            page_size,
            query_args=[i, fname, lname, grade],
            include_field_names=True
        )
        assert result.status == 0, result.message

    result = cache_get_configuration(conn, 'SQL_PUBLIC_STUDENT')
    assert result.status == 0, result.message

    binary_type_name = result.value[PROP_QUERY_ENTITIES][0]['value_type_name']
    result = sql(
        conn,
        'SQL_PUBLIC_STUDENT',
        binary_type_name,
        'TRUE',
        page_size
    )
    assert result.status == 0, result.message
    assert len(result.value['data']) == page_size
    assert result.value['more'] is True

    for wrapped_object in result.value['data'].values():
        data = unwrap_binary(client, wrapped_object)
        assert data.type_id == entity_id(binary_type_name)

    cursor = result.value['cursor']

    while result.value['more']:
        result = sql_cursor_get_page(conn, cursor)
        assert result.status == 0, result.message

        for wrapped_object in result.value['data'].values():
            data = unwrap_binary(client, wrapped_object)
            assert data.type_id == entity_id(binary_type_name)

    # repeat cleanup
    result = sql_fields(conn, 'PUBLIC', drop_query, page_size)
    assert result.status == 0


def test_sql_fields(client):

    conn = client.random_node

    # cleanup
    client.sql(drop_query)

    result = sql_fields(
        conn,
        'PUBLIC',
        create_query,
        page_size,
        include_field_names=True
    )
    assert result.status == 0, result.message

    for i, data_line in enumerate(initial_data, start=1):
        fname, lname, grade = data_line
        result = sql_fields(
            conn,
            'PUBLIC',
            insert_query,
            page_size,
            query_args=[i, fname, lname, grade],
            include_field_names=True
        )
        assert result.status == 0, result.message

    result = sql_fields(
        conn,
        'PUBLIC',
        select_query,
        page_size,
        include_field_names=True
    )
    assert result.status == 0
    assert len(result.value['data']) == page_size
    assert result.value['more'] is True

    cursor = result.value['cursor']

    result = sql_fields_cursor_get_page(conn, cursor, field_count=4)
    assert result.status == 0
    assert len(result.value['data']) == len(initial_data) - page_size
    assert result.value['more'] is False

    # repeat cleanup
    result = sql_fields(conn, 'PUBLIC', drop_query, page_size)
    assert result.status == 0


def test_long_multipage_query(client):
    """
    The test creates a table with 13 columns (id and 12 enumerated columns)
    and 20 records with id in range from 1 to 20. Values of enumerated columns
    are = column number * id.

    The goal is to ensure that all the values are selected in a right order.
    """

    fields = ["id", "abc", "ghi", "def", "jkl", "prs", "mno", "tuw", "zyz", "abc1", "def1", "jkl1", "prs1"]

    client.sql('DROP TABLE LongMultipageQuery IF EXISTS')

    client.sql("CREATE TABLE LongMultiPageQuery (%s, %s)" % \
               (fields[0] + " INT(11) PRIMARY KEY", ",".join(map(lambda f: f + " INT(11)", fields[1:]))))

    for id in range(1, 21):
        client.sql(
            "INSERT INTO LongMultipageQuery (%s) VALUES (%s)" % (",".join(fields), ",".join("?" * len(fields))),
            query_args=[id] + list(i * id for i in range(1, len(fields))))

    result = client.sql('SELECT * FROM LongMultipageQuery', page_size=1)
    for page in result:
        assert len(page) == len(fields)
        for field_number, value in enumerate(page[1:], start=1):
            assert value == field_number * page[0]

    client.sql(drop_query)


@pytest.mark.parametrize('timezone', ['UTC', 'GMT+5', 'GMT-3'])
def test_server_in_different_timezone(start_ignite_server, start_client, timezone):
    server = start_ignite_server(idx=4, cluster_idx=2, jvm_opts=f'-Duser.timezone={timezone}')
    try:
        client = start_client()
        client.connect('127.0.0.1', 10804)

        client.get_or_create_cache('PUBLIC')
        client.sql('create table test(key int primary key, time datetime)')

        current_time = datetime(year=2020, month=2, day=12, hour=12, minute=32, second=55)
        client.sql(f"insert into test (key, time) VALUES (1, '{current_time}')")

        page = client.sql('SELECT time FROM test')
        received = next(page)[0][0]

        assert current_time == received

        client.close()
    finally:
        kill_process_tree(server.pid)
