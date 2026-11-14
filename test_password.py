import unittest
from unittest.mock import patch
from client_core import Connection

class PasswordTests(unittest.TestCase):
    def test_password_required(self):
        with self.assertRaises(ValueError):
            Connection('localhost', 'root', 22, auth_mode='password', password='')

    def test_password_not_in_command_and_session_reused(self):
        from password_transport import PasswordSession
        with patch('paramiko.SSHClient') as factory:
            session = PasswordSession('localhost', 'root', 22, 'secret')
            self.assertIs(session.client(), session.client())
            factory.return_value.connect.assert_called_once()
            options = factory.return_value.connect.call_args.kwargs
            self.assertFalse(options['allow_agent'])
            self.assertFalse(options['look_for_keys'])
            self.assertEqual(options['password'], 'secret')
            session.close()
            self.assertIsNone(session.password)
            with self.assertRaises(RuntimeError):
                session.client()

    def test_unknown_host_requires_confirmation_and_persists_only_after_accept(self):
        import tempfile
        from pathlib import Path
        import paramiko
        from password_transport import PasswordSession
        with tempfile.TemporaryDirectory() as folder, patch('password_transport.Path.home', return_value=Path(folder)):
            key = paramiko.RSAKey.generate(1024)
            session = PasswordSession('localhost', 'root', 2222, 'secret')
            with patch('paramiko.SSHClient') as factory:
                def connect(**kwargs):
                    policy = factory.return_value.set_missing_host_key_policy.call_args.args[0]
                    policy.missing_host_key(factory.return_value, '[localhost]:2222', key)
                factory.return_value.connect.side_effect = connect
                with self.assertRaisesRegex(RuntimeError, '指纹'):
                    session.client()
            self.assertIn('SHA256:', session.host_key_prompt())
            known = Path(folder) / '.ssh' / 'server_look_known_hosts'
            self.assertFalse(known.exists())
            pending = session.pending_host_key
            session.confirm_host_key(False)
            self.assertFalse(known.exists())
            self.assertIsNotNone(session.failure)
            session.pending_host_key = pending
            session.confirm_host_key(True)
            self.assertIsNone(session.failure)
            self.assertTrue(paramiko.HostKeys(str(known)).check('[localhost]:2222', key))

    def test_changed_host_key_never_offers_trust(self):
        import paramiko
        from password_transport import PasswordSession
        key = paramiko.RSAKey.generate(1024)
        with patch('paramiko.SSHClient') as factory:
            factory.return_value.connect.side_effect = paramiko.BadHostKeyException('localhost', key, key)
            session = PasswordSession('localhost', 'root', 22, 'secret')
            with self.assertRaisesRegex(RuntimeError, '密钥已变化'):
                session.client()
            self.assertIsNone(session.host_key_prompt())

    def test_auth_failure_is_not_retried(self):
        import paramiko
        from password_transport import PasswordSession
        with patch('paramiko.SSHClient') as factory:
            factory.return_value.connect.side_effect = paramiko.AuthenticationException('secret')
            session = PasswordSession('localhost', 'root', 22, 'secret')
            for _ in range(2):
                with self.assertRaisesRegex(RuntimeError, '认证失败') as error:
                    session.client()
                self.assertNotIn('secret', str(error.exception))
            self.assertEqual(factory.return_value.connect.call_count, 1)

if __name__ == '__main__':
    unittest.main()
