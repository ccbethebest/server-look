"""One persistent, read-only SSH agent per server for low-latency navigation."""
import json
from pathlib import Path
import queue
import shlex
import subprocess
import sys
import threading
import time

from settings import SSH_REQUEST_TIMEOUT_SECONDS

DIRECTORY_AGENT = r"""
import json, sys, types
resources = types.ModuleType('resources')
exec(compile(json.loads(sys.stdin.readline())['source'], '<resources>', 'exec'), resources.__dict__)
for line in sys.stdin:
    try:
        request = json.loads(line)
        if request.get('action') == 'mkdir':
            import os
            name = request['name']
            if not name or name in ('.', '..') or any(c in name for c in '/\\\\\x00'):
                raise ValueError('请输入单个文件夹名称')
            os.mkdir(os.path.join(os.path.realpath(request['path']), name))
        elif request.get('action') == 'delete':
            resources.delete_entries(request['path'], request['names'])
        elif request.get('action') in ('copy', 'rename', 'compress', 'extract'):
            resources.file_operation(request['path'], request['action'], request['names'], **request.get('options', {}))
        result = {'result': resources.list_directory(request['path'])}
    except Exception as exc:
        result = {'error': str(exc)}
    print(json.dumps(result), flush=True)
"""


class DirectoryChannel:
    def __init__(self, ssh_args, opener=None):
        self.opener = opener
        self.args = ssh_args
        self.process = None
        self.responses = None
        self.closed = False
        self.lock = threading.Lock()
        self.state_lock = threading.Lock()

    @staticmethod
    def read_responses(process, responses):
        try:
            for line in process.stdout:
                responses.put(line)
        finally:
            responses.put(None)
            process.stdout.close()

    def start(self):
        with self.state_lock:
            if self.closed:
                raise RuntimeError('服务器已断开')
            if self.process is not None and self.process.poll() is None:
                return
            resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
            source = (resources / 'server_resources.py').read_text(encoding='utf-8')
            self.responses = queue.Queue()
            self.process = self.opener('python3 -u -c ' + shlex.quote(DIRECTORY_AGENT)) if self.opener else subprocess.Popen(self.args + ['python3 -u -c ' + shlex.quote(DIRECTORY_AGENT)],
                                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                            encoding='utf-8', errors='replace', bufsize=1,
                                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            threading.Thread(target=self.read_responses, args=(self.process, self.responses), daemon=True).start()
            self.process.stdin.write(json.dumps({'source': source}) + '\n')
            self.process.stdin.flush()

    def request(self, path, **values):
        with self.lock:
            self.start()
            try:
                self.process.stdin.write(json.dumps(dict(path=path, **values)) + '\n')
                self.process.stdin.flush()
                deadline = time.monotonic() + (86400 if values.get('action') in ('copy', 'compress', 'extract') else SSH_REQUEST_TIMEOUT_SECONDS)
                while True:
                    line = self.responses.get(timeout=max(0, deadline - time.monotonic()))
                    if line is None:
                        self.stop()
                        raise RuntimeError('目录连接已关闭，请重试')
                    try:
                        response = json.loads(line)
                    except ValueError:
                        continue  # SSH login banners are not protocol responses.
                    if isinstance(response, dict) and ('result' in response or 'error' in response):
                        break
                if 'error' in response:
                    raise OSError(response['error'])
                return response['result']
            except (queue.Empty, BrokenPipeError):
                self.stop()
                raise RuntimeError('目录连接中断或读取超时，请重试') from None

    def stop(self):
        with self.state_lock:
            if self.process is not None:
                if self.process.poll() is None:
                    self.process.kill()
                try:
                    self.process.stdin.close()
                except OSError:
                    pass
                self.process = None
            if self.responses is not None:
                self.responses.put(None)

    def close(self):
        self.closed = True
        self.stop()
