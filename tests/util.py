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
import os
import signal
import subprocess
import time

from pygridgain import Client
from pygridgain.exceptions import ReconnectError


def wait_for_condition(condition, interval=0.1, timeout=10, error=None):
    start = time.time()
    res = condition()

    while not res and time.time() - start < timeout:
        time.sleep(interval)
        res = condition()

    if res:
        return True

    if error is not None:
        raise Exception(error)

    return False


def is_windows():
    return os.name == "nt"


def get_test_dir():
    return os.path.dirname(os.path.realpath(__file__))


def get_ignite_dirs():
    ignite_home = os.getenv("IGNITE_HOME")
    if ignite_home is not None:
        yield ignite_home

    proj_dir = os.path.abspath(os.path.join(get_test_dir(), "..", ".."))
    yield os.path.join(proj_dir, "ignite")
    yield os.path.join(proj_dir, "incubator_ignite")


def get_ignite_runner():
    ext = ".bat" if is_windows() else ".sh"
    for ignite_dir in get_ignite_dirs():
        runner = os.path.join(ignite_dir, "bin", "ignite" + ext)
        print("Probing Ignite runner at '{0}'...".format(runner))
        if os.path.exists(runner):
            return runner

    raise Exception("Ignite not found.")


def get_ignite_config_path():
    return os.path.join(get_test_dir(), "config", "ignite-config-1.xml")


def get_jul_config_path():
    return os.path.join(get_test_dir(), "config", "java.util.logging.properties")


def try_connect_client():
    cli = Client()
    try:
        cli.connect()
        cli.close()
        return True
    except ReconnectError:
        return False


def kill_process_tree(pid):
    if is_windows():
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)])
    else:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
