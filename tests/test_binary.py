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
from collections import OrderedDict
from decimal import Decimal

from pygridgain import GenericObjectMeta
from pygridgain.datatypes import (
    BinaryObject, BoolObject, IntObject, DecimalObject, LongObject, String, ByteObject, ShortObject, FloatObject,
    DoubleObject, CharObject, UUIDObject, DateObject, TimestampObject, TimeObject, EnumObject, BinaryEnumObject,
    ByteArrayObject, ShortArrayObject, IntArrayObject, LongArrayObject, FloatArrayObject, DoubleArrayObject,
    CharArrayObject, BoolArrayObject, UUIDArrayObject, DateArrayObject, TimestampArrayObject, TimeArrayObject,
    EnumArrayObject, StringArrayObject, DecimalArrayObject, ObjectArrayObject, CollectionObject, MapObject,
    WrappedDataObject,
)
from pygridgain.datatypes.prop_codes import *


insert_data = [
    [1, True, 'asdf', 42, Decimal('2.4')],
    [2, False, 'zxcvb', 43, Decimal('2.5')],
    [3, True, 'qwerty', 44, Decimal('2.6')],
]

page_size = 100

scheme_name = 'PUBLIC'

table_sql_name = 'AllDataType'
table_cache_name = 'SQL_{}_{}'.format(
    scheme_name,
    table_sql_name.upper(),
)

create_query = '''
CREATE TABLE {} (
  test_pk INTEGER(11) PRIMARY KEY,
  test_bool BOOLEAN,
  test_str VARCHAR(24),
  test_int INTEGER(11),
  test_decimal DECIMAL(11, 5),
)
'''.format(table_sql_name)

insert_query = '''
INSERT INTO {} (
  test_pk, test_bool, test_str, test_int, test_decimal, 
) VALUES (?, ?, ?, ?, ?)'''.format(table_sql_name)

select_query = '''SELECT * FROM {}'''.format(table_sql_name)

drop_query = 'DROP TABLE {} IF EXISTS'.format(table_sql_name)


def test_sql_read_as_binary(client):

    client.sql(drop_query)

    # create table
    client.sql(create_query)

    # insert some rows
    for line in insert_data:
        client.sql(insert_query, query_args=line)

    table_cache = client.get_cache(table_cache_name)
    result = table_cache.scan()

    # convert Binary object fields' values to a tuple
    # to compare it with the initial data
    for key, value in result:
        assert key in {x[0] for x in insert_data}
        assert (
                   value.TEST_BOOL,
                   value.TEST_STR,
                   value.TEST_INT,
                   value.TEST_DECIMAL
               ) in {tuple(x[1:]) for x in insert_data}

    client.sql(drop_query)


def test_sql_write_as_binary(client):

    client.get_or_create_cache(scheme_name)

    # configure cache as an SQL table
    type_name = table_cache_name

    # register binary type
    class AllDataType(
        metaclass=GenericObjectMeta,
        type_name=type_name,
        schema=OrderedDict([
            ('TEST_BOOL', BoolObject),
            ('TEST_STR', String),
            ('TEST_INT', IntObject),
            ('TEST_DECIMAL', DecimalObject),
        ]),
    ):
        pass

    table_cache = client.get_or_create_cache({
        PROP_NAME: table_cache_name,
        PROP_SQL_SCHEMA: scheme_name,
        PROP_QUERY_ENTITIES: [
            {
                'table_name': table_sql_name.upper(),
                'key_field_name': 'TEST_PK',
                'key_type_name': 'java.lang.Integer',
                'field_name_aliases': [],
                'query_fields': [
                    {
                        'name': 'TEST_PK',
                        'type_name': 'java.lang.Integer',
                        'is_notnull_constraint_field': True,
                    },
                    {
                        'name': 'TEST_BOOL',
                        'type_name': 'java.lang.Boolean',
                    },
                    {
                        'name': 'TEST_STR',
                        'type_name': 'java.lang.String',
                    },
                    {
                        'name': 'TEST_INT',
                        'type_name': 'java.lang.Integer',
                    },
                    {
                        'name': 'TEST_DECIMAL',
                        'type_name': 'java.math.BigDecimal',
                        'default_value': Decimal('0.00'),
                        'precision': 11,
                        'scale': 2,
                    },
                ],
                'query_indexes': [],
                'value_type_name': type_name,
                'value_field_name': None,
            },
        ],
    })
    table_settings = table_cache.settings
    assert table_settings, 'SQL table cache settings are empty'

    # insert rows as k-v
    for row in insert_data:
        value = AllDataType()
        (
            value.TEST_BOOL,
            value.TEST_STR,
            value.TEST_INT,
            value.TEST_DECIMAL,
        ) = row[1:]
        table_cache.put(row[0], value, key_hint=IntObject)

    data = table_cache.scan()
    assert len(list(data)) == len(insert_data), (
        'Not all data was read as key-value'
    )

    # read rows as SQL
    data = client.sql(select_query, include_field_names=True)

    header_row = next(data)
    for field_name in AllDataType.schema.keys():
        assert field_name in header_row, 'Not all field names in header row'

    data = list(data)
    assert len(data) == len(insert_data), 'Not all data was read as SQL rows'

    # cleanup
    table_cache.destroy()


