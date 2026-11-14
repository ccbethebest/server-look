import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

with patch.dict(sys.modules, {'pwd': types.ModuleType('pwd')} if sys.platform == 'win32' else {}):
    spec = importlib.util.spec_from_file_location('gpu_monitor', (Path(__file__).resolve().parents[1] / 'server_look/remote/npu_top.py'))
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)

class GpuTests(unittest.TestCase):
    def test_nvidia_hardware_and_multi_card_process(self):
        def run(args):
            if args[0] == 'npu-smi':
                raise FileNotFoundError()
            if args[1].startswith('--query-gpu='):
                return '0, GPU-a, NVIDIA A100, 550.1, 81920, 1024, 20, 40, 90\n1, GPU-b, NVIDIA H100, 550.1, 81920, 2048, 30, 50, 100\n'
            return 'GPU-a, 123, 1024\nGPU-b, 123, 2048\nGPU-a, 456, [N/A]\n'
        with patch.object(monitor, 'run', side_effect=run):
            raw, tasks, hardware, errors = monitor.collect_accelerators()
        self.assertFalse(errors)
        self.assertEqual(tasks[123], {'GPU 0': 1024, 'GPU 1': 2048})
        self.assertEqual(tasks[456]['GPU 0'], '[N/A]')
        self.assertEqual(hardware['GPU 数量'], '2')
        self.assertIn('GPU-a', hardware['GPU 0'])
        self.assertIn('1024/81920', raw)

    def test_950_process_table_without_chip_column(self):
        raw = '| NPU ID | Process id | Process name | Process memory(MB) | Process id in container |\n| 0 | 123 | VLLMWorker_DP | 74606 | NA |\n| 5 | 456 | python | 7870 | NA |'
        self.assertEqual(monitor.parse_npu_processes(raw), {123: {'0:0': 74606}, 456: {'5:0': 7870}})

    def test_driver_command_fallback_when_ssh_path_is_minimal(self):
        completed = types.SimpleNamespace(returncode=0, stdout='device data', stderr='')
        with patch.object(monitor.shutil, 'which', return_value=None), \
             patch.object(monitor.os.path, 'isfile', side_effect=lambda path: path == '/usr/local/sbin/npu-smi'), \
             patch.object(monitor.os, 'access', return_value=True), \
             patch.object(monitor.subprocess, 'run', return_value=completed) as execute:
            self.assertEqual(monitor.run(['npu-smi', 'info']), 'device data')
        self.assertEqual(execute.call_args.args[0], ['/usr/local/sbin/npu-smi', 'info'])

    def test_missing_tools_report_unavailable(self):
        with patch.object(monitor, 'run', side_effect=FileNotFoundError()):
            raw, tasks, hardware, errors = monitor.collect_accelerators()
        self.assertFalse(tasks)
        self.assertTrue(errors)

    def test_ascend_survives_missing_nvidia(self):
        raw = '| NPU Chip | Process id | Process name | Process memory(MB) |\n| 0 0 | 123 | python | 2048 |'
        with patch.object(monitor, 'run', side_effect=[raw, FileNotFoundError()]):
            _, tasks, _, errors = monitor.collect_accelerators()
        self.assertEqual(tasks[123], {'0:0': 2048})
        self.assertFalse(errors)
