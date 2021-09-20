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

import attr

from pygridgain.api.tx_api import get_tx_id
from pygridgain.connection.protocol_context import ProtocolContext
from pygridgain.constants import PROTOCOL_BYTE_ORDER
from pygridgain.datatypes import ExpiryPolicy
from pygridgain.exceptions import NotSupportedByClusterError


@attr.s
class CacheInfo:
    cache_id = attr.ib(kw_only=True, type=int, default=0)
    expiry_policy = attr.ib(kw_only=True, type=ExpiryPolicy, default=None)
    protocol_context = attr.ib(kw_only=True, type=ProtocolContext)

    TRANSACTIONS_MASK = 0x02
    EXPIRY_POLICY_MASK = 0x04

    @classmethod
    async def from_python_async(cls, stream, value):
        return cls.from_python(stream, value)

    @classmethod
    def from_python(cls, stream, value):
        cache_id = value.cache_id if value else 0
        expiry_policy = value.expiry_policy if value else None
        flags = 0

        stream.write(cache_id.to_bytes(4, byteorder=PROTOCOL_BYTE_ORDER, signed=True))

        if expiry_policy:
            if not value.protocol_context.is_expiry_policy_supported():
                raise NotSupportedByClusterError("'ExpiryPolicy' API is not supported by the cluster")
            flags |= cls.EXPIRY_POLICY_MASK

        tx_id = get_tx_id()
        if value.protocol_context.is_transactions_supported() and tx_id:
            flags |= cls.TRANSACTIONS_MASK

        stream.write(flags.to_bytes(1, byteorder=PROTOCOL_BYTE_ORDER))

        if expiry_policy:
            ExpiryPolicy.write_policy(stream, expiry_policy)

        if flags & cls.TRANSACTIONS_MASK:
            stream.write(tx_id.to_bytes(4, byteorder=PROTOCOL_BYTE_ORDER, signed=True))
