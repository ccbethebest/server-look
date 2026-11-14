"""Stream search batches over one SSH channel without blocking the GUI."""
import json
import queue
import subprocess
import threading
import time

from settings import SSH_REQUEST_TIMEOUT_SECONDS


def stream_search(connection, command, payload, cancel, on_batch):
    started = time.monotonic()
    process = (connection.session.open_process(command) if connection.session else
               subprocess.Popen(connection.args + [command], stdin=subprocess.PIPE,
                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                   encoding='utf-8', errors='replace',
                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)))
    lines = queue.Queue()

    def read():
        try:
            for line in process.stdout:
                lines.put(line)
        finally:
            lines.put(None)

    threading.Thread(target=read, daemon=True).start()
    results, errors = [], []
    try:
        process.stdin.write(json.dumps(payload))
        process.stdin.flush()
        if connection.session:
            process.channel.shutdown_write()
        process.stdin.close()
        while True:
            if cancel.is_set():
                return dict(results=results, reason='已停止', scanned=None, skipped=None,
                            elapsed=round(time.monotonic() - started, 2))
            if time.monotonic() - started > SSH_REQUEST_TIMEOUT_SECONDS:
                raise TimeoutError('远程搜索连接超时')
            try:
                line = lines.get(timeout=0.05)
            except queue.Empty:
                continue
            if line is None:
                raise RuntimeError('远程搜索未完成：' + ''.join(errors)[-1500:])
            try:
                event = json.loads(line)
            except ValueError:
                errors.append(line)
                errors = errors[-10:]
                continue
            if isinstance(event, dict) and 'batch' in event:
                results.extend(event['batch'])
                on_batch(event['batch'])
            elif isinstance(event, dict) and 'done' in event:
                return dict(results=results, **event['done'])
    finally:
        if process.poll() is None:
            process.kill()
        if not connection.session:
            process.wait(timeout=5)
        process.stdin.close()
        process.stdout.close()
