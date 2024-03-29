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
import glob
import os
import subprocess
import sys

import pytest

from tests.util import get_test_dir, start_ignite_gen

SKIP_LIST = [
    'failover.py',  # it hangs by design
]


def examples_scripts_gen():
    examples_dir = os.path.join(get_test_dir(), '..', 'examples')
    for script in glob.glob1(examples_dir, '*.py'):
        if script not in SKIP_LIST:
            yield os.path.join(examples_dir, script)


@pytest.fixture(autouse=True)
def server():
    yield from start_ignite_gen(idx=0)  # idx=0, because 10800 port is needed for examples.


@pytest.mark.examples
@pytest.mark.parametrize(
    'example_script',
    examples_scripts_gen()
)
def test_examples(example_script):
    proc = subprocess.run([
        sys.executable,
        example_script
    ])

    assert proc.returncode == 0
