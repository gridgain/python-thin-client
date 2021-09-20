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
from pygridgain.api import APIResult
from pygridgain.connection import AioConnection, Connection
from pygridgain.datatypes import Byte
from pygridgain.datatypes.cluster_state import ClusterState
from pygridgain.exceptions import NotSupportedByClusterError, ClusterError
from pygridgain.queries import Query, query_perform
from pygridgain.queries.op_codes import OP_CLUSTER_GET_STATE, OP_CLUSTER_CHANGE_STATE


def cluster_get_state(connection: 'Connection') -> 'APIResult':
    """
    Get cluster state.

    :param connection: Connection to use,
    :return: API result data object. Contains zero status and a state
     retrieved on success, non-zero status and an error description on failure.
    """
    return __cluster_get_state(connection)


async def cluster_get_state_async(connection: 'AioConnection') -> 'APIResult':
    """
    Async version of cluster_get_state
    """
    return await __cluster_get_state(connection)


def __post_process_get_state(result):
    if result.status == 0:
        result.value = ClusterState(result.value['state'])
    return result


def __cluster_get_state(connection):
    if not connection.protocol_context.is_cluster_api_supported():
        raise NotSupportedByClusterError('Cluster API is not supported by the cluster')

    query_struct = Query(OP_CLUSTER_GET_STATE)
    return query_perform(
        query_struct, connection,
        response_config=[('state', Byte)],
        post_process_fun=__post_process_get_state
    )


def cluster_set_state(connection: 'Connection', state: ClusterState) -> 'APIResult':
    """
    Set cluster state.

    :param connection: Connection to use,
    :param state: State to set,
    :return: API result data object. Contains zero status if a value
     is written, non-zero status and an error description otherwise.
    """
    return __cluster_set_state(connection, state)


async def cluster_set_state_async(connection: 'AioConnection', state: ClusterState) -> 'APIResult':
    """
    Async version of cluster_get_state
    """
    return await __cluster_set_state(connection, state)


def __post_process_set_state(result):
    if result.status == 0:
        result.value = result.value['state']
    return result


def __cluster_set_state(connection, state):
    if not ClusterState.has_value(state):
        raise ClusterError(f'Unknown cluster state [state={state}]')
    if not connection.protocol_context.is_cluster_api_supported():
        raise NotSupportedByClusterError('Cluster API is not supported by the cluster')

    query_struct = Query(
        OP_CLUSTER_CHANGE_STATE,
        [
            ('state', Byte)
        ]
    )
    return query_perform(
        query_struct, connection,
        query_params={
            'state': state,
        }
    )
