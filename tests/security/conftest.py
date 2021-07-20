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
import os

import pytest

from pygridgain import monitoring
from tests.util import get_test_dir


@pytest.fixture
def ssl_params():
    yield __create_ssl_param(False)


@pytest.fixture
def ssl_params_with_password():
    yield __create_ssl_param(True)


def __create_ssl_param(with_password=False):
    cert_path = os.path.join(get_test_dir(), 'config', 'ssl')

    if with_password:
        cert = os.path.join(cert_path, 'client_with_pass_full.pem')
        return {
            'ssl_keyfile': cert,
            'ssl_keyfile_password': '654321',
            'ssl_certfile': cert,
            'ssl_ca_certfile': cert,
        }
    else:
        cert = os.path.join(cert_path, 'client_full.pem')
        return {
            'ssl_keyfile': cert,
            'ssl_certfile': cert,
            'ssl_ca_certfile': cert
        }


class AccumulatingConnectionListener(monitoring.ConnectionEventListener):
    def __init__(self):
        self.events = []

    def on_handshake_start(self, event):
        self.events.append(event)

    def on_handshake_success(self, event):
        self.events.append(event)

    def on_handshake_fail(self, event):
        self.events.append(event)

    def on_authentication_fail(self, event):
        self.events.append(event)

    def on_connection_closed(self, event):
        self.events.append(event)

    def on_connection_lost(self, event):
        self.events.append(event)
