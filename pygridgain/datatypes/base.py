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


class GridGainDataTypeProps:
    """
    Add `type_name` and `type_id` properties for all classes and objects
    of GridGain type hierarchy.
    """
    @property
    def type_name(self) -> str:
        """ Binary object type name. """
        return getattr(self, '_type_name', None)

    @property
    def type_id(self) -> int:
        """ Binary object type ID. """
        from pygridgain.utils import entity_id

        return getattr(
            self,
            '_type_id',
            entity_id(getattr(self, '_type_name', None))
        )


class GridGainDataTypeMeta(type, GridGainDataTypeProps):
    """
    Class variant of Ignate data type properties.
    """
    pass


class GridGainDataType(metaclass=GridGainDataTypeMeta):
    """
    This is a base class for all GridGain data types,
    a.k.a. parser/constructor classes, both object and payload varieties.
    """
    @classmethod
    async def hashcode_async(cls, value, **kwargs):
        return cls.hashcode(value, **kwargs)

    @classmethod
    def hashcode(cls, value, **kwargs):
        return 0

    @classmethod
    def parse(cls, stream):
        raise NotImplementedError

    @classmethod
    async def parse_async(cls, stream):
        return cls.parse(stream)

    @classmethod
    def from_python(cls, stream, value, **kwargs):
        raise NotImplementedError

    @classmethod
    async def from_python_async(cls, stream, value, **kwargs):
        cls.from_python(stream, value, **kwargs)

    @classmethod
    def to_python(cls, ctypes_object, **kwargs):
        raise NotImplementedError

    @classmethod
    async def to_python_async(cls, ctypes_object, **kwargs):
        return cls.to_python(ctypes_object, **kwargs)
