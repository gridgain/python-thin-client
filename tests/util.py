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

import jinja2 as jinja2
import psutil
import re
import signal
import subprocess
import time


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

    raise Exception("Ignite not found. Please make sure your IGNITE_HOME environment variable points to directory with "
                    "a valid Ignite instance")


def get_ignite_config_path(use_ssl=False):
    if use_ssl:
        file_name = "ignite-config-ssl.xml"
    else:
        file_name = "ignite-default.xml.jinja2"

    return os.path.join(get_test_dir(), "config", file_name)


def check_server_started(idx=1):
    pattern = re.compile('^Topology snapshot.*')

    for log_file in get_log_files(idx):
        with open(log_file) as f:
            for line in f.readlines():
                if pattern.match(line):
                    return True

    return False


def kill_process_tree(pid):
    if is_windows():
        subprocess.call(['taskkill', '/F', '/T', '/PID', str(pid)])
    else:
        children = psutil.Process(pid).children(recursive=True)
        for child in children:
            os.kill(child.pid, signal.SIGKILL)
        os.kill(pid, signal.SIGKILL)


templateLoader = jinja2.FileSystemLoader(searchpath=os.path.join(get_test_dir(), "config"))
templateEnv = jinja2.Environment(loader=templateLoader)


def create_config_file(tpl_name, file_name, **kwargs):
    template = templateEnv.get_template(tpl_name)
    with open(os.path.join(get_test_dir(), "config", file_name), mode='w') as f:
        f.write(template.render(**kwargs))


def _start_ignite(idx=1, debug=False, use_ssl=False, cluster_idx=1, jvm_opts=''):
    clear_logs(idx)

    runner = get_ignite_runner()

    env = os.environ.copy()

    if debug:
        env["JVM_OPTS"] = env.get("JVM_OPTS", '') + \
                          "-Djava.net.preferIPv4Stack=true -Xdebug -Xnoagent -Djava.compiler=NONE " \
                          "-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address={5005} "

    if jvm_opts:
        env["JVM_OPTS"] = env.get("JVM_OPTS", '') + jvm_opts

    port_offset = (cluster_idx - 1) * 10
    params = {
        'ignite_instance_idx': str(idx),
        'ignite_client_port': 10800 + idx,
        'use_ssl': use_ssl,
        'discovery_port': 48500 + port_offset,
        'discovery_port_range': 48510 + port_offset,
        'communication_port': 48100 + port_offset,
    }

    create_config_file('log4j.xml.jinja2', f'log4j-{idx}.xml', **params)
    create_config_file('ignite-default.xml.jinja2', f'ignite-config-{idx}.xml', **params)

    ignite_cmd = [runner, os.path.join(get_test_dir(), "config", f'ignite-config-{idx}.xml')]
    print("Starting Ignite server node:", ignite_cmd)

    srv = subprocess.Popen(ignite_cmd, env=env, cwd=get_test_dir())

    started = wait_for_condition(lambda: check_server_started(idx), timeout=30)
    if started:
        return srv

    kill_process_tree(srv.pid)
    raise Exception("Failed to start Ignite: timeout while trying to connect")


def start_ignite_gen(idx=1, debug=False, use_ssl=False):
    srv = _start_ignite(idx, debug=debug, use_ssl=use_ssl)
    yield srv
    kill_process_tree(srv.pid)


def get_log_files(idx=1):
    logs_pattern = os.path.join(get_test_dir(), "logs", "ignite-log-{0}*.txt".format(idx))
    return glob.glob(logs_pattern)


def clear_logs(idx=1):
    for f in get_log_files(idx):
        os.remove(f)
