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
# The package metadata lives in pyproject.toml. What is left here is the C
# extension, which has to be attempted and then given up on when the platform
# cannot compile it, so that the client still installs as pure Python.
#
from setuptools.command.build_ext import build_ext
from setuptools.errors import CCompilerError, ExecError, PlatformError

import setuptools
import sys


cext = setuptools.Extension(
    "pygridgain._cutils",
    sources=[
        "./cext/cutils.c"
    ],
    include_dirs=["./cext"]
)

if sys.platform == 'win32':
    ext_errors = (CCompilerError, ExecError, PlatformError, IOError, ValueError)
else:
    ext_errors = (CCompilerError, ExecError, PlatformError)


class BuildFailed(Exception):
    pass


class ve_build_ext(build_ext):
    # This class allows C extension building to fail.

    def run(self):
        try:
            build_ext.run(self)
        except PlatformError:
            raise BuildFailed()

    def build_extension(self, ext):
        try:
            build_ext.build_extension(self, ext)
        except ext_errors:
            raise BuildFailed()


def run_setup(with_binary=True):
    if with_binary:
        kw = dict(
            ext_modules=[cext],
            cmdclass=dict(build_ext=ve_build_ext),
        )
    else:
        kw = dict()

    setuptools.setup(**kw)


try:
    run_setup()
except BuildFailed:
    BUILD_EXT_WARNING = ("WARNING: The C extension could not be compiled, "
                         "speedups are not enabled.")
    print('*' * 75)
    print(BUILD_EXT_WARNING)
    print("Failure information, if any, is above.")
    print("I'm retrying the build without the C extension now.")
    print('*' * 75)

    run_setup(False)

    print('*' * 75)
    print(BUILD_EXT_WARNING)
    print("Plain python installation succeeded.")
    print('*' * 75)
