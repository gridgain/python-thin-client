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

"""
This module contains sync and async cursors for different types of queries.
"""

import asyncio

from pygridgain.api import (
    scan, scan_cursor_get_page, resource_close, scan_async, scan_cursor_get_page_async, resource_close_async, sql,
    sql_cursor_get_page, sql_fields, sql_fields_cursor_get_page, sql_fields_cursor_get_page_async, sql_fields_async
)
from pygridgain.exceptions import CacheError, SQLError


__all__ = ['ScanCursor', 'SqlCursor', 'SqlFieldsCursor', 'AioScanCursor', 'AioSqlFieldsCursor']


class BaseCursorMixin:
    @property
    def connection(self):
        return getattr(self, '_conn', None)

    @connection.setter
    def connection(self, value):
        setattr(self, '_conn', value)

    @property
    def cursor_id(self):
        return getattr(self, '_cursor_id', None)

    @cursor_id.setter
    def cursor_id(self, value):
        setattr(self, '_cursor_id', value)

    @property
    def more(self):
        return getattr(self, '_more', None)

    @more.setter
    def more(self, value):
        setattr(self, '_more', value)

    @property
    def cache_id(self):
        return getattr(self, '_cache_id', None)

    @cache_id.setter
    def cache_id(self, value):
        setattr(self, '_cache_id', value)

    @property
    def client(self):
        return getattr(self, '_client', None)

    @client.setter
    def client(self, value):
        setattr(self, '_client', value)

    @property
    def data(self):
        return getattr(self, '_data', None)

    @data.setter
    def data(self, value):
        setattr(self, '_data', value)


class CursorMixin(BaseCursorMixin):
    def __enter__(self):
        return self

    def __iter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        if self.connection and self.cursor_id and self.more:
            resource_close(self.connection, self.cursor_id)


class AioCursorMixin(BaseCursorMixin):
    def __await__(self):
        return (yield from self.__aenter__().__await__())

    def __aiter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def close(self):
        if self.connection and self.cursor_id and self.more:
            await resource_close_async(self.connection, self.cursor_id)


class AbstractScanCursor:
    def __init__(self, client, cache_id, page_size, partitions, local):
        self.client = client
        self.cache_id = cache_id
        self._page_size = page_size
        self._partitions = partitions
        self._local = local

    def _finalize_init(self, result):
        if result.status != 0:
            raise CacheError(result.message)

        self.cursor_id, self.more = result.value['cursor'], result.value['more']
        self.data = iter(result.value['data'].items())

    def _process_page_response(self, result):
        if result.status != 0:
            raise CacheError(result.message)

        self.data, self.more = iter(result.value['data'].items()), result.value['more']


class ScanCursor(AbstractScanCursor, CursorMixin):
    def __init__(self, client, cache_id, page_size, partitions, local):
        super().__init__(client, cache_id, page_size, partitions, local)

        self.connection = self.client.random_node
        result = scan(self.connection, self.cache_id, self._page_size, self._partitions, self._local)
        self._finalize_init(result)

    def __next__(self):
        if not self.data:
            raise StopIteration

        try:
            k, v = next(self.data)
        except StopIteration:
            if self.more:
                self._process_page_response(scan_cursor_get_page(self.connection, self.cursor_id))
                k, v = next(self.data)
            else:
                raise StopIteration

        return self.client.unwrap_binary(k), self.client.unwrap_binary(v)


class AioScanCursor(AbstractScanCursor, AioCursorMixin):
    def __init__(self, client, cache_id, page_size, partitions, local):
        super().__init__(client, cache_id, page_size, partitions, local)

    async def __aenter__(self):
        if not self.connection:
            self.connection = await self.client.random_node()
            result = await scan_async(self.connection, self.cache_id, self._page_size, self._partitions, self._local)
            self._finalize_init(result)
        return self

    async def __anext__(self):
        if not self.connection:
            raise CacheError("Using uninitialized cursor, initialize it using async with expression.")

        if not self.data:
            raise StopAsyncIteration

        try:
            k, v = next(self.data)
        except StopIteration:
            if self.more:
                self._process_page_response(await scan_cursor_get_page_async(self.connection, self.cursor_id))
                try:
                    k, v = next(self.data)
                except StopIteration:
                    raise StopAsyncIteration
            else:
                raise StopAsyncIteration

        return await asyncio.gather(
            *[self.client.unwrap_binary(k), self.client.unwrap_binary(v)]
        )


