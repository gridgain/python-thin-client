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

from enum import IntEnum


class ClusterState(IntEnum):
    """
    Cluster states.
    """

    #: Cluster deactivated. Cache operations aren't allowed.
    INACTIVE = 0

    #: Cluster activated. All cache operations are allowed.
    ACTIVE = 1

    #: Cluster activated. Cache read operation allowed, Cache data change operation
    #: aren't allowed.
    ACTIVE_READ_ONLY = 2

    @classmethod
    def has_value(cls, value):
        if not hasattr(cls, 'values'):
            cls.values = set(item.value for item in ClusterState)
        return value in cls.values
