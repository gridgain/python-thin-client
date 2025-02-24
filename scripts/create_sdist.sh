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

PACKAGE_NAME=pygridgain

# Create source dist.
for PYBIN in /opt/python/*/bin; do
    if [[ $PYBIN =~ ^(.*)cp39(.*)$ ]] || [[ $PYBIN =~ ^(.*)cp31[0123](.*)$ ]]; then
        cd $PACKAGE_NAME
        "${PYBIN}/python" setup.py sdist --formats=gztar,zip --dist-dir /dist
        break;
    fi
done

chown -R `stat -c "%u:%g" /dist/` /dist/*

rm -rf /$PACKAGE_NAME/*.egg-info
rm -rf /$PACKAGE_NAME/.eggs