class SqlCursor(CursorMixin):
    def __init__(self, client, cache_id, *args, **kwargs):
        self.client = client
        self.cache_id = cache_id
        self.connection = self.client.random_node
        result = sql(self.connection, self.cache_id, *args, **kwargs)
        if result.status != 0:
            raise SQLError(result.message)

        self.cursor_id, self.more = result.value['cursor'], result.value['more']
        self.data = iter(result.value['data'].items())

    def __next__(self):
        if not self.data:
            raise StopIteration

        try:
            k, v = next(self.data)
        except StopIteration:
            if self.more:
                result = sql_cursor_get_page(self.connection, self.cursor_id)
                if result.status != 0:
                    raise SQLError(result.message)
                self.data, self.more = iter(result.value['data'].items()), result.value['more']

                k, v = next(self.data)
            else:
                raise StopIteration

        return self.client.unwrap_binary(k), self.client.unwrap_binary(v)


class AbstractSqlFieldsCursor:
    def __init__(self, client, cache_id):
        self.client = client
        self.cache_id = cache_id

    def _finalize_init(self, result):
        if result.status != 0:
            raise SQLError(result.message)

        self.cursor_id, self.more = result.value['cursor'], result.value['more']
        self.data = iter(result.value['data'])
        self._field_names = result.value.get('fields', None)
        if self._field_names:
            self._field_count = len(self._field_names)
        else:
            self._field_count = result.value['field_count']


class SqlFieldsCursor(AbstractSqlFieldsCursor, CursorMixin):
    def __init__(self, client, cache_id, *args, **kwargs):
        super().__init__(client, cache_id)
        self.connection = self.client.random_node
        self._finalize_init(sql_fields(self.connection, self.cache_id, *args, **kwargs))

    def __next__(self):
        if not self.data:
            raise StopIteration

        if self._field_names:
            result = self._field_names
            self._field_names = None
            return result

        try:
            row = next(self.data)
        except StopIteration:
            if self.more:
                result = sql_fields_cursor_get_page(self.connection, self.cursor_id, self._field_count)
                if result.status != 0:
                    raise SQLError(result.message)

                self.data, self.more = iter(result.value['data']), result.value['more']

                row = next(self.data)
            else:
                raise StopIteration

        return [self.client.unwrap_binary(v) for v in row]


class AioSqlFieldsCursor(AbstractSqlFieldsCursor, AioCursorMixin):
    def __init__(self, client, cache_id, *args, **kwargs):
        super().__init__(client, cache_id)
        self._params = (args, kwargs)

    async def __aenter__(self):
        await self._initialize(*self._params[0], *self._params[1])
        return self

    async def __anext__(self):
        if not self.connection:
            raise SQLError("Attempting to use uninitialized aio cursor, please await on it or use with expression.")

        if not self.data:
            raise StopAsyncIteration

        if self._field_names:
            result = self._field_names
            self._field_names = None
            return result

        try:
            row = next(self.data)
        except StopIteration:
            if self.more:
                result = await sql_fields_cursor_get_page_async(self.connection, self.cursor_id, self._field_count)
                if result.status != 0:
                    raise SQLError(result.message)

                self.data, self.more = iter(result.value['data']), result.value['more']
                try:
                    row = next(self.data)
                except StopIteration:
                    raise StopAsyncIteration
            else:
                raise StopAsyncIteration

        return await asyncio.gather(*[self.client.unwrap_binary(v) for v in row])

    async def _initialize(self, *args, **kwargs):
        if self.connection and self.cursor_id:
            return

        self.connection = await self.client.random_node()
        self._finalize_init(await sql_fields_async(self.connection, self.cache_id, *args, **kwargs))
