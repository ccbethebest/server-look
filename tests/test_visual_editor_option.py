"""Visual editing is optional, and accepts text independently of filename."""
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

from tests.test_terminal_recovery import TerminalRecoveryTests
from server_look.remote.file_editor import edit_file
from server_look.transport.terminal_editor import EditorBridge, editor_command


class VisualEditorOptionTests(TerminalRecoveryTests):
    def test_default_and_toggle_apply_to_command_entry_and_direct_input(self):
        self.assertTrue(self.panel.visual_editor.get())
        self.item['ready'] = True
        self.panel.visual_editor.set(False)
        self.item['command_entry'].insert(0, 'vim notes.txt')
        self.panel.execute_command(self.item)
        self.assertIn('command vim', self.item['session'].send.call_args.args[0])
        self.assertNotIn('!%s', self.item['session'].send.call_args.args[0])
        self.item['stream'].feed('root# ')
        for char in 'vi script.py':
            self.panel.keypress(SimpleNamespace(keysym=char, char=char, state=0), self.item)
            self.item['stream'].feed(char)
        self.panel.keypress(SimpleNamespace(keysym='Return', char='\r', state=0), self.item)
        self.assertNotIn('!%s', self.item['session'].send.call_args.args[0])

    def test_real_shell_visual_multiple_files_and_native_passthrough(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        shell = str(bash) if bash.exists() else '/bin/bash'
        visual = editor_command('vim -p -- "a b.py" script.sh', 'option')
        native = editor_command('vim "a b.py"', 'option', visual=False)
        # A shell executable fixture proves disabled mode reaches the native command.
        with tempfile.TemporaryDirectory() as folder:
            executable = Path(folder) / 'vim'
            executable.write_text('#!/bin/sh\nprintf "NATIVE:%s" "$1"\n', encoding='utf-8')
            executable.chmod(0o755)
            result = subprocess.run([shell, '--noprofile', '--norc'], cwd=folder,
                                    input='PATH="$PWD:$PATH"\n' + visual + '\n' + native,
                                    text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        visible, requests = EditorBridge('option').feed(result.stdout)
        self.assertEqual([Path(r['path']).name for r in requests], ['a b.py', 'script.sh'])
        self.assertEqual(visible, 'NATIVE:a b.py')

    def test_text_scripts_and_new_files_preserve_conflict_protection(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'script.cmd'
            path.write_text('echo hello', encoding='utf-8')
            path.chmod(0o755)
            self.assertEqual(edit_file(path)['text'], 'echo hello')
            path = Path(folder) / 'new.py'
            document = edit_file(path)
            self.assertFalse(path.exists())
            document.pop('text')
            edit_file(path, text='print(1)', **document)
            self.assertEqual(path.read_text(), 'print(1)')
            with self.assertRaisesRegex(ValueError, '修改|创建'):
                edit_file(path, text='overwrite', **document)
