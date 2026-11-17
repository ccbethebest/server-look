"""Editing must follow the terminal namespace, never a same-named host file."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from server_look.remote import file_editor as editor
from server_look.transport.terminal_editor import EditorBridge


CONTEXT = dict(boot='boot', namespace='mnt:[42]', uid='0', gid='0')


class ContainerEditorTests(unittest.TestCase):
    def test_worker_roundtrip_and_external_change_conflict(self):
        real_run = subprocess.run
        source = Path('server_look/remote/file_editor.py').read_text(encoding='utf-8')
        source += '\neditor_identity = lambda: ' + repr(CONTEXT) + '\n'
        def run(args, **kwargs):
            if args[1] == 'ps':
                return subprocess.CompletedProcess(args, 0, 'a' * 64, '')
            if args[1] == 'inspect':
                data = [dict(Id='a' * 64, State=dict(Pid=321), Name='/training')]
                return subprocess.CompletedProcess(args, 0, json.dumps(data), '')
            # Run the exact generated Python worker, replacing only Docker transport.
            return real_run([sys.executable, '-c', args[-1]], env=dict(os.environ, PYTHONIOENCODING='utf-8'), **kwargs)
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(editor, 'editor_identity', return_value=dict(CONTEXT, namespace='mnt:[1]')), \
                patch.object(editor.os, 'readlink', return_value='mnt:[42]'), \
                patch.object(subprocess, 'run', side_effect=run):
            path = Path(folder) / 'container-only.txt'
            path.write_text('before', encoding='utf-8')
            document = editor.edit_in_context(CONTEXT, dict(path=str(path)), source)
            self.assertEqual(document.pop('text'), 'before')
            document.pop('location')
            editor.edit_in_context(CONTEXT, dict(path=str(path), text='after', **document), source)
            self.assertEqual(path.read_text(encoding='utf-8'), 'after')
            with self.assertRaisesRegex(ValueError, '外部修改'):
                editor.edit_in_context(CONTEXT, dict(path=str(path), text='stale', **document), source)
            self.assertEqual(path.read_text(encoding='utf-8'), 'after')

    def test_fragmented_context_preserves_path(self):
        message = '\x1b]777;server-look;t;!boot|mnt:[42]|0|0|/tmp/中文|x.txt\x07'
        bridge = EditorBridge('t')
        requests = []
        for char in message:
            visible, found = bridge.feed(char)
            self.assertFalse(visible)
            requests.extend(found)
        self.assertEqual(requests, [dict(path='/tmp/中文|x.txt', context=CONTEXT)])

    def test_container_read_and_save_use_same_context_and_numeric_user(self):
        calls = []
        def run(args, **kwargs):
            calls.append((args, kwargs))
            if args[1] == 'ps':
                output = 'a' * 64
            elif args[1] == 'inspect':
                output = json.dumps([dict(Id='a' * 64, State=dict(Pid=321), Name='/training')])
            else:
                payload = json.loads(kwargs['input'])
                self.assertEqual(payload['context'], CONTEXT)
                self.assertEqual(payload['options']['path'], '/tmp/model.py')
                output = json.dumps(dict(text='container contents', digest='abc'))
            return subprocess.CompletedProcess(args, 0, output, '')
        with patch.object(editor, 'editor_identity', return_value=dict(CONTEXT, namespace='mnt:[1]')), \
                patch.object(editor.os, 'readlink', return_value='mnt:[42]'), \
                patch.object(subprocess, 'run', side_effect=run), \
                patch.object(editor, 'edit_file', side_effect=AssertionError('host accessed')):
            for options in (dict(path='/tmp/model.py'), dict(path='/tmp/model.py', text='saved', digest='abc')):
                result = editor.edit_in_context(CONTEXT, options, 'source')
                self.assertIn('training', result['location'])
        commands = [args for args, _ in calls if args[1] == 'exec']
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][2:6], ['-i', '--user', '0:0', 'a' * 64])

    def test_foreign_host_missing_container_and_changed_identity_fail_closed(self):
        with patch.object(editor, 'editor_identity', return_value=dict(CONTEXT, boot='other')), \
                patch.object(editor, 'edit_file') as host:
            with self.assertRaisesRegex(ValueError, '服务器'):
                editor.edit_in_context(CONTEXT, dict(path='/tmp/a'), '')
            host.assert_not_called()
        with patch.object(editor, 'editor_identity', return_value=dict(CONTEXT, namespace='mnt:[1]')), \
                patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '', '')):
            with self.assertRaisesRegex(ValueError, '容器'):
                editor.edit_in_context(CONTEXT, dict(path='/tmp/a'), '')
        source = Path('server_look/remote/file_editor.py').read_text(encoding='utf-8')
        program = source + '\nimport json,sys\np=json.load(sys.stdin)\nverify_editor_identity(p["context"])\n'
        result = subprocess.run([sys.executable, '-c', program], input=json.dumps(dict(context=CONTEXT)),
                                text=True, capture_output=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('身份', result.stderr)
