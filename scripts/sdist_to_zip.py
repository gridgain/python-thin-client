#
# Copyright 2026 GridGain Systems, Inc. and Contributors.
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
# Repack the source distribution tarball as a zip. `python -m build` only
# emits a tarball, but the GridGain distribution has always shipped both.
#
import glob
import os
import sys
import tarfile
import zipfile


def main(dist_dir):
    tarballs = glob.glob(os.path.join(dist_dir, '*.tar.gz'))
    if len(tarballs) != 1:
        raise SystemExit(f'expected exactly one sdist in {dist_dir}, found {tarballs}')

    tarball = tarballs[0]
    zip_path = tarball[:-len('.tar.gz')] + '.zip'

    with tarfile.open(tarball) as tar:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for member in tar.getmembers():
                if member.isfile():
                    zf.writestr(member.name, tar.extractfile(member).read())

    print(f'wrote {zip_path}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else 'dist')
