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
import secrets
import socket
import unittest.mock as mock

import pytest

from pygridgain import Client
from tests.util import get_or_create_cache

old_recv_into = socket.socket.recv_into


def patched_recv_into_factory(buf_len):
    def patched_recv_into(self, buffer, nbytes, **kwargs):
        return old_recv_into(self, buffer, min(nbytes, buf_len) if buf_len else nbytes, **kwargs)
    return patched_recv_into


@pytest.mark.parametrize('buf_len', [0, 1, 4, 16, 32, 64, 128, 256, 512, 1024])
def test_get_large_value(buf_len):
    with mock.patch.object(socket.socket, 'recv_into', new=patched_recv_into_factory(buf_len)):
        c = Client()
        with c.connect("127.0.0.1", 10801):
            with get_or_create_cache(c, 'test') as cache:
                value = secrets.token_hex((1 << 16) + 1)
                cache.put(1, value)
                assert value == cache.get(1)