def test_nested_binary_objects(client):

    nested_cache = client.get_or_create_cache('nested_binary')

    class InnerType(
        metaclass=GenericObjectMeta,
        schema=OrderedDict([
            ('inner_int', LongObject),
            ('inner_str', String),
        ]),
    ):
        pass

    class OuterType(
        metaclass=GenericObjectMeta,
        schema=OrderedDict([
            ('outer_int', LongObject),
            ('nested_binary', BinaryObject),
            ('outer_str', String),
        ]),
    ):
        pass

    inner = InnerType(inner_int=42, inner_str='This is a test string')

    outer = OuterType(
        outer_int=43,
        nested_binary=inner,
        outer_str='This is another test string'
    )

    nested_cache.put(1, outer)

    result = nested_cache.get(1)
    assert result.outer_int == 43
    assert result.outer_str == 'This is another test string'
    assert result.nested_binary.inner_int == 42
    assert result.nested_binary.inner_str == 'This is a test string'

    nested_cache.destroy()


def test_add_schema_to_binary_object(client):

    migrate_cache = client.get_or_create_cache('migrate_binary')

    class MyBinaryType(
        metaclass=GenericObjectMeta,
        schema=OrderedDict([
            ('test_str', String),
            ('test_int', LongObject),
            ('test_bool', BoolObject),
        ]),
    ):
        pass

    binary_object = MyBinaryType(
        test_str='Test string',
        test_int=42,
        test_bool=True,
    )
    migrate_cache.put(1, binary_object)

    result = migrate_cache.get(1)
    assert result.test_str == 'Test string'
    assert result.test_int == 42
    assert result.test_bool is True

    modified_schema = MyBinaryType.schema.copy()
    modified_schema['test_decimal'] = DecimalObject
    del modified_schema['test_bool']

    class MyBinaryTypeV2(
        metaclass=GenericObjectMeta,
        type_name='MyBinaryType',
        schema=modified_schema,
    ):
        pass

    assert MyBinaryType.type_id == MyBinaryTypeV2.type_id
    assert MyBinaryType.schema_id != MyBinaryTypeV2.schema_id

    binary_object_v2 = MyBinaryTypeV2(
        test_str='Another test',
        test_int=43,
        test_decimal=Decimal('2.34')
    )

    migrate_cache.put(2, binary_object_v2)

    result = migrate_cache.get(2)
    assert result.test_str == 'Another test'
    assert result.test_int == 43
    assert result.test_decimal == Decimal('2.34')
    assert not hasattr(result, 'test_bool')

    migrate_cache.destroy()


def test_complex_object_names(client):
    """
    Test the ability to work with Complex types, which names contains symbols
    not suitable for use in Python identifiers.
    """
    type_name = 'Non.Pythonic#type-name$'
    key = 'key'
    data = 'test'

    class NonPythonicallyNamedType(
        metaclass=GenericObjectMeta,
        type_name=type_name,
        schema=OrderedDict([
            ('field', String),
        ])
    ):
        pass

    cache = client.get_or_create_cache('test_name_cache')
    cache.put(key, NonPythonicallyNamedType(field=data))

    obj = cache.get(key)
    assert obj.type_name == type_name, 'Complex type name mismatch'
    assert obj.field == data, 'Complex object data failure'


