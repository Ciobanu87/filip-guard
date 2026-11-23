"""Run real Python gateway/engine against PHP companion with simulated WP/wpdb.

No network listener, WordPress installation or real database is involved.
"""
import json
import os
import select
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backup import BackupManager
from wordpress_autofix_engine import AutoFixEngine
from wordpress_rest_gateway import WordPressRESTGateway
from test_wordpress_companion_php import PHP, ROOT


class PHPBridge:
    def __init__(self):
        self.process = subprocess.Popen([PHP, '-n', str(ROOT / 'tests/php/companion_harness.php'), 'bridge'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        self.drop_next_write_reply = False
        self.connections = []

    def exchange(self, command):
        self.process.stdin.write(json.dumps(command) + '\n')
        self.process.stdin.flush()
        ready, _, _ = select.select([self.process.stdout], [], [], 5)
        if not ready:
            raise TimeoutError('PHP bridge fixture did not respond')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('PHP bridge fixture exited unexpectedly')
        return json.loads(line)

    def close(self):
        if self.process.poll() is None:
            try:
                self.exchange({'control': 'quit'})
            except (OSError, RuntimeError, ValueError):
                pass
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            stream.close()

    def connection(self, *args, **kwargs):
        bridge = self
        class Connection:
            result = b''
            closed = False
            def settimeout(self, timeout):
                assert timeout > 0
            def sendall(self, wire):
                header, body = wire.split(b'\r\n\r\n', 1)
                lines = header.decode().split('\r\n')
                method, path, _ = lines[0].split()
                headers = dict(line.split(': ', 1) for line in lines[1:])
                assert headers['Host'] == 'example.com'
                if body:
                    assert int(headers['Content-Length']) == len(body)
                result = bridge.exchange(dict(method=method, path=path,
                    authorization=headers['Authorization'], body=json.loads(body) if body else None))
                data = json.dumps(result['body']).encode()
                self.result = (f"HTTP/1.1 {result['status']} Result\r\nContent-Type: application/json\r\nContent-Length: {len(data)}\r\n\r\n".encode() + data)
                if method == 'POST' and bridge.drop_next_write_reply:
                    bridge.drop_next_write_reply = False
                    raise TimeoutError('Simulated lost reply after PHP write')
            def recv(self, size):
                data, self.result = self.result[:size], self.result[size:]
                return data
            def close(self):
                self.closed = True
        connection = Connection()
        self.connections.append(connection)
        return connection


@unittest.skipUnless(PHP, 'PHP runtime unavailable; cross-language tests are required in CI')
class PythonPHPIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bridge = PHPBridge()
        self.addCleanup(self.bridge.close)
        patcher = patch('wordpress_secure_https.create_verified_connection', side_effect=self.bridge.connection)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.gateway = WordPressRESTGateway('https://example.com', lambda: ('editor', 'fake password'))
        self.engine = AutoFixEngine(os.path.join(self.temp.name, 'engine.sqlite'),
            BackupManager(os.path.join(self.temp.name, 'backup.sqlite')), self.gateway)
        self.session = dict(user_id=7, session_id='p' * 43, now=100)

    def approved(self):
        plan = self.engine.propose(site_url='https://example.com', resource_type='post', resource_id=10,
            proposed_content='<p>Updated</p>', **self.session)['plan_id']
        return plan, self.engine.approve(plan, confirmed=True, **self.session)

    def test_approved_repair_through_actual_php_endpoint(self):
        plan, token = self.approved()
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self.bridge.exchange({'control': 'stats'})['queries'], 1)
        self.assertEqual(self.engine.backups.get_backup(result['backup_id'])['content'], '<p>Original</p>')
        self.assertTrue(all(connection.closed for connection in self.bridge.connections))

    def test_php_atomic_condition_rejects_concurrent_title_change(self):
        plan, token = self.approved()
        self.bridge.exchange({'control': 'race'})
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(self.bridge.exchange({'control': 'stats'})['content'], '<p>Original</p>')

    def test_python_verification_failure_uses_php_conditional_rollback(self):
        plan, token = self.approved()
        self.bridge.exchange({'control': 'verification_failure'})
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rolled_back')
        stats = self.bridge.exchange({'control': 'stats'})
        self.assertEqual(stats['queries'], 2)
        self.assertEqual(stats['content'], '<p>Original</p>')

    def test_lost_php_reply_stays_unknown_and_does_not_replay_write(self):
        plan, token = self.approved()
        self.bridge.drop_next_write_reply = True
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.engine.apply(plan, token, **self.session), result)
        self.assertEqual(self.bridge.exchange({'control': 'stats'})['queries'], 1)

    def test_php_permission_revocation_blocks_application(self):
        plan, token = self.approved()
        self.bridge.exchange({'control': 'forbidden'})
        with self.assertRaises(PermissionError):
            self.engine.apply(plan, token, **self.session)
        self.assertEqual(self.bridge.exchange({'control': 'stats'})['queries'], 0)
