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
import datetime
import decimal
import uuid
from collections.abc import Mapping
from typing import Any, Dict, Optional, Union, List

from pygridgain.connection import AioConnection, Connection
from pygridgain.constants import MAX_INT, MAX_LONG, MIN_INT, MIN_LONG, PROTOCOL_BYTE_ORDER
from pygridgain.datatypes import AnyDataArray, AnyDataObject, Bool, Byte, Int, Long, Map, Null, String, StructArray, \
    FloatArrayObject, DecimalObject, TimestampObject
from pygridgain.datatypes import Float as PyFloat
from pygridgain.datatypes.sql import StatementType
from pygridgain.datatypes.type_codes import TC_DECIMAL
from pygridgain.exceptions import NotSupportedByClusterError
from pygridgain.queries import Query, query_perform
from pygridgain.queries.response import VectorResponse
from pygridgain.queries.op_codes import (
    OP_QUERY_SCAN, OP_QUERY_SCAN_CURSOR_GET_PAGE, OP_QUERY_SQL, OP_QUERY_SQL_CURSOR_GET_PAGE, OP_QUERY_SQL_FIELDS,
    OP_QUERY_SQL_FIELDS_CURSOR_GET_PAGE, OP_RESOURCE_CLOSE, OP_QUERY_VECTOR, OP_QUERY_VECTOR_CURSOR_GET_PAGE
)
from pygridgain.utils import deprecated
from .result import APIResult
from ..queries.cache_info import CacheInfo
from ..queries.response import SQLResponse

#: Vector query flag: append the engine similarity score to every result row.
#: Scores are raw engine (Lucene) values: similarity-function-dependent and not normalized.
VECTOR_FLAG_WITH_SCORES = 1

#: Vector query flag: omit value objects from result rows (keys, and optionally scores, only).
VECTOR_FLAG_NOCONTENT = 2

#: The value types a vector query field filter accepts. Exact types, the way the client's own
#: type mapping (AnyDataObject) matches them, so every value that passes is written as the
#: matching GridGain object.
VECTOR_FILTER_VALUE_TYPES = (str, int, float, bool, decimal.Decimal, uuid.UUID, datetime.datetime, datetime.date)

#: The nanoseconds a Timestamp keeps beside its milliseconds: GridGain stores millis + nanos.
MAX_TIMESTAMP_NANOS = 999_999


def validate_vector_params(field_filter: Optional[Dict[str, Any]], oversample: int) -> Optional[Dict[str, Any]]:
    """
    Checks the vector query field filter and oversample by the rules the server applies, so
    that a bad filter fails before anything is sent.

    :param field_filter: map of field name to the value the field must equal, or None,
    :param oversample: oversample, a non-negative int,
    :return: a copy of the filter, or None when the filter is None or empty.
    """
    if isinstance(oversample, bool) or not isinstance(oversample, int) or oversample < 0:
        raise ValueError(f'oversample must be a non-negative int, got {oversample!r}')
    if oversample > MAX_INT:
        raise ValueError(f'oversample must fit a 32-bit int, got {oversample}')

    if field_filter is None:
        return None
    if not isinstance(field_filter, Mapping):
        raise ValueError(f'field_filter must be a dict of field name to value, got {type(field_filter).__name__}')

    for name, value in field_filter.items():
        if not isinstance(name, str) or not name:
            raise ValueError(f'field_filter: a field name must be a non-empty string, got {name!r}')
        if value is None:
            raise ValueError(f'field_filter[{name!r}]: the value must not be None')
        if type(value) is tuple:
            # The client's own Timestamp form. A java.sql.Timestamp field only matches a Timestamp
            # value: a datetime goes out as a java.util.Date, whose text form never equals it.
            if (len(value) != 2 or type(value[0]) is not datetime.datetime or type(value[1]) is not int
                    or not 0 <= value[1] <= MAX_TIMESTAMP_NANOS):
                raise ValueError(f'field_filter[{name!r}]: a tuple value must be (datetime, nanos) with nanos '
                                 f'in 0..{MAX_TIMESTAMP_NANOS}, the Timestamp form, got {value!r}')
            continue
        if type(value) not in VECTOR_FILTER_VALUE_TYPES:
            raise ValueError(f'field_filter[{name!r}]: a {type(value).__name__} value is not supported, '
                             f'use str, int, float, bool, Decimal, UUID, datetime, date or (datetime, nanos)')
        if type(value) is int and not MIN_LONG <= value <= MAX_LONG:
            raise ValueError(f'field_filter[{name!r}]: {value} does not fit a 64-bit long')
        if type(value) is decimal.Decimal:
            if not value.is_finite():
                raise ValueError(f'field_filter[{name!r}]: {value} is not a finite Decimal')
            scale = -value.as_tuple().exponent
            if not MIN_INT <= scale <= MAX_INT:
                raise ValueError(f'field_filter[{name!r}]: {value} has scale {scale}, which does not fit '
                                 f'the 32-bit scale of a Java BigDecimal')

    return dict(field_filter) if field_filter else None