def test_complex_object_hash(client):
    """
    Test that Python client correctly calculates hash of the binary object that
    contains negative bytes.
    """
    class Internal(
        metaclass=GenericObjectMeta,
        type_name='Internal',
        schema=OrderedDict([
            ('id', IntObject),
            ('str', String),
        ])
    ):
        pass

    class TestObject(
        metaclass=GenericObjectMeta,
        type_name='TestObject',
        schema=OrderedDict([
            ('id', IntObject),
            ('str', String),
            ('internal', BinaryObject),
        ])
    ):
        pass

    obj_ascii = TestObject()
    obj_ascii.id = 1
    obj_ascii.str = 'test_string'

    obj_ascii.internal = Internal()
    obj_ascii.internal.id = 2
    obj_ascii.internal.str = 'lorem ipsum'

    hash_ascii = BinaryObject.hashcode(obj_ascii, client=client)

    assert hash_ascii == -1314567146, 'Invalid hashcode value for object with ASCII strings'

    obj_utf8 = TestObject()
    obj_utf8.id = 1
    obj_utf8.str = 'юникод'

    obj_utf8.internal = Internal()
    obj_utf8.internal.id = 2
    obj_utf8.internal.str = 'ユニコード'

    hash_utf8 = BinaryObject.hashcode(obj_utf8, client=client)

    assert hash_utf8 == -1945378474, 'Invalid hashcode value for object with UTF-8 strings'


def test_complex_object_null_fields(client):
    """
    Test that Python client can correctly write and read binary object that
    contains null fields.
    """
    class AllTypesObject(
        metaclass=GenericObjectMeta,
        type_name='TestObject',
        schema=OrderedDict([
            ('byteField', ByteObject),
            ('shortField', ShortObject),
            ('intField', IntObject),
            ('longField', LongObject),
            ('floatField', FloatObject),
            ('doubleField', DoubleObject),
            ('charField', CharObject),
            ('boolField', BoolObject),
            ('uuidField', UUIDObject),
            ('dateField', DateObject),
            ('timestampField', TimestampObject),
            ('timeField', TimeObject),
            ('enumField', EnumObject),
            ('binaryEnumField', BinaryEnumObject),
            ('byteArrayField', ByteArrayObject),
            ('shortArrayField', ShortArrayObject),
            ('intArrayField', IntArrayObject),
            ('longArrayField', LongArrayObject),
            ('floatArrayField', FloatArrayObject),
            ('doubleArrayField', DoubleArrayObject),
            ('charArrayField', CharArrayObject),
            ('boolArrayField', BoolArrayObject),
            ('uuidArrayField', UUIDArrayObject),
            ('dateArrayField', DateArrayObject),
            ('timestampArrayField', TimestampArrayObject),
            ('timeArrayField', TimeArrayObject),
            ('enumArrayField', EnumArrayObject),
            ('stringField', String),
            ('stringArrayField', StringArrayObject),
            ('decimalField', DecimalObject),
            ('decimalArrayField', DecimalArrayObject),
            ('objectArrayField', ObjectArrayObject),
            ('collectionField', CollectionObject),
            ('mapField', MapObject),
            ('binaryObjectField', BinaryObject),
        ])
    ):
        pass

    key = 42
    null_fields_value = AllTypesObject()

    null_fields_value.byteField = None
    null_fields_value.shortField = None
    null_fields_value.intField = 10
    null_fields_value.longField = None
    null_fields_value.floatField = None
    null_fields_value.doubleField = None
    null_fields_value.charField = None
    null_fields_value.boolField = None
    null_fields_value.uuidField = None
    null_fields_value.dateField = None
    null_fields_value.timestampField = None
    null_fields_value.timeField = None
    null_fields_value.enumField = None
    null_fields_value.binaryEnumField = None
    null_fields_value.byteArrayField = None
    null_fields_value.shortArrayField = None
    null_fields_value.intArrayField = None
    null_fields_value.longArrayField = None
    null_fields_value.floatArrayField = None
    null_fields_value.doubleArrayField = None
    null_fields_value.charArrayField = None
    null_fields_value.boolArrayField = None
    null_fields_value.uuidArrayField = None
    null_fields_value.dateArrayField = None
    null_fields_value.timestampArrayField = None
    null_fields_value.timeArrayField = None
    null_fields_value.enumArrayField = None
    null_fields_value.stringField = None
    null_fields_value.stringArrayField = None
    null_fields_value.decimalField = None
    null_fields_value.decimalArrayField = None
    null_fields_value.objectArrayField = None
    null_fields_value.collectionField = None
    null_fields_value.mapField = None
    null_fields_value.binaryObjectField = None

    cache = client.get_or_create_cache('all_types_test_cache')
    cache.put(key, null_fields_value)

    got_obj = cache.get(key)

    assert got_obj == null_fields_value, 'Objects mismatch'
