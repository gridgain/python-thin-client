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
import ssl
from ssl import SSLContext, TLSVersion

from pygridgain.constants import SSL_DEFAULT_CIPHERS, SSL_DEFAULT_VERSION
from pygridgain.exceptions import ParameterError

#: ``ssl.PROTOCOL_*`` constants mapped to the (minimum, maximum) TLS version they select;
#: None leaves the OpenSSL default. ``SSLContext()`` warns about all of them except
#: PROTOCOL_TLS_CLIENT, so they are translated, never passed on. A constant is missing
#: when the OpenSSL build does not support that protocol.
_PROTOCOL_VERSIONS = {
    ssl.PROTOCOL_TLS_CLIENT: (None, None),
    ssl.PROTOCOL_TLS: (None, None),
    **{
        getattr(ssl, name): (version, version)
        for name, version in (
            ('PROTOCOL_TLSv1', TLSVersion.TLSv1),
            ('PROTOCOL_TLSv1_1', TLSVersion.TLSv1_1),
            ('PROTOCOL_TLSv1_2', TLSVersion.TLSv1_2),
        )
        if hasattr(ssl, name)
    },
}


def wrap(socket, ssl_params):
    """ Wrap socket in SSL wrapper. """
    if not ssl_params.get('use_ssl'):
        return socket

    context = create_ssl_context(ssl_params)

    return context.wrap_socket(sock=socket)


def check_ssl_params(params):
    expected_args = [
        'use_ssl',
        'ssl_version',
        'ssl_ciphers',
        'ssl_cert_reqs',
        'ssl_keyfile',
        'ssl_keyfile_password',
        'ssl_certfile',
        'ssl_ca_certfile',
    ]
    for param in params:
        if param not in expected_args:
            raise ParameterError((
                'Unexpected parameter for connection initialization: `{}`'
            ).format(param))


def create_ssl_context(ssl_params):
    if not ssl_params.get('use_ssl'):
        return None

    keyfile = ssl_params.get('ssl_keyfile', None)
    certfile = ssl_params.get('ssl_certfile', None)

    if keyfile and not certfile:
        raise ValueError("certfile must be specified")

    password = ssl_params.get('ssl_keyfile_password', None)
    ssl_version = ssl_params.get('ssl_version')
    if ssl_version is None:
        ssl_version = SSL_DEFAULT_VERSION
    ciphers = ssl_params.get('ssl_ciphers', SSL_DEFAULT_CIPHERS)
    cert_reqs = ssl_params.get('ssl_cert_reqs', ssl.CERT_NONE)
    ca_certs = ssl_params.get('ssl_ca_certfile', None)

    context = SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    # PROTOCOL_TLS_CLIENT turns hostname checks on, and the client never did them. It must be
    # turned off before verify_mode, which cannot be CERT_NONE while check_hostname is on.
    context.check_hostname = False
    context.verify_mode = cert_reqs
    _set_tls_versions(context, ssl_version)

    if ca_certs:
        context.load_verify_locations(ca_certs)
    if certfile:
        context.load_cert_chain(certfile, keyfile, password)
    if ciphers:
        context.set_ciphers(ciphers)

    return context


def _set_tls_versions(context, ssl_version):
    """
    Apply ``ssl_version`` to the context: a ``ssl.TLSVersion`` is the minimum version, while a
    legacy ``ssl.PROTOCOL_*`` constant keeps the versions it selected before.
    """
    if isinstance(ssl_version, TLSVersion):
        context.minimum_version = ssl_version
        return
    try:
        minimum, maximum = _PROTOCOL_VERSIONS[ssl_version]
    except (KeyError, TypeError):
        raise ParameterError(f'Unsupported ssl_version: {ssl_version!r}') from None
    if minimum is not None:
        context.minimum_version = minimum
    if maximum is not None:
        context.maximum_version = maximum
