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
import ctypes


def test_structs():
    test_class = type(
        "FooBar",
        (ctypes.BigEndianStructure,),
        {
            '_pack_': 1,
            '_fields_': [
                ('length', ctypes.c_int),
                ('op_code', ctypes.c_short),
                ('query_id', ctypes.c_longlong),
            ],
        },
    )

    obj = test_class()
    obj.length = 7
    obj.op_code = 13
    obj.query_id = 42

    # LE: b'\x07\x00\x00\x00\r\x00*\x00\x00\x00\x00\x00\x00\x00'
    # BE: b'\x00\x00\x00\x07\x00\r\x00\x00\x00\x00\x00\x00\x00*'
    bytearr = bytes(obj)
    print(''.join('{:02x} '.format(x) for x in bytearr))
    #print(bytearr)