class VectorFilterValue:
    """
    Writes a vector query field filter value: a Decimal as a Java BigDecimal with the same
    unscaled value and scale, a (datetime, nanos) tuple as a Timestamp, everything else by
    AnyDataObject.

    The filter is a set of exact-value tests, so a Decimal must reach the server as the caller
    wrote it. DecimalObject normalizes first: 12.50 would go out as 12.5 and 100 as 1E+2, and
    under the active decimal context a valid value can even round or underflow to 0.

    The server tests text forms, which limits date and time precision. A datetime or date goes
    out as a java.util.Date, and its text form has whole seconds only: two values in the same
    second match the same rows, and the milliseconds are lost. A (datetime, nanos) Timestamp
    keeps its fraction.
    """

    @classmethod
    def from_python(cls, stream, value):
        if type(value) is decimal.Decimal:
            cls.__write_decimal(stream, value)
        elif type(value) is tuple:
            TimestampObject.from_python(stream, value)
        else:
            AnyDataObject.from_python(stream, value)

    @classmethod
    async def from_python_async(cls, stream, value):
        if type(value) is decimal.Decimal:
            cls.__write_decimal(stream, value)
        elif type(value) is tuple:
            await TimestampObject.from_python_async(stream, value)
        else:
            await AnyDataObject.from_python_async(stream, value)

    @staticmethod
    def __write_decimal(stream, value: decimal.Decimal):
        # Exact and context-free: the digits and exponent as given, no normalize(), no rounding.
        sign, digits, exponent = value.as_tuple()
        magnitude = int(decimal.Decimal((0, digits, 0)))
        # What Java writes for a BigDecimal: the scale, then the big-endian magnitude with room
        # for a sign bit, set for a negative value. Java has no negative zero.
        data = bytearray(magnitude.to_bytes(magnitude.bit_length() // 8 + 1, byteorder='big'))
        if sign and magnitude:
            data[0] |= 0x80

        data_object = DecimalObject.build_c_type(len(data))()
        data_object.type_code = int.from_bytes(TC_DECIMAL, byteorder=PROTOCOL_BYTE_ORDER)
        data_object.scale = -exponent
        data_object.length = len(data)
        data_object.data[:] = data
        stream.write(data_object)


def scan(conn: 'Connection', cache_info: CacheInfo, page_size: int, partitions: int = -1,
         local: bool = False) -> APIResult:
    """
    Performs scan query.

    :param conn: connection to GridGain server,
    :param cache_info: cache meta info.
    :param page_size: cursor page size,
    :param partitions: (optional) number of partitions to query
     (negative to query entire cache),
    :param local: (optional) pass True if this query should be executed
     on local node only. Defaults to False,
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `cursor`: int, cursor ID,
     * `data`: dict, result rows as key-value pairs,
     * `more`: bool, True if more data is available for subsequent
       ‘scan_cursor_get_page’ calls.
    """
    return __scan(conn, cache_info, page_size, partitions, local)


async def scan_async(conn: 'AioConnection', cache_info: CacheInfo, page_size: int, partitions: int = -1,
                     local: bool = False) -> APIResult:
    """
    Async version of scan.
    """
    return await __scan(conn, cache_info, page_size, partitions, local)


def __query_result_post_process(result):
    if result.status == 0:
        result.value = dict(result.value)
    return result


def __scan(conn, cache_info, page_size, partitions, local):
    query_struct = Query(
        OP_QUERY_SCAN,
        [
            ('cache_info', CacheInfo),
            ('filter', Null),
            ('page_size', Int),
            ('partitions', Int),
            ('local', Bool),
        ]
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cache_info': cache_info,
            'filter': None,
            'page_size': page_size,
            'partitions': partitions,
            'local': 1 if local else 0,
        },
        response_config=[
            ('cursor', Long),
            ('data', Map),
            ('more', Bool),
        ],
        post_process_fun=__query_result_post_process
    )


def scan_cursor_get_page(conn: 'Connection', cursor: int) -> APIResult:
    """
    Fetches the next scan query cursor page by cursor ID that is obtained
    from `scan` function.

    :param conn: connection to GridGain server,
    :param cursor: cursor ID,
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `data`: dict, result rows as key-value pairs,
     * `more`: bool, True if more data is available for subsequent
       ‘scan_cursor_get_page’ calls.
    """
    return __scan_cursor_get_page(conn, cursor)


async def scan_cursor_get_page_async(conn: 'AioConnection', cursor: int) -> APIResult:
    return await __scan_cursor_get_page(conn, cursor)


def __scan_cursor_get_page(conn, cursor):
    query_struct = Query(
        OP_QUERY_SCAN_CURSOR_GET_PAGE,
        [
            ('cursor', Long),
        ]
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cursor': cursor,
        },
        response_config=[
            ('data', Map),
            ('more', Bool),
        ],
        post_process_fun=__query_result_post_process
    )


