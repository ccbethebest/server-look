"""Read-only terminal smoke test. Run on the NPU host; never sends kill/stop actions."""
import fcntl
import importlib.util
import json
import os
import pty
import select
import struct
import subprocess
import sys
import termios
import time
from pathlib import Path


def main():
    spec = importlib.util.spec_from_file_location('npu_top', (Path(__file__).resolve().parents[1] / 'server_look/remote/npu_top.py'))
    app = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app)
    started = time.monotonic()
    data = app.collect()
    print(json.dumps(dict(collection_seconds=round(time.monotonic() - started, 3),
                          cards=len(app.telemetry_lines(data['npu'])),
                          containers=len(data['containers']),
                          npu_tasks=sum(bool(p.get('npu')) for p in data['processes'].values()),
                          errors=data['errors'])))
    assert len(app.telemetry_lines(data['npu'])) == 8
    assert data['containers']
    assert not data['errors'], data['errors']
    for p in data['processes'].values():
        if p.get('npu'):
            assert p['started'] and p['command']
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 32, 160, 0, 0))
    env = dict(os.environ, TERM='xterm-256color')
    proc = subprocess.Popen([sys.executable, str((Path(__file__).resolve().parents[1] / 'server_look/remote/npu_top.py')),
                             '--read-only', '--interval', '2'],
                            stdin=slave, stdout=slave, stderr=slave, env=env)
    os.close(slave)

    def expect(marker):
        output = b''
        deadline = time.monotonic() + 20
        while marker not in output and time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    output += os.read(master, 65536)
                except OSError:
                    break
            if proc.poll() is not None:
                break
        assert b'Traceback' not in output, output[-1500:]
        assert marker in output, (marker, output[-1500:])

    try:
        expect(b'NPU-TOP')
        os.write(master, b'\t')
        expect(b'native-a2')
        os.write(master, b'\n')
        expect(b'DETAILS')
        os.write(master, b'\na')
        expect(b'TASK STARTED')
        os.write(master, b'k')
        expect(b'Read-only mode: kill disabled')
        os.write(master, b'q')
        assert proc.wait(timeout=15) == 0
        print('Interactive PTY smoke: PASS (Docker, details, container tasks, read-only kill guard, exit)')
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)
        os.close(master)


if __name__ == '__main__':
    main()
