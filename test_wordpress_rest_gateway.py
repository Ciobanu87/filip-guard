"""Wire-level simulated REST integration. No network or WordPress site is used."""
import base64
from hashlib import sha256
import json
import os
import re
import tempfile
import unittest
from unittest.mock import patch

from backup import BackupManager
from wordpress_autofix_engine import AutoFixEngine
from wordpress_local_fixture import LocalWordPressFixture
from wordpress_rest_gateway import WordPressRESTGateway, WordPressRESTError, WordPressRESTAuthenticationError
from wordpress_revision_guard import RevisionMismatchError


def response(status, data, extra=b''):
    body = json.dumps(data, ensure_ascii=True).encode()
    return (f'HTTP/1.1 {status} Result\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n'.encode()
            + extra + b'\r\n' + body)


class RESTFixture:
    def __init__(self, path):
        self.db = LocalWordPressFixture(path)
        self.site = 'https://example.com'
        self.db.seed(self.site, 'post', 10, 'Original ✓', user_id=7)
        self.requests = []
        self.auth_status = 200
        self.resource_status = 200
        self.missing_plugin = False
        self.race = False
        self.disconnect_after_commit = False
        self.fail_verification = False
        self.fail_rollback = False
        self.wrote = False

    def current(self):
        return self.db.read_authorized(self.site, 'post', 10, 7)

    def snapshot(self, snapshot):
        return dict(protocol='filip-guard-cas-v1', resource_id=10, resource_type='post',
                    user_id=7, can_edit=True, content=snapshot.content,
                    version=sha256(snapshot.revision.encode()).hexdigest())

    def exchange(self, request):
        head, body = request.split(b'\r\n\r\n', 1)
        lines = head.split(b'\r\n')
        method, path, _ = lines[0].decode().split(' ')
        headers = dict(line.decode().split(': ', 1) for line in lines[1:])
        assert headers['Host'] == 'example.com'
        assert headers['Authorization'] == 'Basic ' + base64.b64encode(b'editor:fakepassword').decode()
        assert 'Cookie' not in headers
        self.requests.append((method, path, headers, body))
        if self.auth_status != 200:
            return response(self.auth_status, {'code': 'auth_denied'})
        if path == '/wp-json/wp/v2/users/me':
            return response(200, {'id': 7, 'slug': 'editor', 'name': 'Editor'})
        assert path == '/wp-json/filip-guard/v1/resources/post/10'
        if self.missing_plugin:
            return response(404, {'code': 'rest_no_route'})
        if self.resource_status != 200:
            return response(self.resource_status, {'code': 'rest_forbidden'})
        if method == 'GET':
            if self.wrote and self.fail_verification:
                self.fail_verification = False
                raise TimeoutError('verification disconnected')
            return response(200, self.snapshot(self.current()))
        assert method == 'POST'
        assert int(headers['Content-Length']) == len(body)
        assert headers['Content-Type'] == 'application/json'
        data = json.loads(body)
        if data['operation_id'].endswith(':rollback') and self.fail_rollback:
            return response(503, {'code': 'unavailable'})
        if self.race:
            self.race = False
            self.db.compare_and_swap(self.current(), 'Concurrent edit', 7, operation_id='racer')
        current = self.current()
        if data['expected_version'] != self.snapshot(current)['version']:
            return response(409, {'code': 'fg_conflict'})
        assert data['user_id'] == 7
        receipt = self.db.compare_and_swap(current, data['proposed_content'], 7,
                                           operation_id=data['operation_id'])
        self.wrote = True
        if self.disconnect_after_commit:
            raise TimeoutError('reply lost after server commit')
        return response(200, self.snapshot(receipt))

    def connection(self, *args, **kwargs):
        fixture = self
        class Connection:
            closed = False
            result = b''
            def settimeout(self, timeout):
                assert timeout > 0
            def sendall(self, request):
                self.result = fixture.exchange(request)
            def recv(self, count):
                result, self.result = self.result[:count], self.result[count:]
                return result
            def close(self):
                self.closed = True
        connection = Connection()
        fixture.connections.append(connection)
        return connection


class RESTGatewayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.server = RESTFixture(os.path.join(self.temp.name, 'fixture.sqlite'))
        self.server.connections = []
        self.transport = patch('wordpress_secure_https.create_verified_connection', side_effect=self.server.connection)
        self.transport.start()
        self.addCleanup(self.transport.stop)
        self.gateway = WordPressRESTGateway(self.server.site, lambda: ('editor', 'fake password'))
        self.engine = AutoFixEngine(os.path.join(self.temp.name, 'engine.sqlite'),
            BackupManager(os.path.join(self.temp.name, 'backups.sqlite')), self.gateway)
        self.session = dict(user_id=7, session_id='s' * 43, now=100)

    def approved(self):
        plan = self.engine.propose(site_url=self.server.site, resource_type='post', resource_id=10,
            proposed_content='Updated ✓', **self.session)['plan_id']
        return plan, self.engine.approve(plan, confirmed=True, **self.session)

    def test_real_gateway_engine_approval_backup_write_and_verify(self):
        plan, token = self.approved()
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'applied')
        self.assertEqual(self.server.current().content, 'Updated ✓')
        self.assertEqual(self.engine.backups.get_backup(result['backup_id'])['content'], 'Original ✓')
        posts = [request for request in self.server.requests if request[0] == 'POST']
        self.assertEqual(len(posts), 1)
        self.assertEqual(json.loads(posts[0][3])['operation_id'], plan)
        self.assertTrue(all(conn.closed for conn in self.server.connections))
        self.assertNotIn('fakepassword', repr(result))
        # A replay is served from the persistent engine journal, without requests.
        request_count = len(self.server.requests)
        self.assertEqual(self.engine.apply(plan, token, **self.session), result)
        self.assertEqual(len(self.server.requests), request_count)

    def test_authentication_and_authorization_failure(self):
        for status in (401, 403):
            self.server.auth_status = status
            with self.assertRaises(PermissionError):
                self.gateway.read_authorized(self.server.site, 'post', 10, 7)
        self.server.auth_status = 200
        self.server.resource_status = 403
        with self.assertRaises(PermissionError):
            self.gateway.read_authorized(self.server.site, 'post', 10, 7)
        self.assertEqual(self.server.current().revision, '1')

    def test_wrong_user_or_site_never_reaches_mutation(self):
        with self.assertRaises(PermissionError):
            self.gateway.read_authorized(self.server.site, 'post', 10, 8)
        count = len(self.server.requests)
        with self.assertRaises(PermissionError):
            self.gateway.read_authorized('https://other.example', 'post', 10, 7)
        self.assertEqual(len(self.server.requests), count)

    def test_missing_atomic_endpoint_never_falls_back_to_standard_post(self):
        self.server.missing_plugin = True
        with self.assertRaises(WordPressRESTError):
            self.gateway.read_authorized(self.server.site, 'post', 10, 7)
        self.assertTrue(all('/wp/v2/posts' not in req[1] for req in self.server.requests))

    def test_concurrent_edit_between_read_and_post_is_preserved(self):
        plan, token = self.approved()
        self.server.race = True
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(self.server.current().content, 'Concurrent edit')

    def test_lost_connection_after_commit_is_unknown_and_never_retried(self):
        plan, token = self.approved()
        self.server.disconnect_after_commit = True
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'outcome_unknown')
        self.assertEqual(self.server.current().content, 'Updated ✓')
        self.engine.apply(plan, token, **self.session)
        self.assertEqual(len([x for x in self.server.requests if x[0] == 'POST']), 1)
        self.assertTrue(all(conn.closed for conn in self.server.connections))

    def test_failed_verification_restores_through_same_conditional_rest_endpoint(self):
        plan, token = self.approved()
        self.server.fail_verification = True
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rolled_back')
        self.assertEqual(self.server.current().content, 'Original ✓')
        requests = [json.loads(x[3]) for x in self.server.requests if x[0] == 'POST']
        self.assertEqual(requests[-1]['operation_id'], plan + ':rollback')
        self.assertNotEqual(requests[0]['expected_version'], requests[-1]['expected_version'])

    def test_failed_restoration_is_explicit(self):
        plan, token = self.approved()
        self.server.fail_verification = self.server.fail_rollback = True
        result = self.engine.apply(plan, token, **self.session)
        self.assertEqual(result['status'], 'rollback_unverified')
        self.assertTrue(result['requires_intervention'])

    def test_redirect_or_tls_error_does_not_retry_or_expose_secret(self):
        for error in (OSError('fakepassword'), ValueError('private destination')):
            with patch('wordpress_secure_https.create_verified_connection', side_effect=error) as connect:
                with self.assertRaises(WordPressRESTError) as caught:
                    self.gateway.read_authorized(self.server.site, 'post', 10, 7)
                self.assertNotIn('fakepassword', str(caught.exception))
                connect.assert_called_once()
        with patch.object(self.server, 'exchange', return_value=response(302, {}, b'Location: https://other.example/\r\n')) as exchange:
            with self.assertRaises(WordPressRESTError):
                self.gateway.read_authorized(self.server.site, 'post', 10, 7)
            exchange.assert_called_once()

    def test_malformed_or_duplicate_json_receipts_are_rejected(self):
        for data in ({'protocol': 'wrong'}, {'id': True}):
            with patch.object(self.server, 'exchange', return_value=response(200, data)):
                with self.assertRaises(WordPressRESTError):
                    self.gateway.read_authorized(self.server.site, 'post', 10, 7)
        data = b'{"id":7,"id":8,"slug":"editor","name":"Editor"}'
        raw = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(data)).encode() + b'\r\n\r\n' + data
        with patch.object(self.server, 'exchange', return_value=raw):
            with self.assertRaises(WordPressRESTError):
                self.gateway.read_authorized(self.server.site, 'post', 10, 7)

    def test_oversized_request_fails_before_connection(self):
        from wordpress_secure_https import _https_request_exchange
        with patch('wordpress_secure_https.create_verified_connection') as connect:
            with self.assertRaises(ValueError):
                _https_request_exchange('example.com', '/', 15, method='POST', body=b'x' * 1_100_001)
            connect.assert_not_called()