@deprecated(version='1.2.0', reason="This API is deprecated and will be removed in the following major release. "
                                    "Use sql_fields instead")
def sql(
    conn: 'Connection', cache_info: CacheInfo,
    table_name: str, query_str: str, page_size: int, query_args=None,
    distributed_joins: bool = False, replicated_only: bool = False,
    local: bool = False, timeout: int = 0
) -> APIResult:
    """
    Executes an SQL query over data stored in the cluster. The query returns
    the whole record (key and value).

    :param conn: connection to GridGain server,
    :param cache_info: Cache meta info,
    :param table_name: name of a type or SQL table,
    :param query_str: SQL query string,
    :param page_size: cursor page size,
    :param query_args: (optional) query arguments,
    :param distributed_joins: (optional) distributed joins. Defaults to False,
    :param replicated_only: (optional) whether query contains only replicated
     tables or not. Defaults to False,
    :param local: (optional) pass True if this query should be executed
     on local node only. Defaults to False,
    :param timeout: (optional) non-negative timeout value in ms. Zero disables
     timeout (default),
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `cursor`: int, cursor ID,
     * `data`: dict, result rows as key-value pairs,
     * `more`: bool, True if more data is available for subsequent
       ‘sql_get_page’ calls.
    """

    if query_args is None:
        query_args = []

    query_struct = Query(
        OP_QUERY_SQL,
        [
            ('cache_info', CacheInfo),
            ('table_name', String),
            ('query_str', String),
            ('query_args', AnyDataArray()),
            ('distributed_joins', Bool),
            ('local', Bool),
            ('replicated_only', Bool),
            ('page_size', Int),
            ('timeout', Long),
        ]
    )
    result = query_struct.perform(
        conn,
        query_params={
            'cache_info': cache_info,
            'table_name': table_name,
            'query_str': query_str,
            'query_args': query_args,
            'distributed_joins': 1 if distributed_joins else 0,
            'local': 1 if local else 0,
            'replicated_only': 1 if replicated_only else 0,
            'page_size': page_size,
            'timeout': timeout,
        },
        response_config=[
            ('cursor', Long),
            ('data', Map),
            ('more', Bool),
        ],
    )
    if result.status == 0:
        result.value = dict(result.value)
    return result


@deprecated(version='1.2.0', reason="This API is deprecated and will be removed in the following major release. "
                                    "Use sql_fields instead")
def sql_cursor_get_page(conn: 'Connection', cursor: int) -> APIResult:
    """
    Retrieves the next SQL query cursor page by cursor ID from `sql`.

    :param conn: connection to GridGain server,
    :param cursor: cursor ID,
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `data`: dict, result rows as key-value pairs,
     * `more`: bool, True if more data is available for subsequent
       ‘sql_cursor_get_page’ calls.
    """

    query_struct = Query(
        OP_QUERY_SQL_CURSOR_GET_PAGE,
        [
            ('cursor', Long),
        ]
    )
    result = query_struct.perform(
        conn,
        query_params={
            'cursor': cursor,
        },
        response_config=[
            ('data', Map),
            ('more', Bool),
        ],
    )
    if result.status == 0:
        result.value = dict(result.value)
    return result


