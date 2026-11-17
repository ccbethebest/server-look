"""Shell-to-editor bridge preserves shell expansion and current directory."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock
from server_look.transport.terminal_editor import EditorBridge, editor_setup
from tests.test_terminal_recovery import TerminalRecoveryTests


class EditorBridgeTests(unittest.TestCase):
    def test_split_messages_and_surrounding_terminal_output(self):
        bridge = EditorBridge('fixture')
        payload = json.dumps('/tmp/中文 notes.txt', ensure_ascii=True)
        message = '\x1b]777;server-look;fixture;' + payload + '\x07'
        visible, paths = '', []
        for char in 'before' + message + 'after':
            text, requests = bridge.feed(char)
            visible += text
            paths += requests
        self.assertEqual(visible, 'beforeafter')
        self.assertEqual(paths, ['/tmp/中文 notes.txt'])

    def test_other_sessions_and_malformed_messages_cannot_open_editor(self):
        bridge = EditorBridge('session-a')
        for payload in ('relative', '/tmp/a\x00b', 42):
            text, paths = bridge.feed('\x1b]777;server-look;session-a;' + json.dumps(payload) + '\x07')
            self.assertFalse(paths)
        text, paths = bridge.feed('\x1b]777;server-look;session-b;"/tmp/a"\x07ok')
        self.assertFalse(paths)
        self.assertTrue(text.endswith('ok'))

    def test_unterminated_request_is_bounded(self):
        bridge = EditorBridge('fixture')
        bridge.feed('\x1b]777;server-look;fixture;' + 'x' * 20000)
        self.assertLess(len(bridge.pending), 10000)

    def test_real_shell_resolves_quoted_filename_and_returns_to_prompt(self):
        import os
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        shell = str(bash) if bash.exists() else '/bin/bash'
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'notes $x.txt'
            path.write_text('original', encoding='utf-8')
            # Use the same Python as this test on Windows; production uses remote python3.
            import sys
            program = editor_setup('fixture', python=sys.executable.replace('\\', '/'))
            aliases = "alias vi='printf alias-vi' vim='printf alias-vim'\n"
            result = subprocess.run([shell, '--noprofile', '--norc', '-O', 'expand_aliases'],
                                    input=aliases + program + '\nvim "notes $x.txt"\nvi "notes $x.txt"\nprintf DONE',
                                    cwd=folder, env=dict(os.environ, x='$x'),
                                    text=True, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            text, paths = EditorBridge('fixture').feed(result.stdout)
            self.assertEqual(text.strip(), 'DONE')
            self.assertEqual([Path(item) for item in paths], [path, path])
            self.assertEqual(path.read_text(), 'original')


class EditorRoutingTests(TerminalRecoveryTests):
    def test_stale_or_readonly_session_cannot_open_editor(self):
        self.panel.page.resources = MagicMock()
        self.item['ready'] = True
        bridge = self.item['editor_bridge']
        request = '\x1b]777;server-look;' + bridge.token + ';"/tmp/a"\x07'
        self.panel.page.generation += 1
        self.item['session'].events.put(('data', request))
        self.poll()
        self.panel.page.generation = self.item['generation']
        self.panel.page.readonly.set(True)
        self.item['session'].events.put(('data', request))
        self.poll()
        self.panel.page.resources.editors.open.assert_not_called()

    def test_ready_installs_only_once_for_shell(self):
        self.item['session'].events.put(('ready', None))
        self.poll()
        self.item['session'].send.assert_called_once()
        self.assertIn('vim()', self.item['session'].send.call_args.args[0])

    def test_shell_editor_request_opens_existing_remote_editor(self):
        self.panel.page.resources = MagicMock()
        self.item['ready'] = True
        bridge = self.item['editor_bridge']
        self.item['session'].events.put(('data', '\x1b]777;server-look;' + bridge.token + ';"/tmp/notes.txt"\x07prompt> '))
        self.poll()
        self.panel.page.resources.editors.open.assert_called_once_with('/tmp/notes.txt', remote=True)
        self.assertIn('prompt>', self.item['output'].get('1.0', 'end'))

    def test_python_session_does_not_install_shell_functions(self):
        self.panel.new_python()
        item = list(self.panel.sessions.values())[-1]
        item['session'].events.put(('ready', None))
        self.poll()
        item['session'].send.assert_not_called()
