#!/usr/bin/env python3
"""Ascend NPU / Docker task monitor. Python 3.9+, Linux host, no dependencies."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import json
import os
from pathlib import Path
import pwd
import re
import select
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time
import unicodedata


class Terminal:
    """Small ANSI terminal adapter; works even when Python has no _curses module."""
    KEY_UP, KEY_DOWN, KEY_ENTER = 1001, 1002, 10
    A_REVERSE, A_NORMAL = True, False

    def __enter__(self):
        import termios
        import tty
        self.fd = sys.stdin.fileno()
        self.saved = termios.tcgetattr(self.fd)
        self.input = b''
        self.lines = {}
        tty.setcbreak(self.fd)
        sys.stdout.write('\x1b[?1049h\x1b[?25l')
        sys.stdout.flush()
        return self

    def __exit__(self, *exc):
        import termios
        termios.tcsetattr(self.fd, termios.TCSADRAIN, self.saved)
        sys.stdout.write('\x1b[0m\x1b[?25h\x1b[?1049l')
        sys.stdout.flush()

    def getmaxyx(self):
        size = os.get_terminal_size(sys.stdout.fileno())
        return size.lines, size.columns

    def erase(self):
        self.lines = {}

    def addnstr(self, y, x, text, width, highlight):
        fitted, used = [], 0
        for char in text:
            cells = 0 if unicodedata.combining(char) else (2 if unicodedata.east_asian_width(char) in 'WF' else 1)
            if used + cells > width:
                break
            fitted.append(char)
            used += cells
        self.lines[y] = ('\x1b[7m' if highlight else '') + ''.join(fitted) + '\x1b[0m'

    def refresh(self):
        height, _ = self.getmaxyx()
        output = ''.join(f'\x1b[{y + 1};1H{self.lines.get(y, "")}\x1b[K' for y in range(height))
        sys.stdout.write(output)
        sys.stdout.flush()

    def getch(self):
        if not self.input:
            if not select.select([self.fd], [], [], 0.1)[0]:
                return -1
            self.input = os.read(self.fd, 128)
            if not self.input:
                return ord('q')
        if self.input.startswith(b'\x1b'):
            if len(self.input) < 3 and select.select([self.fd], [], [], 0.03)[0]:
                self.input += os.read(self.fd, 128)
            for sequence, key in ((b'\x1b[A', self.KEY_UP), (b'\x1b[B', self.KEY_DOWN),
                                  (b'\x1bOA', self.KEY_UP), (b'\x1bOB', self.KEY_DOWN)):
                if self.input.startswith(sequence):
                    self.input = self.input[len(sequence):]
                    return key
        key, self.input = self.input[0], self.input[1:]
        return key


def run(args, timeout=8):
    if args[0] in {'npu-smi', 'nvidia-smi'} and not shutil.which(args[0]):
        candidates = {
            'npu-smi': ('/usr/local/sbin/npu-smi', '/usr/local/Ascend/driver/tools/npu-smi'),
            'nvidia-smi': ('/usr/bin/nvidia-smi', '/usr/local/nvidia/bin/nvidia-smi'),
        }
        for path in candidates[args[0]]:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                args = [path, *args[1:]]
                break
    result = subprocess.run(args, capture_output=True, text=True, errors='replace', timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f'{args[0]} failed')
    return result.stdout


def parse_npu_processes(raw):
    tasks = {}
    in_processes = False
    for line in raw.splitlines():
        if 'Process id' in line:
            in_processes = True
        if not in_processes:
            continue
        match = re.match(r'\|\s*(\d+)(?:\s+(\d+))?\s*\|\s*(\d+)\s*\|[^|]*\|\s*(\d+)\s*\|', line)
        if match:
            card, chip, pid, memory = (int(value or 0) for value in match.groups())
            tasks.setdefault(pid, {})[f'{card}:{chip}'] = memory
    return tasks


def telemetry_lines(raw):
    result, card = [], None
    for line in raw.splitlines():
        if 'Process id' in line:
            break
        cells = [c.strip() for c in line.strip().strip('|').split('|')]
        if len(cells) != 3:
            continue
        first = re.fullmatch(r'(\d+)\s+(\S+)', cells[0])
        if first:
            metrics = cells[2].split()
            if len(metrics) >= 2:
                card = (first.group(1), first.group(2), cells[1], metrics[0], metrics[1])
        elif card and cells[0].isdigit():
            values = re.fullmatch(r'(\d+)\s+(\d+)\s*/\s*(\d+)\s+(\d+)\s*/\s*(\d+)', cells[2])
            if values:
                core, _, _, used, total = values.groups()
                number, name, health, power, temp = card
                result.append(f'{number}:{cells[0]} {name} {health:<8} Core {core}%  '
                              f'HBM {used}/{total}MB  {power}W {temp}C')
    return result


def parse_stat(raw):
    fields = raw[raw.rfind(')') + 2:].split()
    return int(fields[1]), int(fields[19])  # /proc/PID/stat fields 4 and 22


def read_process(pid):
    base = Path('/proc') / str(pid)
    try:
        ppid, ticks = parse_stat((base / 'stat').read_text(errors='replace'))
        argv = (base / 'cmdline').read_bytes().decode(errors='replace').strip('\0').split('\0')
        uid = base.stat().st_uid
        try:
            user = pwd.getpwuid(uid).pw_name
        except KeyError:
            user = str(uid)
        info = dict(pid=pid, ppid=ppid, ticks=ticks, user=user,
                    command=shlex.join(argv) if argv != [''] else
                    '[' + (base / 'comm').read_text(errors='replace').strip() + ': no cmdline / exiting]',
                    cgroup=(base / 'cgroup').read_text())
        # A PID can disappear and be reused while /proc files are being read.
        if parse_stat((base / 'stat').read_text(errors='replace'))[1] != ticks:
            return None
        return info
    except (OSError, ValueError, IndexError):
        return None


def processes():
    result = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            proc = read_process(int(entry.name))
            if proc:
                result[proc['pid']] = proc
    return result


def container_id(cgroup, containers):
    for cid in re.findall(r'(?<![0-9a-f])[0-9a-f]{64}(?![0-9a-f])', cgroup):
        if cid in containers:
            return cid
    return None


def process_tree(root, procs):
    children = {}
    for pid, proc in procs.items():
        children.setdefault(proc['ppid'], []).append(pid)
    result, seen = [], set()
    stack = [(root, False)]
    while stack:
        pid, visited = stack.pop()
        if visited:
            result.append(pid)
        elif pid not in seen:
            seen.add(pid)
            stack.append((pid, True))
            stack.extend((child, False) for child in children.get(pid, []))
    return result


def protected_pids(procs):
    protected = {0, 1}
    pid = os.getpid()
    while pid in procs and pid not in protected:
        protected.add(pid)
        pid = procs[pid]['ppid']
    return protected


def signal_tree(selected, sig):
    """Validate PID/start ticks, then signal a snapshot of descendants via pidfds."""
    current = read_process(selected['pid'])
    if not current or current['ticks'] != selected['ticks']:
        raise RuntimeError('Task exited or PID was reused; refresh and select again')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('Safe kill requires Linux pidfd support (kernel 5.3+, Python 3.9+)')
    procs = processes()
    root = procs.get(selected['pid'])
    if not root or root['ticks'] != selected['ticks']:
        raise RuntimeError('Task changed while taking process snapshot')
    targets = process_tree(selected['pid'], procs)
    if protected_pids(procs).intersection(targets):
        raise RuntimeError('Refusing to stop PID 1, this monitor, or its ancestors')
    handles = []
    try:
        for pid in targets:
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                if pid == selected['pid']:
                    raise RuntimeError('Selected task has exited')
                continue
            handles.append(fd)
            fresh = read_process(pid)
            if not fresh or fresh['ticks'] != procs[pid]['ticks']:
                raise RuntimeError('Process tree changed; refresh and retry')
        sent = 0
        for fd in handles:
            try:
                signal.pidfd_send_signal(fd, sig)
                sent += 1
            except ProcessLookupError:
                pass
        return f'Sent {signal.Signals(sig).name} to {sent} process(es)'
    finally:
        for fd in handles:
            os.close(fd)


def stamp(epoch):
    return dt.datetime.fromtimestamp(epoch).astimezone().strftime('%Y-%m-%d %H:%M:%S %z')


def docker_stamp(text):
    # Docker uses RFC3339 with up to nanosecond precision; datetime accepts microseconds.
    text = re.sub(r'(\.\d{6})\d+', r'\1', text)
    return stamp(dt.datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp())


def collect_accelerators():
    """Probe both vendors independently; keep UUIDs for NVIDIA process association."""
    import csv
    import io
    raw_parts, tasks, hardware, errors = [], {}, {}, []
    available = False
    try:
        raw = run(['npu-smi', 'info'])
        available = True
        raw_parts.append(raw)
        tasks.update(parse_npu_processes(raw))
    except FileNotFoundError:
        pass
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        errors.append('npu-smi: ' + str(exc))
    fields = 'index,uuid,name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw'
    try:
        raw = run(['nvidia-smi', '--query-gpu=' + fields, '--format=csv,noheader,nounits'])
        available = True
        rows = list(csv.reader(io.StringIO(raw), skipinitialspace=True))
        mapping = {}
        display = ['NVIDIA GPU：序号 | 型号 | 显存 MiB | 利用率 % | 温度 °C | 功耗 W']
        models = set()
        for row in rows:
            if len(row) != 9:
                raise ValueError('nvidia-smi 返回了无法识别的设备数据')
            index, uuid, model, driver, total, used, util, temp, power = [v.strip() for v in row]
            mapping[uuid] = 'GPU ' + index
            models.add(model)
            hardware['GPU ' + index] = f'{model} · UUID {uuid} · 驱动 {driver} · 显存 {total} MiB'
            display.append(f'{index} | {model} | {used}/{total} | {util} | {temp} | {power}')
        hardware.update({'GPU 数量': str(len(rows)), 'GPU 型号': ', '.join(sorted(models)) or '未检测到设备'})
        raw_parts.append('\n'.join(display))
        try:
            processes_raw = run(['nvidia-smi', '--query-compute-apps=gpu_uuid,pid,used_gpu_memory', '--format=csv,noheader,nounits'])
            for row in csv.reader(io.StringIO(processes_raw), skipinitialspace=True):
                if len(row) != 3 or not row[1].strip().isdigit():
                    continue
                uuid, pid, memory = [v.strip() for v in row]
                # MIG UUIDs remain distinct rather than being mapped to the wrong card.
                tasks.setdefault(int(pid), {})[mapping.get(uuid, uuid)] = int(memory) if memory.isdigit() else memory
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
            errors.append('NVIDIA 计算进程采集失败：' + str(exc))
    except FileNotFoundError:
        pass
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        errors.append('nvidia-smi: ' + str(exc))
    if not available:
        errors.append('未发现可用的 npu-smi / nvidia-smi，请检查驱动和命令路径')
    return '\n\n'.join(raw_parts), tasks, hardware, errors


def collect():
    """Collect host telemetry and all /proc processes; SSH applies its own filter."""
    raw, tasks, accelerator_hardware, errors = collect_accelerators()
    containers = {}
    try:
        ids = run(['docker', 'ps', '-q', '--no-trunc']).split()
        for item in json.loads(run(['docker', 'inspect', *ids])) if ids else []:
            containers[item['Id']] = dict(
                id=item['Id'], name=item['Name'].lstrip('/'), image=item['Config']['Image'],
                started=docker_stamp(item['State']['StartedAt']), created=docker_stamp(item['Created']),
                pid=item['State']['Pid'], command=shlex.join([item['Path'], *item.get('Args', [])]),
                restart=item['HostConfig']['RestartPolicy']['Name'],
                mounts=[f"{m['Source']} -> {m['Destination']}" for m in item.get('Mounts', [])])
    except (OSError, RuntimeError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        errors.append(f'Docker: {exc}')
    procs = processes()
    boot = next(int(line.split()[1]) for line in Path('/proc/stat').read_text().splitlines()
                if line.startswith('btime '))
    hz = os.sysconf('SC_CLK_TCK')
    for proc in procs.values():
        proc['container'] = container_id(proc['cgroup'], containers)
        proc['started'] = stamp(boot + proc['ticks'] / hz)
    # Parent fallback covers a cgroup namespace rooted below the Docker scope.
    for proc in procs.values():
        ancestor, visited = proc, set()
        while not proc['container'] and ancestor['pid'] not in visited:
            visited.add(ancestor['pid'])
            match = next((cid for cid, c in containers.items() if c['pid'] == ancestor['pid']), None)
            proc['container'] = match or ancestor['container']
            ancestor = procs.get(ancestor['ppid'])
            if ancestor is None:
                break
    for pid, devices in tasks.items():
        if pid in procs:
            procs[pid]['npu'] = devices
        else:
            errors.append(f'NPU PID {pid} disappeared or /proc is inaccessible')
    return dict(host=socket.gethostname(), time=stamp(time.time()), npu=raw,
                containers=containers, processes=procs, errors=errors, accelerator_hardware=accelerator_hardware)


def clean(text):
    # Commands can contain terminal escape/control sequences.
    return ''.join(c if c.isprintable() else ' ' for c in str(text))


def detail_lines(proc, data):
    result = [f"PID: {proc['pid']}   PPID: {proc['ppid']}   User: {proc['user']}",
              f"Task started: {proc['started']}", f"Command: {proc['command']}"]
    try:
        result.append(f"Working directory: {os.readlink('/proc/' + str(proc['pid']) + '/cwd')}")
    except OSError:
        pass
    cid = proc['container']
    if cid:
        c = data['containers'][cid]
        result += [f"Docker: {c['name']} ({cid[:12]})", f"Image: {c['image']}",
                   f"Docker started: {c['started']}", f"Docker created: {c['created']}",
                   f"Docker entrypoint: {c['command']}", f"Restart policy: {c['restart']}",
                   'Mounts: ' + '; '.join(c['mounts'])]
    ancestor = data['processes'].get(proc['ppid'])
    seen = {proc['pid']}
    while ancestor and ancestor['pid'] not in seen:
        seen.add(ancestor['pid'])
        result.append(f"Parent {ancestor['pid']} [{ancestor['started']}]: {ancestor['command']}")
        ancestor = data['processes'].get(ancestor['ppid'])
    return result


def dashboard(screen, args, worker):
    data, updated, selected, offset = None, 0, None, 0
    mode, details, status, armed = 'npu', False, '', None
    pending = None
    while True:
        if data is None:
            data = collect()
            updated = time.monotonic()
        elif not details:
            if pending is not None and pending.done():
                data = pending.result()
                pending = None
                updated = time.monotonic()
            if pending is None and time.monotonic() - updated >= args.interval:
                pending = worker.submit(collect)
        procs = data['processes']
        if mode == 'docker':
            rows = list(data['containers'].values())
            identities = [c['id'] for c in rows]
        else:
            rows = sorted((p for p in procs.values() if p.get('npu') or
                           (mode == 'all' and p['container'] and p['command'])), key=lambda p: p['pid'])
            # Keep a chosen launcher visible after pressing p.
            if selected and selected[0] in procs and selected not in [(p['pid'], p['ticks']) for p in rows]:
                p = procs[selected[0]]
                if p['ticks'] == selected[1]:
                    rows.insert(0, p)
            identities = [(p['pid'], p['ticks']) for p in rows]
        if selected is None and identities:
            selected = identities[0] if identities else None
        index = identities.index(selected) if selected in identities else -1
        item = rows[index] if index >= 0 else None
        if selected is not None and item is None:
            status = 'Selected task exited. Use Up/Down to select again; kill keys are inactive.'
            details = False
        height, width = screen.getmaxyx()
        screen.erase()

        def put(y, text, highlight=False):
            if 0 <= y < height and width > 1:
                screen.addnstr(y, 0, clean(text), width - 1, highlight)

        put(0, f"NPU-TOP  {data['host']}  {data['time']}  [{mode}]  interval={args.interval:g}s"
            + (' sampling...' if pending else ''))
        put(1, 'Up/Down select | k TERM tree | K KILL tree | s stop Docker (press twice)')
        put(2, 'Tab NPU/Docker | a container tasks | p parent | Enter details | r refresh | q quit')
        content = []
        if details and item:
            content = detail_lines(item, data) if mode != 'docker' else [f'{k}: {v}' for k, v in item.items()]
            content = [part for line in content for part in (textwrap.wrap(clean(line), max(10, width - 2)) or [''])]
            put(3, 'DETAILS (refresh paused) | Up/Down scroll | Enter/Esc back')
        else:
            if mode != 'docker':
                content.extend(telemetry_lines(data['npu']))
            content.append('NAME / ID       STARTED                         IMAGE' if mode == 'docker' else
                           'PID      USER         NPU:CHIP(MB)       TASK STARTED               DOCKER / COMMAND')
            for row in rows:
                if mode == 'docker':
                    content.append(f"{row['name']} / {row['id'][:12]}  {row['started']}  {row['image']}")
                else:
                    devices = ','.join(f'{d}({m})' for d, m in row.get('npu', {}).items()) or '-'
                    c = data['containers'].get(row['container'], {})
                    content.append(f"{row['pid']:<8} {row['user']:<12} {devices:<18} {row['started']}  "
                                   f"{c.get('name', 'host')} / {row['command']}")
            if not rows:
                content.append('No NPU tasks. Tab: running Docker containers; a: container processes.')
            table_start = len(content) - len(rows) if rows else len(content)
            target_line = table_start + index
            visible = max(1, height - 6)
            if target_line < offset:
                offset = target_line
            elif target_line >= offset + visible:
                offset = target_line - visible + 1
        offset = max(0, min(offset, max(0, len(content) - max(1, height - 6))))
        for n, line in enumerate(content[offset:offset + max(1, height - 6)]):
            put(4 + n, line, not details and bool(rows) and offset + n == target_line)
        put(height - 2, '; '.join(data['errors']) or 'k/K affect selected PID + current descendants; p selects launcher. No process-group kill.')
        put(height - 1, status or 'Enter: full command, start time, parent chain, image, entrypoint and mounts')
        screen.refresh()
        key = screen.getch()
        if key in (ord('q'), 3):
            return
        if key == -1:
            continue
        if key not in (ord('s'),):
            armed = None
        if key in (10, 13, 27):
            details = not details if key != 27 else False
            offset = 0
        elif key in (Terminal.KEY_UP, Terminal.KEY_DOWN):
            step = -1 if key == Terminal.KEY_UP else 1
            if details:
                offset += step
            elif identities:
                selected = identities[max(0, min(len(rows) - 1, index + step))]
        elif key in (9, ord('a')):
            mode = ('docker' if mode != 'docker' else 'npu') if key == 9 else ('npu' if mode == 'all' else 'all')
            selected, offset, details = None, 0, False
        elif key == ord('r'):
            updated = 0
            details = False
        elif key == ord('p') and item and mode != 'docker':
            parent = procs.get(item['ppid'])
            if parent and parent['pid'] not in protected_pids(procs):
                selected = (parent['pid'], parent['ticks'])
                details, offset = False, 0
            else:
                status = 'Parent is unavailable or protected'
        elif key in (ord('k'), ord('K')) and item and mode != 'docker':
            if args.read_only:
                status = 'Read-only mode: kill disabled'
                continue
            try:
                status = signal_tree(item, signal.SIGTERM if key == ord('k') else signal.SIGKILL)
            except (OSError, RuntimeError) as exc:
                status = f'Kill failed: {exc}'
            updated = 0
            details = False
        elif key == ord('s') and item:
            cid = item['id'] if mode == 'docker' else item['container']
            if args.read_only or not cid:
                status = 'Read-only mode or selected task has no Docker container'
            elif armed and armed[0] == cid and time.monotonic() - armed[1] < 3:
                try:
                    status = 'Stopped Docker: ' + run(['docker', 'stop', '--time', '10', cid], timeout=18).strip()
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    status = f'Docker stop: {exc}'
                armed, updated, details = None, 0, False
            else:
                armed = (cid, time.monotonic())
                status = f"Press s again within 3s to stop ALL tasks in {data['containers'][cid]['name']}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--interval', type=float, default=2, help='Refresh seconds (default: 2)')
    parser.add_argument('--once', action='store_true', help='Print one snapshot and exit')
    parser.add_argument('--json', action='store_true', help='Print snapshot as JSON and exit')
    parser.add_argument('--read-only', action='store_true', help='Disable kill and Docker stop keys')
    args = parser.parse_args()
    if not sys.platform.startswith('linux'):
        parser.error('Run on the Linux NPU host, outside Docker')
    if not 0.5 <= args.interval <= 3600:
        parser.error('--interval must be between 0.5 and 3600 seconds')
    if args.once or args.json:
        data = collect()
        if args.json:
            # Do not dump unrelated host commands into a monitoring snapshot.
            data['processes'] = {pid: p for pid, p in data['processes'].items() if p.get('npu') or p['container']}
            print(json.dumps(data, ensure_ascii=True, indent=2))
        else:
            print(f"{data['host']}  {data['time']}\n{data['npu']}")
            for proc in data['processes'].values():
                if proc.get('npu'):
                    print('\n'.join(clean(line) for line in detail_lines(proc, data)), '\n')
            print('RUNNING DOCKER CONTAINERS')
            for c in data['containers'].values():
                print(clean(f"{c['name']}  {c['id'][:12]}  started={c['started']}  image={c['image']}"))
            for error in data['errors']:
                print(clean(error), file=sys.stderr)
        return
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        parser.error('Interactive mode needs a TTY; use ssh -t, --once or --json')
    try:
        with Terminal() as screen, ThreadPoolExecutor(max_workers=1) as worker:
            dashboard(screen, args, worker)
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
