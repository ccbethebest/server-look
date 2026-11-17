"""Close the selected Python tab and recover the shell-to-editor bridge."""
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tests.test_terminal_recovery import TerminalRecoveryTests
from server_look.transport.terminal_editor import EditorBridge, editor_command, editor_setup


class SessionEditorFixTests(TerminalRecoveryTests):
    def test_setup_echo_is_hidden_by_ui_and_timeout_keeps_terminal_usable(self):
        self.item['session'].events.put(('ready', ''))
        self.poll()
        setup = self.item['session'].send.call_args.args[0]
        self.item['session'].events.put(('data', setup + '\nroot# pwd\r\n/root\r\n'))
        self.poll()
        visible = self.item['output'].get('1.0', 'end')
        self.assertNotIn('__SL_BEGIN_', visible)
        self.assertNotIn('unalias', visible)
        self.assertIn('/root', visible)
        with patch('server_look.transport.terminal_editor.time.monotonic', return_value=0):
            self.item['session'].events.put(('data', setup[:180]))
            self.poll()
        with patch('server_look.transport.terminal_editor.time.monotonic', return_value=10):
            self.poll()
        self.assertIn('__SL_BEGIN_', self.item['output'].get('1.0', 'end'))
        self.panel.send(self.item, 'pwd\r')
        self.item['session'].send.assert_called_with('pwd\r')

    def test_close_button_removes_python_and_keeps_shell_usable(self):
        shell = self.item
        self.panel.new_python()
        python = list(self.panel.sessions.values())[-1]
        self.panel.actions[2].invoke()
        self.assertTrue(python['ended'])
        self.assertFalse(python['frame'].winfo_exists())
        python['session'].close.assert_called_once()
        shell['session'].close.assert_not_called()
        self.assertEqual(self.panel.tabs.select(), str(shell['frame']))
        shell['ready'] = True
        self.panel.send(shell, 'pwd\r')
        shell['session'].send.assert_called_once_with('pwd\r')
        self.panel.actions[2].invoke()
        self.panel.actions[2].invoke()  # An empty notebook is safe to close again.
        self.assertFalse(self.panel.sessions)

    def test_command_entry_reinstalls_bridge_and_routes_fragmented_request(self):
        self.item['ready'] = True
        self.panel.page.resources = MagicMock()
        self.item['command_entry'].insert(0, 'vim "中文 notes.txt"')
        self.panel.execute_command(self.item)
        sent = self.item['session'].send.call_args.args[0]
        self.assertIn('vim()', sent)
        self.assertTrue(sent.endswith('; vim "中文 notes.txt"\r'))
        request = self.item['editor_bridge'].prefix + '@/tmp/中文 notes.txt\x07'
        for part in (request[:3], request[3:30], request[30:]):
            self.item['session'].events.put(('data', part))
            self.poll()
        self.panel.page.resources.editors.open.assert_called_once_with('/tmp/中文 notes.txt', remote=True)

    def test_visual_return_replaces_whole_command_even_with_cursor_in_middle(self):
        self.item['ready'] = True
        screen, line = self.item['screen'], self.item['shell_line']
        self.item['stream'].feed('root# ')
        line.record(screen, 'vim notes.txt')
        self.item['stream'].feed('vim notes.txt')
        line.record(screen, '\x1b[D')
        self.item['stream'].feed('\x1b[D')
        self.assertTrue(line.matches(screen))
        self.panel.keypress(SimpleNamespace(keysym='Return', char='\r', state=0), self.item)
        sent = self.item['session'].send.call_args.args[0]
        self.assertTrue(sent.startswith('\x05\x15: __SL_BEGIN_'))
        self.assertTrue(sent.endswith('; vim notes.txt\r'))

    def test_container_prompt_with_application_cursor_still_opens_editor(self):
        self.item['ready'] = True
        self.item['stream'].feed('\x1b[?1h(base) [root@container ~]# ')
        for char in 'vim /tmp/container.txt':
            self.panel.keypress(SimpleNamespace(keysym=char, char=char, state=0), self.item)
            self.item['stream'].feed(char)
        self.panel.keypress(SimpleNamespace(keysym='Return', char='\r', state=0), self.item)
        sent = self.item['session'].send.call_args.args[0]
        self.assertTrue(sent.startswith('\x05\x15: __SL_BEGIN_'), repr(sent))
        self.assertTrue(sent.endswith('; vim /tmp/container.txt\r'))
        self.panel.page.resources = MagicMock()
        context = dict(boot='boot-fixture', namespace='mnt:[42]', uid='0', gid='0')
        request = self.item['editor_bridge'].prefix + '!boot-fixture|mnt:[42]|0|0|/tmp/container.txt\x07'
        self.item['session'].events.put(('data', request))
        self.poll()
        self.panel.page.resources.editors.open.assert_called_once_with(
            '/tmp/container.txt', remote=True, context=context)

    def test_python_at_application_cursor_prompt_also_restores_bridge(self):
        self.item['ready'] = True
        self.item['stream'].feed('\x1b[?1hroot@container:~# ')
        for char in 'python3':
            self.panel.keypress(SimpleNamespace(keysym=char, char=char, state=0), self.item)
            self.item['stream'].feed(char)
        self.panel.keypress(SimpleNamespace(keysym='Return', char='\r', state=0), self.item)
        sent = self.item['session'].send.call_args.args[0]
        self.assertTrue(sent.startswith('\x05\x15: __SL_BEGIN_'), repr(sent))
        self.assertTrue(sent.endswith('; python3\r'))

    def test_fullscreen_editor_keeps_return_and_does_not_inject_shell_code(self):
        self.item['ready'] = True
        self.item['stream'].feed('\x1b[?1049h\x1b[?1h')
        for char in 'vim /tmp/container.txt':
            self.panel.keypress(SimpleNamespace(keysym=char, char=char, state=0), self.item)
            self.item['stream'].feed(char)
        self.panel.keypress(SimpleNamespace(keysym='Return', char='\r', state=0), self.item)
        self.item['session'].send.assert_called_with('\r')

    def test_recovery_uses_current_directory_and_overrides_broken_function(self):
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        shell = str(bash) if bash.exists() else '/bin/bash'
        command = editor_command('vim "notes with spaces.txt"', 'recovery')
        result = subprocess.run([shell, '--noprofile', '--norc'],
                                input='vim() { printf BROKEN; }\ncd /\n' + command + '\nprintf READY',
                                text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        text, paths = EditorBridge('recovery').feed(result.stdout)
        self.assertEqual([request['path'] for request in paths], ['/notes with spaces.txt'])
        self.assertEqual(text, 'READY')

    def test_native_editor_and_other_commands_are_preserved(self):
        for command in ('command vim notes.txt', 'pwd',
                        'cd /tmp', 'export NAME=value', 'ls -la | head -n 3',
                        'printf hello > notes.txt', 'cat < notes.txt', 'sleep 1 &',
                        'false; echo $?', 'echo "中文"', 'sudo whoami', 'docker ps'):
            self.assertEqual(editor_command(command, 'fixture'), command)

    def test_basic_shell_commands_match_without_editor_bridge(self):
        import tempfile
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        shell = str(bash) if bash.exists() else '/bin/bash'
        commands = ['cd /', 'pwd', 'export SERVER_LOOK_TEST=value',
                    'printf "%s\\n" "$SERVER_LOOK_TEST"',
                    'printf "one\\ntwo\\n" | head -n 1',
                    'false; printf "exit=%s\\n" "$?"',
                    'printf "中文\\n"', 'printf data > sample.txt', 'cat < sample.txt']
        outputs = []
        for bridge in (False, True):
            with tempfile.TemporaryDirectory() as folder:
                # Use the temporary directory for redirect tests, then exercise cd.
                script = commands[2:] + commands[:2]
                if bridge:
                    script = [editor_setup('fixture')] + [editor_command(c, 'fixture') for c in script]
                result = subprocess.run([shell, '--noprofile', '--norc'], cwd=folder,
                                        input='\n'.join(script), text=True, encoding='utf-8',
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((Path(folder) / 'sample.txt').read_text(), 'data')
                outputs.append((result.stdout, result.stderr))
        self.assertEqual(outputs[0], outputs[1])
        self.assertIn('value\none\nexit=1\n中文\ndata/', outputs[1][0])
