#
# Copyright 2026 GridGain Systems, Inc. and Contributors.
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
Server-free coverage for the vector query field filter and oversample (GG-51945).

The server reads them only when QUERY_VECTOR_PARAMS (bit 43) was negotiated, right after the
QUERY_VECTOR_EXTENDED fields:

    if (QUERY_VECTOR_EXTENDED) { efSearch int; flags byte; }
    if (QUERY_VECTOR_PARAMS)   { oversample int; N int; N x (field name string, value object); }

Without the feature the request must stay byte-identical to the old one, so these tests pin
the bytes, written out by hand here, rather than the declared field list. The connection is a
stand-in on the client stubs: it records the request and answers with an empty page.
"""
import datetime
import decimal
import enum
import struct
import uuid
from unittest import mock

import pytest

from pygridgain import AioClient, Client
from pygridgain.api.sql import VECTOR_FLAG_WITH_SCORES, validate_vector_params, vector, vector_async
from pygridgain.connection import AioConnection
from pygridgain.connection.bitmask_feature import BitmaskFeature
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.datatypes import DateObject, DecimalObject, TimestampObject, UUIDObject
from pygridgain.exceptions import NotSupportedByClusterError
from pygridgain.queries.cache_info import CacheInfo
from pygridgain.queries.op_codes import OP_QUERY_VECTOR
from pygridgain.stream import BinaryStream
from pygridgain.utils import cache_id
from tests.client_stubs import AioBinaryRegistryStub, BinaryRegistryStub

# Feature flags only exist from 1.7.0; ProtocolContext drops them below that.
VERSION = (1, 7, 1)

EXTENDED = BitmaskFeature.QUERY_VECTOR_EXTENDED
PARAMS = BitmaskFeature.QUERY_VECTOR_PARAMS

CACHE_NAME = 'vec'
TYPE_NAME, FIELD, VECTOR, K, THRESHOLD = 'Doc', 'embedding', [0.5, -1.0], 5, 0.25

# StatusFlagResponseHeader (length, query id, flags), then cursor, row count 0, more = false.
EMPTY_PAGE = struct.pack('<iqh', 8 + 2 + 8 + 4 + 1, 0, 0) + struct.pack('<qib', 1, 0, 0)


def context(*features):
    """A protocol context advertising exactly the given features."""
    mask = BitmaskFeature(0)
    for feature in features:
        mask |= feature
    return ProtocolContext(VERSION, mask)


class _Client(BinaryRegistryStub):
    """The stub client, plus what a query reads off a client: no listeners, no affinity."""
    _event_listeners = None
    affinity_version = (0, 0)

    def __init__(self, protocol_context):
        super().__init__()
        self.protocol_context = protocol_context


class _AioClient(AioBinaryRegistryStub, _Client):
    pass


class _Connection:
    """Records every request and answers each with an empty vector page."""
    host, port, uuid = '127.0.0.1', 10800, None

    def __init__(self, *features):
        self.client = _Client(context(*features))
        self.sent = []

    @property
    def protocol_context(self):
        return self.client.protocol_context

    def request(self, data):
        self.sent.append(bytes(data))
        return bytearray(EMPTY_PAGE)


class _AioConnection(AioConnection):
    """An AioConnection only so that query_perform takes the async path; it opens no socket."""

    def __init__(self, *features):
        # No super().__init__(): this connection never connects, and needs none of its state.
        self.client = _AioClient(context(*features))
        self.host, self.port, self.uuid = '127.0.0.1', 10800, None
        self.sent = []

    async def request(self, query_id, data):
        self.sent.append(bytes(data))
        return bytearray(EMPTY_PAGE)


# --- the expected bytes, by hand --------------------------------------------------------

def string(value):
    data = value.encode('utf-8')
    return b'\x09' + struct.pack('<i', len(data)) + data


def base_body():
    """Everything the request carried before QUERY_VECTOR_EXTENDED: cache info to threshold."""
    return b''.join((
        struct.pack('<ib', cache_id(CACHE_NAME), 0),
        struct.pack('<i', K),  # page size
        string(TYPE_NAME),
        string(FIELD),
        b'\x10' + struct.pack('<i', len(VECTOR)) + struct.pack(f'<{len(VECTOR)}f', *VECTOR),
        struct.pack('<i', K),
        struct.pack('<f', THRESHOLD),
    ))


def extended(ef_search=0, flags=0):
    return struct.pack('<ib', ef_search, flags)


def params(oversample, *pairs):
    return struct.pack('<ii', oversample, len(pairs)) + b''.join(string(name) + value for name, value in pairs)


def body_of(request):
    """Checks the request header and returns what follows it."""
    length, op_code, _ = struct.unpack_from('<ihq', request)
    assert length == len(request) - 4
    assert op_code == OP_QUERY_VECTOR
    return request[4 + 2 + 8:]


def send(conn, ef_search=0, query_flags=0, **kwargs):
    cache_info = CacheInfo(cache_id=cache_id(CACHE_NAME), protocol_context=conn.protocol_context)
    result = vector(conn, cache_info, K, TYPE_NAME, FIELD, VECTOR, K, THRESHOLD, ef_search, query_flags, **kwargs)
    assert result.status == 0
    assert len(conn.sent) == 1
    return body_of(conn.sent[0])


async def send_async(conn, ef_search=0, query_flags=0, **kwargs):
    cache_info = CacheInfo(cache_id=cache_id(CACHE_NAME), protocol_context=conn.protocol_context)
    result = await vector_async(conn, cache_info, K, TYPE_NAME, FIELD, VECTOR, K, THRESHOLD, ef_search, query_flags,
                                **kwargs)
    assert result.status == 0
    assert len(conn.sent) == 1
    return body_of(conn.sent[0])


FILTER = {'tenant': 'acme', 'year': 2024, 'active': True, 'rank': 0.5}
FILTER_BYTES = (
    ('tenant', string('acme')),
    ('year', b'\x04' + struct.pack('<q', 2024)),
    ('active', b'\x08\x01'),
    ('rank', b'\x06' + struct.pack('<d', 0.5)),
)


# --- the feature bit itself ------------------------------------------------------------

def test_feature_bit_is_43():
    # The server side is ClientBitmaskFeature.QUERY_VECTOR_PARAMS(43).
    assert PARAMS == 1 << 43


def test_feature_is_advertised_as_supported():
    assert PARAMS in BitmaskFeature.all_supported()


@pytest.mark.parametrize(
    'features, supported',
    [((), False), ((EXTENDED,), False), ((PARAMS,), True), ((EXTENDED, PARAMS), True)],
)
def test_protocol_context_reports_the_feature(features, supported):
    assert bool(context(*features).is_query_vector_params_supported()) is supported


def test_feature_is_not_reported_below_1_7_0():
    stale = ProtocolContext((1, 6, 0), BitmaskFeature(0) | PARAMS)
    assert not stale.is_query_vector_params_supported()


# --- what goes on the wire -------------------------------------------------------------

@pytest.mark.parametrize('field_filter', [None, {}])
def test_without_the_feature_the_request_is_unchanged(field_filter):
    assert send(_Connection(), field_filter=field_filter) == base_body()
    assert send(_Connection(EXTENDED), field_filter=field_filter) == base_body() + extended()


def test_extended_fields_still_precede_without_the_feature():
    body = send(_Connection(EXTENDED), ef_search=64, query_flags=VECTOR_FLAG_WITH_SCORES)
    assert body == base_body() + extended(64, VECTOR_FLAG_WITH_SCORES)


@pytest.mark.parametrize('field_filter', [None, {}])
def test_with_the_feature_and_nothing_set_the_new_fields_are_zero(field_filter):
    # The fields are mandatory once negotiated: the server reads them from every request.
    body = send(_Connection(EXTENDED, PARAMS), field_filter=field_filter)
    assert body == base_body() + extended() + params(0)


def test_filter_and_oversample_follow_the_extended_fields():
    body = send(_Connection(EXTENDED, PARAMS), ef_search=64, query_flags=VECTOR_FLAG_WITH_SCORES,
                field_filter=FILTER, oversample=3)
    assert body == base_body() + extended(64, VECTOR_FLAG_WITH_SCORES) + params(3, *FILTER_BYTES)


def test_oversample_alone():
    body = send(_Connection(EXTENDED, PARAMS), oversample=2)
    assert body == base_body() + extended() + params(2)


def test_filter_keeps_the_callers_order():
    reversed_filter = dict(reversed(list(FILTER.items())))
    body = send(_Connection(EXTENDED, PARAMS), field_filter=reversed_filter)
    assert body == base_body() + extended() + params(0, *reversed(FILTER_BYTES))


@pytest.mark.parametrize('value, expected', [
    ('', string('')),
    ('ünïcødé', string('ünïcødé')),
    (-2 ** 63, b'\x04' + struct.pack('<q', -2 ** 63)),
    (2 ** 63 - 1, b'\x04' + struct.pack('<q', 2 ** 63 - 1)),
    (False, b'\x08\x00'),
    (-0.0, b'\x06' + struct.pack('<d', -0.0)),
    (uuid.UUID('12345678-1234-5678-1234-567812345678'),
     # Java UUID: most then least significant long, each little-endian.
     b'\x0a' + bytes.fromhex('7856341278563412') + bytes.fromhex('7856341278563412')),
])
def test_scalar_values_are_written_as_binary_objects(value, expected):
    body = send(_Connection(EXTENDED, PARAMS), field_filter={'f': value})
    assert body == base_body() + extended() + params(0, ('f', expected))


def _typed(writer, value):
    with BinaryStream(None) as stream:
        writer.from_python(stream, value)
        return stream.getvalue()


@pytest.mark.parametrize('value, writer, type_code', [
    (uuid.UUID('12345678-1234-5678-1234-567812345678'), UUIDObject, b'\x0a'),
    (datetime.datetime(2024, 5, 17, 10, 30, 15), DateObject, b'\x0b'),
    (datetime.date(2024, 5, 17), DateObject, b'\x0b'),
    ((datetime.datetime(2024, 5, 17, 10, 30, 15), 123), TimestampObject, b'\x21'),
])
def test_other_values_are_written_by_the_clients_own_writers(value, writer, type_code):
    expected = _typed(writer, value)
    assert expected[:1] == type_code
    body = send(_Connection(EXTENDED, PARAMS), field_filter={'f': value})
    assert body == base_body() + extended() + params(0, ('f', expected))


def java_decimal(scale, magnitude):
    """What Java writes for a BigDecimal: scale, then the big-endian magnitude, sign in the top bit."""
    data = bytes.fromhex(magnitude)
    return b'\x1e' + struct.pack('<ii', scale, len(data)) + data


# A filter is an exact-value test, so a Decimal keeps its own scale, as new BigDecimal(text) does.
DECIMAL_CASES = [
    ('12.50', java_decimal(2, '04e2')),
    ('-12.50', java_decimal(2, '84e2')),
    ('12.5', java_decimal(1, '7d')),
    ('100', java_decimal(0, '64')),
    ('1E+2', java_decimal(-2, '01')),
    ('0', java_decimal(0, '00')),
    ('0.00', java_decimal(2, '00')),
    ('-0', java_decimal(0, '00')),  # Java has no negative zero
    ('128', java_decimal(0, '0080')),  # a leading zero byte keeps the sign bit clear
    ('-128', java_decimal(0, '8080')),
    # More digits than the default context's 28: normalize() would round this one.
    ('1234567890123456789012345678901234567890.5', java_decimal(1, '2447db449988978536bf5bbbe40e766c39')),
    # The ends of the 32-bit scale: normalize() underflows the first to 0 and overflows the last.
    ('1E-2147483647', java_decimal(2 ** 31 - 1, '01')),
    ('1E+2147483647', java_decimal(-2 ** 31 + 1, '01')),
    ('1E+2147483648', java_decimal(-2 ** 31, '01')),
]


@pytest.mark.parametrize('text, expected', DECIMAL_CASES, ids=[text for text, _ in DECIMAL_CASES])
def test_decimal_values_keep_their_own_scale(text, expected):
    body = send(_Connection(EXTENDED, PARAMS), field_filter={'price': decimal.Decimal(text)})
    assert body == base_body() + extended() + params(0, ('price', expected))


def test_decimal_values_do_not_depend_on_the_decimal_context():
    with decimal.localcontext() as ctx:
        ctx.prec, ctx.Emin, ctx.Emax = 2, -3, 3
        for signal in (decimal.Inexact, decimal.Rounded, decimal.Underflow, decimal.Overflow, decimal.Clamped):
            ctx.traps[signal] = True
        for text, expected in DECIMAL_CASES:
            body = send(_Connection(EXTENDED, PARAMS), field_filter={'price': decimal.Decimal(text)})
            assert body == base_body() + extended() + params(0, ('price', expected)), text


def test_the_filter_does_not_change_how_other_decimals_are_written():
    # Cache puts still normalize: only the filter needs the caller's scale.
    assert _typed(DecimalObject, decimal.Decimal('12.50')) == java_decimal(1, '7d')


# --- the error when the feature is absent ----------------------------------------------

@pytest.mark.parametrize('features', [(), (EXTENDED,)])
@pytest.mark.parametrize('kwargs', [{'field_filter': {'tenant': 'acme'}}, {'oversample': 2},
                                    {'field_filter': {'tenant': 'acme'}, 'oversample': 2}])
def test_absent_feature_is_an_error_not_a_dropped_filter(features, kwargs):
    conn = _Connection(*features)
    with pytest.raises(NotSupportedByClusterError, match='QUERY_VECTOR_PARAMS'):
        send(conn, **kwargs)
    assert conn.sent == []


def test_cache_vector_reports_the_absent_feature():
    client = Client()
    client.protocol_context = context(EXTENDED)
    conn = _Connection(EXTENDED)
    with mock.patch.object(Client, 'random_node', new_callable=mock.PropertyMock, return_value=conn):
        with pytest.raises(NotSupportedByClusterError, match='QUERY_VECTOR_PARAMS'):
            client.get_cache(CACHE_NAME).vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD,
                                                field_filter={'tenant': 'acme'})
    assert conn.sent == []


# --- validation, before anything is sent -----------------------------------------------

class _Color(enum.IntEnum):
    RED = 1


BAD_NAMES = ['', 1, None, b'tenant', ('tenant',)]

BAD_VALUES = [
    [1], (1,), {1}, frozenset({1}), {'a': 1}, b'acme', bytearray(b'acme'), object(), 1j,
    datetime.timedelta(seconds=1), datetime.time(10, 30), _Color.RED,
]

BAD_OVERSAMPLES = [-1, 1.5, '2', True, None, 2 ** 31]


@pytest.mark.parametrize('name', BAD_NAMES)
def test_field_name_must_be_a_non_empty_string(name):
    with pytest.raises(ValueError, match='non-empty string'):
        validate_vector_params({name: 'acme'}, 0)


def test_value_must_not_be_none():
    with pytest.raises(ValueError, match=r"field_filter\['tenant'\].*None"):
        validate_vector_params({'tenant': None}, 0)


@pytest.mark.parametrize('value', BAD_VALUES, ids=lambda v: type(v).__name__)
def test_value_must_be_a_scalar_of_a_supported_type(value):
    with pytest.raises(ValueError, match=r"field_filter\['tenant'\]"):
        validate_vector_params({'year': 2024, 'tenant': value}, 0)


WHEN = datetime.datetime(2024, 5, 17, 10, 30, 15)

BAD_TIMESTAMPS = [
    (WHEN,), (WHEN, 0, 0), (WHEN, -1), (WHEN, 1_000_000), (WHEN, True), (WHEN, 1.5),
    (datetime.date(2024, 5, 17), 0), ('2024-05-17', 0), (0, WHEN),
]


@pytest.mark.parametrize('value', BAD_TIMESTAMPS, ids=repr)
def test_a_tuple_must_be_the_timestamp_form(value):
    with pytest.raises(ValueError, match=r"field_filter\['ts'\].*\(datetime, nanos\)"):
        validate_vector_params({'ts': value}, 0)


@pytest.mark.parametrize('nanos', [0, 999_999])
def test_timestamp_tuple_passes(nanos):
    assert validate_vector_params({'ts': (WHEN, nanos)}, 0) == {'ts': (WHEN, nanos)}


@pytest.mark.parametrize('value', [2 ** 63, -2 ** 63 - 1])
def test_int_value_must_fit_a_long(value):
    with pytest.raises(ValueError, match=r"field_filter\['year'\].*64-bit long"):
        validate_vector_params({'year': value}, 0)


@pytest.mark.parametrize('value', [decimal.Decimal('NaN'), decimal.Decimal('Infinity')])
def test_decimal_value_must_be_finite(value):
    with pytest.raises(ValueError, match=r"field_filter\['price'\].*finite"):
        validate_vector_params({'price': value}, 0)


@pytest.mark.parametrize('value', ['1E-2147483648', '10E-2147483648', '1E+2147483649', '1E-9999999999'])
def test_decimal_scale_must_fit_an_int(value):
    # A Java BigDecimal scale is an int; this one has no BigDecimal to compare against.
    with pytest.raises(ValueError, match=r"field_filter\['price'\].*scale"):
        validate_vector_params({'price': decimal.Decimal(value)}, 0)


@pytest.mark.parametrize('value', ['1E-2147483647', '1E+2147483648'])
def test_decimal_scale_at_the_int_limits_passes(value):
    assert validate_vector_params({'price': decimal.Decimal(value)}, 0) == {'price': decimal.Decimal(value)}


@pytest.mark.parametrize('field_filter', [[('tenant', 'acme')], 'tenant', 1])
def test_filter_must_be_a_mapping(field_filter):
    with pytest.raises(ValueError, match='field_filter must be a dict'):
        validate_vector_params(field_filter, 0)


@pytest.mark.parametrize('oversample', BAD_OVERSAMPLES)
def test_oversample_must_be_a_non_negative_int(oversample):
    with pytest.raises(ValueError, match='oversample'):
        validate_vector_params(None, oversample)


@pytest.mark.parametrize('value', [
    'acme', 0, -1, 2 ** 63 - 1, 0.0, float('inf'), True, decimal.Decimal('1.5'), uuid.uuid4(),
    datetime.datetime(2024, 1, 1), datetime.date(2024, 1, 1),
])
def test_supported_values_pass(value):
    assert validate_vector_params({'f': value}, 0) == {'f': value}


def test_validation_returns_a_copy_and_none_for_no_filter():
    field_filter = {'tenant': 'acme'}
    checked = validate_vector_params(field_filter, 0)
    assert checked == field_filter and checked is not field_filter
    assert validate_vector_params(None, 0) is None
    assert validate_vector_params({}, 5) is None
    assert validate_vector_params(None, 2 ** 31 - 1) is None


@pytest.mark.parametrize('features', [(), (EXTENDED, PARAMS)])
def test_builder_validates_before_sending(features):
    conn = _Connection(*features)
    with pytest.raises(ValueError, match=r"field_filter\['tags'\]"):
        send(conn, field_filter={'tags': ['a', 'b']})
    with pytest.raises(ValueError, match='oversample'):
        send(conn, oversample=-1)
    with pytest.raises(ValueError, match=r"field_filter\['price'\].*scale"):
        send(conn, field_filter={'price': decimal.Decimal('1E+2147483649')})
    assert conn.sent == []


@pytest.mark.parametrize('kwargs, message', [
    ({'field_filter': {'': 'acme'}}, 'non-empty string'),
    ({'field_filter': {'tenant': None}}, r"field_filter\['tenant'\]"),
    ({'field_filter': {'tags': ('a', 'b')}}, r"field_filter\['tags'\]"),
    ({'oversample': -3}, 'oversample'),
])
def test_cache_vector_validates_before_connecting(kwargs, message):
    cache = Client().get_cache(CACHE_NAME)
    with mock.patch('pygridgain.cache.VectorCursor') as cursor:
        with pytest.raises(ValueError, match=message):
            cache.vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD, **kwargs)
    cursor.assert_not_called()


# --- Cache.vector() end to end ---------------------------------------------------------

def test_cache_vector_sends_the_filter():
    client = Client()
    client.protocol_context = context(EXTENDED, PARAMS)
    conn = _Connection(EXTENDED, PARAMS)
    with mock.patch.object(Client, 'random_node', new_callable=mock.PropertyMock, return_value=conn):
        rows = list(client.get_cache(CACHE_NAME).vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD,
                                                        field_filter=FILTER, oversample=3))
    assert rows == []
    assert body_of(conn.sent[0]) == base_body() + extended() + params(3, *FILTER_BYTES)


def test_cache_vector_defaults_send_no_filter():
    client = Client()
    client.protocol_context = context(EXTENDED, PARAMS)
    conn = _Connection(EXTENDED, PARAMS)
    with mock.patch.object(Client, 'random_node', new_callable=mock.PropertyMock, return_value=conn):
        client.get_cache(CACHE_NAME).vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD)
    assert body_of(conn.sent[0]) == base_body() + extended() + params(0)


# --- AioCache parity -------------------------------------------------------------------

PARITY_CASES = [
    ((), {}),
    ((EXTENDED,), {}),
    ((EXTENDED,), {'ef_search': 64, 'query_flags': VECTOR_FLAG_WITH_SCORES}),
    ((EXTENDED, PARAMS), {}),
    ((EXTENDED, PARAMS), {'field_filter': FILTER, 'oversample': 3}),
    ((EXTENDED, PARAMS), {'field_filter': {'d': decimal.Decimal('2.5'), 'u': uuid.UUID(int=7),
                                           'when': datetime.date(2024, 5, 17)}}),
    ((EXTENDED, PARAMS), {'field_filter': {'d': decimal.Decimal('-12.50'), 'e': decimal.Decimal('1E-2147483647')}}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('features, kwargs', PARITY_CASES)
async def test_async_builder_sends_the_same_bytes(features, kwargs):
    assert await send_async(_AioConnection(*features), **kwargs) == send(_Connection(*features), **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('features', [(), (EXTENDED,)])
async def test_async_builder_reports_the_absent_feature(features):
    conn = _AioConnection(*features)
    with pytest.raises(NotSupportedByClusterError, match='QUERY_VECTOR_PARAMS'):
        await send_async(conn, field_filter={'tenant': 'acme'})
    with pytest.raises(NotSupportedByClusterError, match='QUERY_VECTOR_PARAMS'):
        await send_async(conn, oversample=1)
    assert conn.sent == []


@pytest.mark.asyncio
async def test_async_builder_validates_before_sending():
    conn = _AioConnection(EXTENDED, PARAMS)
    with pytest.raises(ValueError, match=r"field_filter\['tags'\]"):
        await send_async(conn, field_filter={'tags': {'a'}})
    assert conn.sent == []


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs, message', [
    ({'field_filter': {'': 'acme'}}, 'non-empty string'),
    ({'field_filter': {'tenant': None}}, r"field_filter\['tenant'\]"),
    ({'field_filter': {'tags': ('a', 'b')}}, r"field_filter\['tags'\]"),
    ({'oversample': -3}, 'oversample'),
])
async def test_aio_cache_vector_validates_on_the_call(kwargs, message):
    # Like the k check, the error comes from vector() itself, not from entering the cursor.
    cache = await AioClient().get_cache(CACHE_NAME)
    with mock.patch('pygridgain.aio_cache.AioVectorCursor') as cursor:
        with pytest.raises(ValueError, match=message):
            cache.vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD, **kwargs)
    cursor.assert_not_called()


async def _aio_cache(*features):
    client = AioClient()
    client.protocol_context = context(*features)
    return client, await client.get_cache(CACHE_NAME)


@pytest.mark.asyncio
async def test_aio_cache_vector_sends_the_filter():
    client, cache = await _aio_cache(EXTENDED, PARAMS)
    conn = _AioConnection(EXTENDED, PARAMS)
    with mock.patch.object(AioClient, 'random_node', new=mock.AsyncMock(return_value=conn)):
        async with cache.vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD,
                                field_filter=FILTER, oversample=3) as cursor:
            assert [row async for row in cursor] == []
    assert body_of(conn.sent[0]) == base_body() + extended() + params(3, *FILTER_BYTES)


@pytest.mark.asyncio
async def test_aio_cache_vector_sends_the_filter_as_it_was_at_the_call():
    # The async cursor sends on entry; a filter changed in between must not bypass validation.
    client, cache = await _aio_cache(EXTENDED, PARAMS)
    conn = _AioConnection(EXTENDED, PARAMS)
    field_filter = dict(FILTER)
    cursor = cache.vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD, field_filter=field_filter, oversample=3)
    field_filter['tags'] = ['not', 'allowed']
    with mock.patch.object(AioClient, 'random_node', new=mock.AsyncMock(return_value=conn)):
        async with cursor:
            pass
    assert body_of(conn.sent[0]) == base_body() + extended() + params(3, *FILTER_BYTES)


@pytest.mark.asyncio
async def test_aio_cache_vector_reports_the_absent_feature_on_entry():
    client, cache = await _aio_cache(EXTENDED)
    conn = _AioConnection(EXTENDED)
    cursor = cache.vector(TYPE_NAME, FIELD, VECTOR, k=K, threshold=THRESHOLD, field_filter={'tenant': 'acme'})
    with mock.patch.object(AioClient, 'random_node', new=mock.AsyncMock(return_value=conn)):
        with pytest.raises(NotSupportedByClusterError, match='QUERY_VECTOR_PARAMS'):
            async with cursor:
                pass
    assert conn.sent == []
