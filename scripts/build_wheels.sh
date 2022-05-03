#!/bin/bash
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

set -e -u -x

function repair_wheel {
    wheel="$1"
    if ! auditwheel show "$wheel"; then
        echo "Skipping non-platform wheel $wheel"
    else
        auditwheel repair "$wheel" --plat "$PLAT" -w /wheels
    fi
}

# Compile wheels
for PYBIN in /opt/python/*/bin; do
    if [[ $PYBIN =~ ^(.*)cp3[7891](.*)$ ]]; then
        "${PYBIN}/pip" wheel /pygridgain/ --no-deps -w /wheels
    fi
done

# Bundle external shared libraries into the wheels
for whl in /wheels/*.whl; do
    repair_wheel "$whl"
done

for whl in /wheels/*.whl; do
    if [[ ! $whl =~ ^(.*)manylinux(.*)$ ]]; then
        rm "$whl"
    else
        chmod 666 "$whl"
    fi
done

rm -rf /pygridgain/*.egg-info
rm -rf /pygridgain/.eggs