def sql_fields(
    conn: 'Connection', cache_info: CacheInfo,
    query_str: str, page_size: int, query_args=None, schema: str = None,
    statement_type: int = StatementType.ANY, distributed_joins: bool = False,
    local: bool = False, replicated_only: bool = False,
    enforce_join_order: bool = False, collocated: bool = False,
    lazy: bool = False, include_field_names: bool = False, max_rows: int = -1,
    timeout: int = 0
) -> APIResult:
    """
    Performs SQL fields query.

    :param conn: connection to GridGain server,
    :param cache_info: cache meta info.
    :param query_str: SQL query string,
    :param page_size: cursor page size,
    :param query_args: (optional) query arguments. List of values or
     (value, type hint) tuples,
    :param schema: schema for the query.
    :param statement_type: (optional) statement type. Can be:

     * StatementType.ALL − any type (default),
     * StatementType.SELECT − select,
     * StatementType.UPDATE − update.

    :param distributed_joins: (optional) distributed joins.
    :param local: (optional) pass True if this query should be executed
     on local node only.
    :param replicated_only: (optional) whether query contains only
     replicated tables or not.
    :param enforce_join_order: (optional) enforce join order.
    :param collocated: (optional) whether your data is co-located or not.
    :param lazy: (optional) lazy query execution.
    :param include_field_names: (optional) include field names in result.
    :param max_rows: (optional) query-wide maximum of rows.
    :param timeout: (optional) non-negative timeout value in ms. Zero disables
     timeout.
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `cursor`: int, cursor ID,
     * `data`: list, result values,
     * `more`: bool, True if more data is available for subsequent
       ‘sql_fields_cursor_get_page’ calls.
    """
    return __sql_fields(conn, cache_info, query_str, page_size, query_args, schema, statement_type, distributed_joins,
                        local, replicated_only, enforce_join_order, collocated, lazy, include_field_names, max_rows,
                        timeout)


async def sql_fields_async(
        conn: 'AioConnection', cache_info: CacheInfo,
        query_str: str, page_size: int, query_args=None, schema: str = None,
        statement_type: int = StatementType.ANY, distributed_joins: bool = False,
        local: bool = False, replicated_only: bool = False,
        enforce_join_order: bool = False, collocated: bool = False,
        lazy: bool = False, include_field_names: bool = False, max_rows: int = -1,
        timeout: int = 0
) -> APIResult:
    """
    Async version of sql_fields.
    """
    return await __sql_fields(conn, cache_info, query_str, page_size, query_args, schema, statement_type,
                              distributed_joins, local, replicated_only, enforce_join_order, collocated, lazy,
                              include_field_names, max_rows, timeout)


def __sql_fields(
        conn, cache_info, query_str, page_size, query_args, schema, statement_type, distributed_joins, local,
        replicated_only, enforce_join_order, collocated, lazy, include_field_names, max_rows, timeout
):
    if query_args is None:
        query_args = []

    query_struct = Query(
        OP_QUERY_SQL_FIELDS,
        [
            ('cache_info', CacheInfo),
            ('schema', String),
            ('page_size', Int),
            ('max_rows', Int),
            ('query_str', String),
            ('query_args', AnyDataArray()),
            ('statement_type', StatementType),
            ('distributed_joins', Bool),
            ('local', Bool),
            ('replicated_only', Bool),
            ('enforce_join_order', Bool),
            ('collocated', Bool),
            ('lazy', Bool),
            ('timeout', Long),
            ('include_field_names', Bool),
        ],
        response_type=SQLResponse
    )

    return query_perform(
        query_struct, conn,
        query_params={
            'cache_info': cache_info,
            'schema': schema,
            'page_size': page_size,
            'max_rows': max_rows,
            'query_str': query_str,
            'query_args': query_args,
            'statement_type': statement_type,
            'distributed_joins': distributed_joins,
            'local': local,
            'replicated_only': replicated_only,
            'enforce_join_order': enforce_join_order,
            'collocated': collocated,
            'lazy': lazy,
            'timeout': timeout,
            'include_field_names': include_field_names,
        },
        include_field_names=include_field_names,
        has_cursor=True,
    )


