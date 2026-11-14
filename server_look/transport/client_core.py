"""SSH transport shared by the Windows desktop client and its tests."""
from server_look.paths import resource_root
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from server_look.app.settings import SSH_REQUEST_TIMEOUT_SECONDS
from server_look.transport.directory_channel import DirectoryChannel

REMOTE = """
import json, sys, signal, types
request = json.load(sys.stdin)
monitor = types.ModuleType('npu_top_remote')
exec(compile(request.pop('source'), '<npu-monitor>', 'exec'), monitor.__dict__)
resources = types.ModuleType('server_resources_remote')
exec(compile(request.pop('resource_source'), '<server-resources>', 'exec'), resources.__dict__)
action = request['action']
if action == 'snapshot':
    data = monitor.collect()
    data.update(resources.collect_resources(data.get('npu', '')))
    data['hardware'].update(data.get('accelerator_hardware', {}))
    processes = data['processes']
    related = {pid for pid, p in processes.items() if p.get('npu') or p['container']}
    # Preserve launcher ancestors and descendants, including host-side helper processes.
    changed = True
    while changed:
        before = len(related)
        for pid in list(related):
            parent = processes[pid]['ppid']
            if parent in processes:
                related.add(parent)
        changed = len(related) != before
    # Only descend from monitored tasks, not from shared ancestors such as init/sshd.
    descendants = {pid for pid, p in processes.items() if p.get('npu') or p['container']}
    changed = True
    while changed:
        children = {pid for pid, p in processes.items() if p['ppid'] in descendants}
        changed = not children.issubset(descendants)
        descendants.update(children)
    data['processes'] = {pid: p for pid, p in processes.items() if pid in related or pid in descendants}
    print(json.dumps(data))
elif action == 'idle':
    raw, tasks, hardware, errors = monitor.collect_accelerators()
    result = resources.accelerator_occupancy(raw, tasks, hardware)
    result['errors'].extend(errors)
    print(json.dumps(result))
elif action == 'search':
    options = {key: request[key] for key in ('path', 'pattern', 'mode', 'case_sensitive', 'recursive', 'kind')}
    options['directory_sizes'] = request.get('directory_sizes', False)
    if request.get('stream'):
        data = resources.run_search(**options, on_batch=lambda rows: print(json.dumps({'batch': rows}), flush=True))
        data.pop('results')
        print(json.dumps({'done': data}), flush=True)
    else:
        print(json.dumps(resources.run_search(**options)))
elif action in ('term', 'kill'):
    pid, ticks = int(request['pid']), int(request['ticks'])
    if pid <= 1 or ticks <= 0:
        raise ValueError('Invalid process identity')
    print(json.dumps({'message': monitor.signal_tree({'pid': pid, 'ticks': ticks}, signal.SIGTERM if action == 'term' else signal.SIGKILL)}))
elif action == 'stop':
    import re
    cid = request['cid']
    if not re.fullmatch('[0-9a-f]{64}', cid):
        raise ValueError('Invalid container ID')
    print(json.dumps({'message': monitor.run(['docker', 'stop', '--time', '10', cid], timeout=20).strip()}))
else:
    raise ValueError('Unknown action')
"""


def connection_args(host, user, port):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.:-]{0,252}', host):
        raise ValueError('服务器地址格式不正确')
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.-]{0,63}', user):
        raise ValueError('SSH 用户名格式不正确')
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError('端口必须为 1–65535')
    native = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/OpenSSH/ssh.exe'
    executable = str(native) if native.exists() else shutil.which('ssh')
    if not executable:
        raise RuntimeError('未安装 OpenSSH 客户端')
    return [executable, '-o', 'BatchMode=yes', '-o', 'StrictHostKeyChecking=yes',
            '-o', 'ConnectTimeout=10', '-o', 'ServerAliveInterval=5',
            '-o', 'ServerAliveCountMax=2', '-p', str(port), '-l', user, host]


class Connection:
    """Validated target with snapshot requests and a persistent directory channel."""
    def __init__(self, host, user, port, auth_mode="key", password=""):
        if auth_mode not in ("key", "password"):
            raise ValueError("未知认证方式")
        if auth_mode == "password" and not password:
            raise ValueError("请输入 SSH 登录密码")
        self.args = connection_args(host, user, port)
        self.session = None
        if auth_mode == "password":
            from server_look.transport.password_transport import PasswordSession
            self.session = PasswordSession(host, user, int(port), password)
        self.directory = DirectoryChannel(self.args, self.session.open_process if self.session else None)

    def close(self):
        self.directory.close()
        if self.session:
            self.session.close()

    def request(self, action='snapshot', **values):
        if action == 'list_directory':
            return self.directory.request(values['path'])
        resources = resource_root() / 'server_look' / 'remote'
        source = (resources / 'npu_top.py').read_text(encoding='utf-8')
        resource_source = (resources / 'server_resources.py').read_text(encoding='utf-8')
        if action == 'search':
            resource_source += '\n' + (resources / 'file_search.py').read_text(encoding='utf-8-sig')
        payload = json.dumps(dict(action=action, source=source, resource_source=resource_source, **values))
        if self.session:
            return json.loads(self.session.execute("python3 -c " + shlex.quote(REMOTE), payload))
        result = subprocess.run(
            self.args + ['python3 -c ' + shlex.quote(REMOTE)],
            input=json.dumps(dict(action=action, source=source, resource_source=resource_source, **values)), capture_output=True,
            encoding='utf-8', errors='replace', timeout=SSH_REQUEST_TIMEOUT_SECONDS,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip()[-2500:])
        return json.loads(result.stdout)

    def search(self, options, cancel, on_batch):
        from server_look.files.remote_search import stream_search
        resources = resource_root() / 'server_look' / 'remote'
        payload = dict(action='search', stream=True, **options,
                       source=(resources / 'npu_top.py').read_text(encoding='utf-8'),
                       resource_source=(resources / 'server_resources.py').read_text(encoding='utf-8') +
                       '\n' + (resources / 'file_search.py').read_text(encoding='utf-8-sig'))
        command = 'python3 -u -c ' + shlex.quote(REMOTE)
        return stream_search(self, command, payload, cancel, on_batch)


def task_identity(task):
    return int(task['pid']), int(task['ticks'])


def find_task(data, identity):
    if identity is None:
        return None
    task = data.get('processes', {}).get(str(identity[0]))
    return task if task and task_identity(task) == identity else None
