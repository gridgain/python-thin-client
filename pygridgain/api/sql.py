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
from typing import Union, List

from pygridgain.connection import AioConnection, Connection
from pygridgain.datatypes import AnyDataArray, AnyDataObject, Bool, Byte, Int, Long, Map, Null, String, StructArray, \
    FloatArrayObject
from pygridgain.datatypes import Float as PyFloat
from pygridgain.datatypes.sql import StatementType
from pygridgain.exceptions import NotSupportedByClusterError
from pygridgain.queries import Query, query_perform
from pygridgain.queries.op_codes import (
    OP_QUERY_SCAN, OP_QUERY_SCAN_CURSOR_GET_PAGE, OP_QUERY_SQL, OP_QUERY_SQL_CURSOR_GET_PAGE, OP_QUERY_SQL_FIELDS,
    OP_QUERY_SQL_FIELDS_CURSOR_GET_PAGE, OP_RESOURCE_CLOSE, OP_QUERY_VECTOR, OP_QUERY_VECTOR_CURSOR_GET_PAGE
)
from pygridgain.utils import deprecated
from .result import APIResult
from ..queries.cache_info import CacheInfo
from ..queries.response import SQLResponse

#: Vector query flag: append the engine similarity score to every result row.
VECTOR_FLAG_WITH_SCORES = 1

#: Vector query flag: omit value objects from result rows (keys, and optionally scores, only).
VECTOR_FLAG_NOCONTENT = 2


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
           ef_search: int = 0, query_flags: int = 0) -> APIResult:
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
    :return: API result data object. Contains zero status and a value
     of type dict with results on success, non-zero status and an error
     description otherwise.

     Value dict is of following format:

     * `cursor`: int, cursor ID,
     * `data`: result rows - a dict of key-value pairs when `query_flags` is 0, otherwise
       a list of per-row dicts with `key`, optionally `value` (no VECTOR_FLAG_NOCONTENT) and
       optionally `score` (VECTOR_FLAG_WITH_SCORES) entries,
     * `more`: bool, True if more data is available for subsequent
       ‘vector_cursor_get_page’ calls.
    """
    return __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold,
                    ef_search, query_flags)


async def vector_async(conn: 'AioConnection', cache_info: CacheInfo, page_size: int,
                       type_name: str, field: str, clause_vector: List[float], k: int, threshold: float,
                       ef_search: int = 0, query_flags: int = 0) -> APIResult:
    """
    Async version of vector.
    """
    return await __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold,
                          ef_search, query_flags)


def __vector_rows_type(query_flags):
    """
    Response rows encoding: a plain key-value sequence for legacy queries, a row struct shaped
    by the flags otherwise.
    """
    if not query_flags:
        return Map

    row = [('key', AnyDataObject)]

    if not query_flags & VECTOR_FLAG_NOCONTENT:
        row.append(('value', AnyDataObject))

    if query_flags & VECTOR_FLAG_WITH_SCORES:
        row.append(('score', PyFloat))

    return StructArray(row)


def __vector(conn, cache_info, page_size, type_name, field, clause_vector, k, threshold, ef_search, query_flags):
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

    query_struct = Query(OP_QUERY_VECTOR, fields)

    return query_perform(
        query_struct, conn,
        query_params=query_params,
        response_config=[
            ('cursor', Long),
            ('data', __vector_rows_type(query_flags)),
            ('more', Bool),
        ],
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
        ]
    )
    return query_perform(
        query_struct, conn,
        query_params={
            'cursor': cursor,
        },
        response_config=[
            ('data', __vector_rows_type(query_flags)),
            ('more', Bool),
        ],
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
