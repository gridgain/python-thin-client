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
from pygridgain.exceptions import NotSupportedByClusterError
from pygridgain.queries import Query, query_perform
from pygridgain.queries.op_codes import OP_CLUSTER_GET_STATE, OP_CLUSTER_CHANGE_STATE


def cluster_get_state(connection: 'Connection', query_id=None) -> 'APIResult':
    """
    Get cluster state.

    :param connection: Connection to use,
    :param query_id: (optional) a value generated by client and returned as-is
     in response.query_id. When the parameter is omitted, a random value
     is generated,
    :return: API result data object. Contains zero status and a state
     retrieved on success, non-zero status and an error description on failure.
    """
    return __cluster_get_state(connection, query_id)


async def cluster_get_state_async(connection: 'AioConnection', query_id=None) -> 'APIResult':
    """
    Async version of cluster_get_state
    """
    return await __cluster_get_state(connection, query_id)


def __post_process_get_state(result):
    if result.status == 0:
        result.value = result.value['state']
    return result


def __cluster_get_state(connection, query_id):
    if not connection.protocol_context.is_cluster_api_supported():
        raise NotSupportedByClusterError('Cluster API is not supported by the cluster')

    query_struct = Query(OP_CLUSTER_GET_STATE, query_id=query_id)
    return query_perform(
        query_struct, connection,
        response_config=[('state', Byte)],
        post_process_fun=__post_process_get_state
    )


def cluster_set_state(connection: 'Connection', state: int, query_id=None) -> 'APIResult':
    """
    Set cluster state.

    :param connection: Connection to use,
    :param state: State to set,
    :param query_id: (optional) a value generated by client and returned as-is
     in response.query_id. When the parameter is omitted, a random value
     is generated,
    :return: API result data object. Contains zero status if a value
     is written, non-zero status and an error description otherwise.
    """
    return __cluster_set_state(connection, state, query_id)


async def cluster_set_state_async(connection: 'AioConnection', state: int, query_id=None) -> 'APIResult':
    """
    Async version of cluster_get_state
    """
    return await __cluster_set_state(connection, state, query_id)


def __post_process_set_state(result):
    if result.status == 0:
        result.value = result.value['state']
    return result


def __cluster_set_state(connection, state, query_id):
    if not connection.protocol_context.is_cluster_api_supported():
        raise NotSupportedByClusterError('Cluster API is not supported by the cluster')

    query_struct = Query(
        OP_CLUSTER_CHANGE_STATE,
        [
            ('state', Byte)
        ],
        query_id=query_id
    )
    return query_perform(
        query_struct, connection,
        query_params={
            'state': state,
        }
    )
