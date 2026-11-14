import importlib.util
import signal
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('npu_top', Path(__file__).with_name('npu_top.py'))
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class MonitorTests(unittest.TestCase):
    def test_docker_nanoseconds_supported_on_python310(self):
        self.assertRegex(app.docker_stamp('2026-11-11T07:37:38.802079004Z'),
                         r'^2026-11-11 \d\d:\d\d:\d\d [+-]\d{4}$')

    def test_npu_process_table_deduplicates_pid_across_cards(self):
        raw = '''| 0 910B4 | OK | 90 40 |
| NPU Chip | Process id | Process name | Process memory(MB) |
| 0 0 | 123 | python | 2048 |
| 1 0 | 123 | python | 4096 |
| 2 0 | 456 | worker | 512 |
| No running processes found in NPU 3 |'''
        self.assertEqual(app.parse_npu_processes(raw), {
            123: {'0:0': 2048, '1:0': 4096}, 456: {'2:0': 512}})

    def test_stat_handles_spaces_and_parentheses_in_process_name(self):
        fields = ['S', '7'] + ['0'] * 17 + ['12345', '0']
        self.assertEqual(app.parse_stat('42 (worker (a) b) ' + ' '.join(fields)), (7, 12345))

    def test_tree_excludes_siblings(self):
        procs = {10: {'ppid': 1}, 11: {'ppid': 10}, 12: {'ppid': 11}, 20: {'ppid': 1}}
        self.assertEqual(app.process_tree(10, procs), [12, 11, 10])

    def test_container_cgroup_v1_and_v2(self):
        cid = 'a' * 64
        for text in [f'0::/system.slice/docker-{cid}.scope', f'12:memory:/docker/{cid}']:
            self.assertEqual(app.container_id(text, {cid: {}}), cid)
        self.assertIsNone(app.container_id('0::/init.scope', {cid: {}}))

    def test_changed_pid_is_never_signalled(self):
        with patch.object(app, 'read_process', return_value={'ticks': 999}), \
                patch.object(app.os, 'pidfd_open', create=True) as opened:
            with self.assertRaises(RuntimeError):
                app.signal_tree({'pid': 43210, 'ticks': 123}, signal.SIGTERM)
            opened.assert_not_called()

    def test_self_cannot_be_killed(self):
        with self.assertRaisesRegex(RuntimeError, 'Refusing'):
            app.signal_tree(app.read_process(os.getpid()), signal.SIGTERM)

    def test_telemetry_compacts_card_and_chip_rows(self):
        raw = '''| 0 910B4-1 | OK | 93.2 40 0 / 0 |
| 0 | 0000:C1:00.0 | 0 0 / 0 3450 / 65536 |
| NPU Chip | Process id | Process name | Process memory(MB) |
| 0 0 | 123 | python | 100 |'''
        lines = app.telemetry_lines(raw)
        self.assertEqual(len(lines), 1)
        self.assertIn('HBM 3450/65536MB', lines[0])
        self.assertIn('Core 0%', lines[0])

    def test_real_signals_only_affect_selected_tree(self):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with self.subTest(signal=sig):
                program = ('import subprocess,sys,time; '
                           'p=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                           'print(p.pid,flush=True); time.sleep(60)')
                root = subprocess.Popen([sys.executable, '-c', program], stdout=subprocess.PIPE, text=True)
                unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
                child = int(root.stdout.readline())
                try:
                    result = app.signal_tree(app.read_process(root.pid), sig)
                    self.assertIn('2 process(es)', result)
                    self.assertEqual(root.wait(timeout=3), -sig)
                    self.assertIsNone(unrelated.poll())
                    deadline = time.monotonic() + 3
                    while time.monotonic() < deadline:
                        try:
                            state = Path(f'/proc/{child}/stat').read_text().rsplit(')', 1)[1].split()[0]
                        except FileNotFoundError:
                            break
                        if state == 'Z':
                            break
                        time.sleep(0.02)
                    else:
                        self.fail('Child still running after tree signal')
                finally:
                    if root.poll() is None:
                        root.kill()
                    root.wait()
                    root.stdout.close()
                    unrelated.terminate()
                    unrelated.wait()
                    try:
                        os.kill(child, signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
