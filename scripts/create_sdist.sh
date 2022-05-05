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

# Create source dist.
for PYBIN in /opt/python/*/bin; do
    if [[ $PYBIN =~ ^(.*)cp3[7891](.*)$ ]]; then
        cd pygridgain
        "${PYBIN}/python" setup.py sdist --formats=gztar,zip --dist-dir /dist
        break;
    fi
done

for archive in /dist/*; do
    if [[ $archive =~ ^(.*)(tar\.gz|zip)$ ]]; then
        chmod 666 "$archive"
    fi
done

rm -rf /pygridgain/*.egg-info
rm -rf /pygridgain/.eggs