def sql_fields_cursor_get_page(conn: 'Connection', cursor: int, field_count: int) -> APIResult:
    """
    Retrieves the next query result page by cursor ID from `sql_fields`.

    :param conn: connection to GridGain server,
    :param cursor: cursor ID,
    :param field_count: a number of fields in a row,
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `data`: list, result values,
     * `more`: bool, True if more data is available for subsequent
       ‘sql_fields_cursor_get_page’ calls.
    """
    return __sql_fields_cursor_get_page(conn, cursor, field_count)


async def sql_fields_cursor_get_page_async(conn: 'AioConnection', cursor: int, field_count: int) -> APIResult:
    """
    Async version sql_fields_cursor_get_page.
    """
    return await __sql_fields_cursor_get_page(conn, cursor, field_count)


def __sql_fields_cursor_get_page(conn, cursor, field_count):
    query_struct = Query(
        OP_QUERY_SQL_FIELDS_CURSOR_GET_PAGE,
        [
            ('cursor', Long),
        ]
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cursor': cursor,
        },
        response_config=[
            ('data', StructArray([(f'field_{i}', AnyDataObject) for i in range(field_count)])),
            ('more', Bool),
        ],
        post_process_fun=__post_process_sql_fields_cursor
    )


def __post_process_sql_fields_cursor(result):
    if result.status != 0:
        return result

    value = result.value
    result.value = {
        'data': [],
        'more': value['more']
    }
    for row_dict in value['data']:
        result.value['data'].append(list(row_dict.values()))
    return result


def vector(conn: 'Connection', cache_info: CacheInfo, page_size: int,
           type_name: str, field: str, clause_vector: List[float], k: int, threshold: float,
           ef_search: int = 0, query_flags: int = 0, field_filter: Optional[Dict[str, Any]] = None,
           oversample: int = 0) -> APIResult:
    """
    Performs vector query.
    Vector queries based on Apache Lucene engine.

    :param conn: connection to GridGain server,
    :param cache_info: cache meta info.
    :param page_size: cursor page size.
    :param type_name: Name of the type.
    :param field: Name of the field.
    :param clause_vector: Search vector.
    :param k: [K]NN, how many vectors to return.
    :param threshold: similarity threshold, non-positive values disable it.
    :param ef_search: (optional) search beam width, 0 or negative means the engine default.
     Requires the QUERY_VECTOR_EXTENDED cluster feature.
    :param query_flags: (optional) combination of VECTOR_FLAG_WITH_SCORES and VECTOR_FLAG_NOCONTENT.
     Requires the QUERY_VECTOR_EXTENDED cluster feature.
    :param field_filter: (optional) map of field name to value, applied before the k nearest
     are chosen: a conjunction of exact-value tests on fields of the type's text index. A
     value is a str, int, float, bool, Decimal, UUID, datetime, date or a (datetime, nanos)
     Timestamp tuple. A Decimal keeps its own scale, like a Java BigDecimal: Decimal('12.50')
     is sent as 12.50, not 12.5. A datetime or date matches at second precision only. None or
     an empty map means no filter. Requires the QUERY_VECTOR_PARAMS cluster feature.
    :param oversample: (optional) the vector query oversample, a non-negative int. 0 leaves it
     unset. Requires the QUERY_VECTOR_PARAMS cluster feature.
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `cursor`: int, cursor ID,
     * `data`: result rows as final Python values, shaped by the flags: `(key, value)` tuples
       when `query_flags` is 0, otherwise `key`, `(key, score)`, `(key, value)` or
       `(key, value, score)` per VECTOR_FLAG_NOCONTENT / VECTOR_FLAG_WITH_SCORES,
     * `more`: bool, True if more data is available for subsequent
       ‘vector_cursor_get_page’ calls.
    """
    return __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold,
                    ef_search, query_flags, field_filter, oversample)


async def vector_async(conn: 'AioConnection', cache_info: CacheInfo, page_size: int,
                       type_name: str, field: str, clause_vector: List[float], k: int, threshold: float,
                       ef_search: int = 0, query_flags: int = 0, field_filter: Optional[Dict[str, Any]] = None,
                       oversample: int = 0) -> APIResult:
    """
    Async version of vector.
    """
    return await __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold,
                          ef_search, query_flags, field_filter, oversample)


