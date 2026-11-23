"""Candidate real REST gateway, not wired to the public app or default engine.

Uses the existing pinned verified HTTPS transport. Requires the separately gated
FILIP GUARD companion endpoint for atomic content CAS; NEVER falls back to a
normal WordPress REST POST. Real WordPress integration remains unvalidated.
"""
import base64
from hashlib import sha256
import json
import re

from wordpress_auth_preflight import validate_auth_preflight
from wordpress_execution_gate import _origin
from wordpress_identity_response import inspect_identity_response
from wordpress_revision_guard import ResourceSnapshot, verify_unchanged, RevisionMismatchError
from wordpress_secure_https import _https_request_exchange, parse_http_response


class WordPressRESTError(ConnectionError):
    """Sanitized protocol/network error, never a raw response or credential."""


class WordPressRESTAuthenticationError(PermissionError):
    pass


def _strict_json(body):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(body.decode('utf-8'), object_pairs_hook=pairs)


class WordPressRESTGateway:
    """Explicit development dependency; no flag can activate the public UI.

    credential_provider is trusted server code returning (username, application
    password) transiently. The gateway never persists credentials or includes
    them in diagnostics. The provider must not read credentials from URL/query
    fields or log them; production secret custody is outside this class.
    """
    def __init__(self, site_url, credential_provider, *, timeout=15):
        self.site_url = 'https://' + _origin(site_url)
        if not callable(credential_provider):
            raise ValueError('Trusted transient credential provider required')
        self._credentials = credential_provider
        self.timeout = timeout

    def _request(self, path, *, method='GET', data=None):
        authorization = credentials = username = password = None
        try:
            credentials = self._credentials()
            if type(credentials) is not tuple or len(credentials) != 2:
                raise ValueError()
            username, password = credentials
            checked = validate_auth_preflight(self.site_url, username, password)
            if ':' in username:
                raise ValueError()
            password = password.replace(' ', '')
            if not password:
                raise ValueError()
            authorization = 'Basic ' + base64.b64encode(
                (username + ':' + password).encode('utf-8')).decode('ascii')
            body = b'' if data is None else json.dumps(data, ensure_ascii=True,
                separators=(',', ':'), allow_nan=False).encode('utf-8')
            raw = _https_request_exchange(checked.hostname, path, self.timeout,
                                          method=method, body=body, authorization=authorization)
            response = parse_http_response(raw)
        except Exception:
            raise WordPressRESTError('Secure WordPress REST exchange failed') from None
        finally:
            authorization = credentials = username = password = None
        if response.status == 401:
            raise WordPressRESTAuthenticationError('WordPress authentication rejected')
        if response.status == 403:
            raise PermissionError('WordPress resource permission rejected')
        content_types = [value.lower().split(';')[0].strip() for key, value in response.headers
                         if key == 'content-type']
        if content_types != ['application/json']:
            raise WordPressRESTError('Invalid WordPress REST response content type')
        try:
            data = _strict_json(response.body)
        except (ValueError, UnicodeError, RecursionError):
            raise WordPressRESTError('Invalid WordPress REST JSON response') from None
        if response.status == 409 and type(data) is dict and data.get('code') == 'fg_conflict':
            raise RevisionMismatchError('WordPress resource version changed')
        if response.status != 200 or type(data) is not dict:
            raise WordPressRESTError('WordPress companion request failed or outcome is uncertain')
        return response, data

    def _target(self, site, kind, resource_id, user_id):
        if ('https://' + _origin(site) != self.site_url
                or kind not in ('post', 'page') or type(resource_id) is not int or resource_id <= 0
                or type(user_id) is not int or user_id <= 0):
            raise PermissionError('Invalid WordPress gateway target')
        return f'/wp-json/filip-guard/v1/resources/{kind}/{resource_id}'

    def _identity(self, user_id):
        response, _ = self._request('/wp-json/wp/v2/users/me')
        try:
            identity = inspect_identity_response(response)
        except ValueError:
            raise WordPressRESTError('Invalid WordPress identity response') from None
        if identity.user_id != user_id:
            raise PermissionError('WordPress user identity mismatch')

    def _snapshot(self, data, kind, resource_id, user_id):
        if (data.get('protocol') != 'filip-guard-cas-v1'
                or type(data.get('resource_id')) is not int or data['resource_id'] != resource_id
                or data.get('resource_type') != kind or type(data.get('user_id')) is not int
                or data['user_id'] != user_id or data.get('can_edit') is not True
                or type(data.get('content')) is not str
                or len(data['content'].encode('utf-8')) > 1_000_000
                or type(data.get('version')) is not str
                or not re.fullmatch('[0-9a-f]{64}', data['version'])):
            raise WordPressRESTError('Invalid authorized WordPress resource snapshot')
        return ResourceSnapshot(self.site_url, kind, resource_id, data['content'], data['version'])

    def verify_site_owner(self):
        """Require authenticated site-administration capability for initial binding."""
        response, _ = self._request('/wp-json/wp/v2/users/me')
        try:
            identity = inspect_identity_response(response)
        except ValueError:
            raise WordPressRESTError('Invalid WordPress identity response') from None
        _, proof = self._request('/wp-json/filip-guard/v1/ownership')
        if (proof.get('protocol') != 'filip-guard-cas-v1'
                or type(proof.get('user_id')) is not int or proof['user_id'] != identity.user_id
                or proof.get('can_manage_site') is not True):
            raise PermissionError('Verified site-administration capability required')
        return identity.user_id

    def read_authorized(self, site, kind, resource_id, user_id):
        path = self._target(site, kind, resource_id, user_id)
        self._identity(user_id)
        _, data = self._request(path)
        return self._snapshot(data, kind, resource_id, user_id)

    def compare_and_swap(self, expected, content, user_id, *, operation_id):
        if type(expected) is not ResourceSnapshot:
            raise ValueError('Verified resource snapshot required')
        verify_unchanged(expected, expected)
        path = self._target(expected.site_url, expected.resource_type, expected.resource_id, user_id)
        if (type(content) is not str or content == expected.content
                or len(content.encode('utf-8')) > 1_000_000
                or type(operation_id) is not str or not re.fullmatch('[A-Za-z0-9:_-]{1,96}', operation_id)
                or not re.fullmatch('[0-9a-f]{64}', expected.revision)):
            raise ValueError('Invalid conditional WordPress content update')
        self._identity(user_id)
        _, data = self._request(path, method='POST', data={
            'expected_version': expected.revision, 'proposed_content': content,
            'operation_id': operation_id, 'user_id': user_id})
        receipt = self._snapshot(data, expected.resource_type, expected.resource_id, user_id)
        if receipt.content != content or receipt.revision == expected.revision:
            raise WordPressRESTError('Invalid conditional WordPress write receipt')
        return receipt
