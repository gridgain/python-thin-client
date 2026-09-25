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
import ssl
import warnings

import pytest

from pygridgain.connection.ssl import create_ssl_context
from pygridgain.exceptions import ParameterError

MIN = ssl.TLSVersion.MINIMUM_SUPPORTED
MAX = ssl.TLSVersion.MAXIMUM_SUPPORTED


def _context(**params):
    with warnings.catch_warnings():
        warnings.simplefilter('error', DeprecationWarning)
        return create_ssl_context({'use_ssl': True, **params})


def test_no_context_without_ssl():
    assert create_ssl_context({'use_ssl': False}) is None


@pytest.mark.parametrize('params', [{}, {'ssl_version': None}])
def test_default_allows_tls_1_2_and_newer(params):
    ctx = _context(**params)
    assert ctx.protocol == ssl.PROTOCOL_TLS_CLIENT
    assert (ctx.minimum_version, ctx.maximum_version) == (ssl.TLSVersion.TLSv1_2, MAX)


def test_hostname_is_not_checked():
    ctx = _context(ssl_cert_reqs=ssl.CERT_REQUIRED)
    assert not ctx.check_hostname
    assert ctx.verify_mode == ssl.CERT_REQUIRED
    assert _context().verify_mode == ssl.CERT_NONE


def test_tls_version_is_the_minimum():
    ctx = _context(ssl_version=ssl.TLSVersion.TLSv1_3)
    assert (ctx.minimum_version, ctx.maximum_version) == (ssl.TLSVersion.TLSv1_3, MAX)


def test_legacy_protocol_pins_its_version():
    ctx = _context(ssl_version=ssl.PROTOCOL_TLSv1_2)
    assert (ctx.minimum_version, ctx.maximum_version) == (ssl.TLSVersion.TLSv1_2, ssl.TLSVersion.TLSv1_2)


@pytest.mark.parametrize('protocol', [ssl.PROTOCOL_TLS, ssl.PROTOCOL_SSLv23, ssl.PROTOCOL_TLS_CLIENT])
def test_generic_protocol_keeps_openssl_defaults(protocol):
    ctx = _context(ssl_version=protocol)
    default = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    assert (ctx.minimum_version, ctx.maximum_version) == (default.minimum_version, default.maximum_version)
    assert ctx.minimum_version in (MIN, ssl.TLSVersion.TLSv1_2)


@pytest.mark.parametrize('version', [ssl.PROTOCOL_TLS_SERVER, 'TLSv1.2', []])
def test_unsupported_version_is_rejected(version):
    with pytest.raises(ParameterError):
        _context(ssl_version=version)
