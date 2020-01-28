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
from pygridgain import GenericObjectMeta
from pygridgain.datatypes import (
    IntObject, String
)
from collections import OrderedDict

initial_data = [
        ('Acct', 'John', 'Doe', 5),
        ('Dev', 'Jane', 'Roe', 4),
        ('Acct', 'Joe', 'Bloggs', 4),
        ('Supp', 'Richard', 'Public', 3),
        ('Acct', 'Negidius', 'Numerius', 3),
    ]

create_query = '''CREATE TABLE Student (
    id INT(11),
    dept VARCHAR,
    first_name CHAR(24),
    last_name CHAR(32),
    grade INT(11),
    PRIMARY KEY (id, dept))
    WITH "template=partitioned, backups=1, CACHE_NAME=StudentCache, KEY_TYPE=test.model.StudentKey, VALUE_TYPE=test.model.Student";'''

class StudentKey(
        metaclass=GenericObjectMeta,
        type_name='test.model.StudentKey',
        schema=OrderedDict([
            ('ID', IntObject),
            ('DEPT', String)
        ])
    ):
    pass

class Student(
        metaclass=GenericObjectMeta,
        type_name='test.model.Student',
        schema=OrderedDict([
            ('FIRST_NAME', String),
            ('LAST_NAME', String),
            ('GRADE', IntObject)
        ])
    ):
    pass

insert_query = '''INSERT INTO Student(id, dept, first_name, last_name, grade)
VALUES (?, ?, ?, ?, ?)'''

select_query = 'SELECT id, dept, first_name, last_name, grade FROM Student'

select_count_query = 'SELECT COUNT(*) FROM Student'

drop_query = 'DROP TABLE Student IF EXISTS'

def test_sql_fields(client):
    client.sql(drop_query, 1)

    result = client.sql(create_query, 1)
    assert next(result)[0] == 0

    for i, data_line in enumerate(initial_data, start=1):
        dept, fname, lname, grade = data_line
        result = client.sql(
            insert_query,
            1,
            query_args=[i, dept, fname, lname, grade]
        )
        assert next(result)[0] == 1

    client.get_binary_type("test.model.StudentKey")
    client.get_binary_type("test.model.Student")

    studentCache = client.get_cache('StudentCache')

    studentCache.put(StudentKey(1, 'Supp'), Student('Steph', 'D', 100))
    studentCache.put(StudentKey(6, 'Acct'), Student('Glenn', 'W', 4))
    studentCache.put(StudentKey(2, 'Dev'), Student('Ilya', 'K', 13))

    assert studentCache.get(StudentKey(2, 'Dev')).FIRST_NAME == "Ilya"
    assert studentCache.get(StudentKey(6, 'Acct')).LAST_NAME == "W"
    assert studentCache.get(StudentKey(1, 'Acct')).FIRST_NAME == "John"

    result = client.sql(select_count_query, 1)
    assert next(result)[0] == 7
