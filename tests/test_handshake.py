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
from datetime import datetime

from pygridgain.api import *
from pygridgain.datatypes import (
    CollectionObject, IntObject, MapObject, TimestampObject,
)


def test_put_get(client, cache):
    # TODO: We can't get rid of LittleEndianStructure, because every structure has it's own encoding,
    # which is not handled in primitive.py.
    # we have to fix Boolean situation somehow, maybe replace it with int

    conn = client.random_node
    raise Exception("TEST STARTED")

    result = cache_put(conn, cache, 'my_key', 5)
    assert result.status == 0

    result = cache_get(conn, cache, 'my_key')
    assert result.status == 0
    assert result.value == 5