def __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold, ef_search, query_flags,
             field_filter, oversample):
    field_filter = validate_vector_params(field_filter, oversample)

    fields = [
        ('cache_info', CacheInfo),
        ('page_size', Int),
        ('type_name', String),
        ('field', String),
        ('clause_vector', FloatArrayObject),
        ('k', Int),
        ('threshold', PyFloat),
    ]

    query_params = {
        'cache_info': cache_info,
        'page_size': page_size,
        'type_name': type_name,
        'field': field,
        'clause_vector': clause_vector,
        'k': k,
        'threshold': threshold,
    }

    if conn.protocol_context.is_query_vector_extended_supported():
        # The extended fields are mandatory on the wire once the feature is negotiated.
        fields += [
            ('ef_search', Int),
            ('query_flags', Byte),
        ]

        query_params['ef_search'] = ef_search
        query_params['query_flags'] = query_flags
    elif ef_search > 0 or query_flags:
        raise NotSupportedByClusterError('The cluster does not support extended vector queries '
                                         '(efSearch, scores, NOCONTENT) - QUERY_VECTOR_EXTENDED feature is absent.')

    if conn.protocol_context.is_query_vector_params_supported():
        # Mandatory on the wire once the feature is negotiated, like the extended fields:
        # oversample 0 and an empty filter (count 0) mean neither is set.
        fields += [
            ('oversample', Int),
            ('field_filter', StructArray([('name', String), ('value', VectorFilterValue)])),
        ]

        query_params['oversample'] = oversample
        query_params['field_filter'] = [{'name': name, 'value': value} for name, value in (field_filter or {}).items()]
    elif field_filter or oversample:
        raise NotSupportedByClusterError('The cluster does not support the vector query field filter and oversample '
                                         '- QUERY_VECTOR_PARAMS feature is absent.')

    query_struct = Query(OP_QUERY_VECTOR, fields, response_type=VectorResponse)

    # The response decodes in one pass (VectorResponse): rows leave it as final Python values,
    # already shaped the way the cursor yields them.
    return query_perform(
        query_struct, conn,
        query_params=query_params,
        with_scores=bool(query_flags & VECTOR_FLAG_WITH_SCORES),
        no_content=bool(query_flags & VECTOR_FLAG_NOCONTENT),
        legacy=not query_flags,
        has_cursor=True,
        post_process_fun=__query_result_post_process
    )


def vector_cursor_get_page(conn: 'Connection', cursor: int, query_flags: int = 0) -> APIResult:
    """
    Fetches the next vector query cursor page by cursor ID that is obtained
    from `vector` function.

    :param conn: connection to GridGain server,
    :param cursor: cursor ID,
    :param query_flags: (optional) the flags of the originating query - pages keep its row shape.
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `data`: result rows, shaped as in the `vector` function response,
     * `more`: bool, True if more data is available for subsequent
       ‘vector_cursor_get_page’ calls.
    """
    return __vector_cursor_get_page(conn, cursor, query_flags)


async def vector_cursor_get_page_async(conn: 'AioConnection', cursor: int, query_flags: int = 0) -> APIResult:
    return await __vector_cursor_get_page(conn, cursor, query_flags)


def __vector_cursor_get_page(conn, cursor, query_flags):
    query_struct = Query(
        OP_QUERY_VECTOR_CURSOR_GET_PAGE,
        [
            ('cursor', Long),
        ],
        response_type=VectorResponse,
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cursor': cursor,
        },
        with_scores=bool(query_flags & VECTOR_FLAG_WITH_SCORES),
        no_content=bool(query_flags & VECTOR_FLAG_NOCONTENT),
        legacy=not query_flags,
        has_cursor=False,
        post_process_fun=__query_result_post_process
    )


def resource_close(conn: 'Connection', cursor: int) -> APIResult:
    """
    Closes a resource, such as query cursor.

    :param conn: connection to GridGain server,
    :param cursor: cursor ID,
    :return: API result data object. Contains zero status on success,
     non-zero status and an error description otherwise.
    """
    return __resource_close(conn, cursor)


async def resource_close_async(conn: 'AioConnection', cursor: int) -> APIResult:
    return await __resource_close(conn, cursor)


def __resource_close(conn, cursor):
    query_struct = Query(
        OP_RESOURCE_CLOSE,
        [
            ('cursor', Long),
        ]
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cursor': cursor,
        }
    )
