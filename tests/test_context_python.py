"""Python windows retain their originating shell and interpreter lifecycle."""
from server_look.transport.terminal_editor import EditorBridge, editor_command
from tests.test_terminal_recovery import TerminalRecoveryTests
import os
from pathlib import Path
import subprocess
import unittest


class ContextPythonTests(TerminalRecoveryTests):
    def marker(self, value):
        return self.item['editor_bridge'].prefix + '?' + value + '\x07'

    def test_window_executes_multiline_on_original_session_and_returns_to_shell(self):
        self.item['ready'] = True
        self.item['session'].events.put(('data', self.marker('python') + '>>> '))
        self.poll()
        window = self.item['python_window']
        window.editor.insert('1.0', 'x = 3\nprint(x)')
        window.execute()
        self.assertIn('x = 3', self.item['session'].send.call_args.args[0])
        self.assertIn('print(x)', self.item['session'].send.call_args.args[0])
        self.item['session'].events.put(('data', '3\r\n' + self.marker('end') + 'root# '))
        self.poll()
        self.assertIn('3', window.output.get('1.0', 'end'))
        self.assertFalse(window.active)
        self.assertIsNone(self.item.get('python_window'))
        self.assertIn('root#', self.item['output'].get('1.0', 'end'))
        window.destroy()

    def test_close_window_requests_exit_and_close_session_destroys_window(self):
        self.item['ready'] = True
        self.item['session'].events.put(('data', self.marker('python')))
        self.poll()
        window = self.item['python_window']
        window.close()
        window.window.after_cancel(window.exit_job)
        window.request_exit()
        self.assertIn('SystemExit', self.item['session'].send.call_args.args[0])
        self.panel.close_current()
        self.assertFalse(window.window.winfo_exists())

    def test_python_command_only_intercepts_bare_interpreter(self):
        self.assertNotEqual(editor_command('python3', 'test'), 'python3')
        for command in ('python3 job.py', 'python -m pip list', 'python -c "print(1)"'):
            self.assertEqual(editor_command(command, 'test'), command)

    def test_protocol_preserves_start_output_end_order(self):
        result = EditorBridge('a').feed_events('before\x1b]777;server-look;a;?python\x07'
                                              'inside\x1b]777;server-look;a;?end\x07after')
        self.assertEqual([event for event in result if event[1] != ''],
                         [('text', 'before'), ('python', True), ('text', 'inside'),
                          ('python', False), ('text', 'after')])


class RealInterpreterTests(unittest.TestCase):
    def test_shell_environment_and_multiline_state_are_retained(self):
        from server_look.transport.terminal_editor import editor_setup
        from server_look.transport.terminal import python_command
        bash = Path('C:/Program Files/Git/bin/bash.exe')
        shell = str(bash) if bash.exists() else '/bin/bash'
        program = editor_setup('actual') + 'export SERVER_LOOK_TEST_ENV=container_fixture; python; printf SHELL_RETURNED'
        source = 'import os\nx = 41\nprint(os.environ["SERVER_LOOK_TEST_ENV"], x + 1)'
        result = subprocess.run([shell, '--noprofile', '--norc', '-c', program],
                                input=python_command(source) + 'raise SystemExit\n',
                                env=dict(os.environ, PYTHONIOENCODING='utf-8'),
                                text=True, capture_output=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        events = EditorBridge('actual').feed_events(result.stdout)
        self.assertIn(('python', True), events)
        self.assertIn(('python', False), events)
        self.assertIn('container_fixture 42', ''.join(value for kind, value in events if kind == 'text'))
        self.assertEqual(events[-1], ('text', 'SHELL_RETURNED'))
