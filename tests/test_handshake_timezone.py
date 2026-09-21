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
Tests for the `client.timezone` attribute the client sends in the handshake.

The server resolves the value with `TimeZone.getTimeZone()`, so it has to be an
IANA zone ID. An abbreviation is not one, and it falls back to GMT for anything
it does not recognise, silently shifting every timestamp of the connection.
"""
import struct
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pygridgain import Client
from pygridgain.connection import Connection
from pygridgain.connection.bitmask_feature import BitmaskFeature
from pygridgain.connection.handshake import HandshakeRequest
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.stream import BinaryStream
from tests.util import client_in_timezone

# Zones observing DST in either hemisphere, a zone with a non-integer offset,
# and a couple of fixed-offset ones.
ZONE_IDS = ['Europe/Berlin', 'America/New_York', 'Australia/Sydney', 'Asia/Kolkata', 'Etc/GMT+5', 'UTC']

# A moment outside and a moment inside the northern DST period.
MOMENTS = [datetime(2020, 2, 12, 12, 32, 55), datetime(2020, 7, 12, 12, 32, 55)]

requires_tzset = pytest.mark.skipif(not hasattr(time, 'tzset'),
                                    reason='TZ is only honoured on POSIX platforms')


@requires_tzset
@pytest.mark.parametrize('zone_id', ZONE_IDS)
def test_connection_reports_zone_id(zone_id):
    with client_in_timezone(zone_id):
        assert Connection(Client(), '127.0.0.1', 10800).timezone == zone_id


@pytest.mark.parametrize('zone_id', ZONE_IDS)
def test_handshake_carries_zone_id(zone_id):
    protocol_context = ProtocolContext((1, 7, 1), BitmaskFeature.all_supported())
    request = HandshakeRequest(protocol_context, timezone=zone_id)

    with BinaryStream(Client()) as stream:
        request.from_python(stream)
        handshake = stream.getvalue()

    assert zone_id.encode() in handshake
    # The length is computed by hand in HandshakeRequest, so check it holds.
    assert struct.unpack('<i', handshake[:4])[0] == len(handshake) - 4


def test_reported_zone_matches_machine_zone():
    """ Whatever the machine is set to, the zone sent has to mean the same as the local one. """
    zone_id = Connection(Client(), '127.0.0.1', 10800).timezone

    assert zone_id is not None, 'nothing is sent, so the server keeps its own default zone'

    reported = ZoneInfo(zone_id)
    for moment in MOMENTS:
        assert moment.astimezone().utcoffset() == moment.replace(tzinfo=reported).utcoffset()
