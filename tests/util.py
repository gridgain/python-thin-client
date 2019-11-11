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
import datetime
import glob
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


def get_ignite_config_path(idx=1):
    return os.path.join(get_test_dir(), "config", "ignite-config-{0}.xml".format(idx))


def try_connect_client(idx=1):
    cli = Client()
    try:
        cli.connect('localhost', 10800 + idx)
        cli.close()
        return True
    except ReconnectError:
        return False


def kill_process_tree(pid):
    if is_windows():
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)])
    else:
        os.killpg(os.getpgid(pid), signal.SIGKILL)


def start_ignite(idx=1, debug=False):
    clear_logs(idx)

    runner = get_ignite_runner()

    env = os.environ.copy()

    if debug:
        env["JVM_OPTS"] = "-Djava.net.preferIPv4Stack=true -Xdebug -Xnoagent -Djava.compiler=NONE " \
                          "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=5005 "

    ignite_cmd = [runner, get_ignite_config_path(idx)]
    print("Starting Ignite server node:", ignite_cmd)

    srv = subprocess.Popen(ignite_cmd, env=env, cwd=get_test_dir())

    started = wait_for_condition(lambda: try_connect_client(idx), timeout=10)
    if started:
        return srv

    kill_process_tree(srv.pid)
    raise Exception("Failed to start Ignite: timeout while trying to connect")


def start_ignite_gen(idx=1):
    srv = start_ignite(idx)
    yield srv
    kill_process_tree(srv.pid)


def get_log_files(idx=1):
    logs_pattern = os.path.join(get_test_dir(), "logs", "ignite-log-{0}*.txt".format(idx))
    return glob.glob(logs_pattern)


def clear_logs(idx=1):
    for f in get_log_files(idx):
        os.remove(f)


def read_log_file(file, skip_before):
    with open(file) as f:
        for line in f.read().splitlines():
            parts = line.split("|")
            timestamp = datetime.datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
            if timestamp > skip_before:
                yield parts[1]


def get_request_grid_idx(message=None):
    last_call = get_request_grid_idx.last_call
    get_request_grid_idx.last_call = datetime.datetime.now()
    for i in range(1, 3):
        for log_file in get_log_files(i):
            log = read_log_file(log_file, last_call)
    # TODO: Keep track of last call time, filter out earlier messages
    return 1
