"""Safe, offline classification of errors from verified WordPress HTTPS transport.

Does not connect to a host, relax TLS checks, or expose endpoint details.
"""
import socket
import ssl


def classify_tls_failure(error):
    """Return a user-facing category and action without leaking host details."""
    visited = set()
    current = error
    while isinstance(current, BaseException) and id(current) not in visited:
        visited.add(id(current))
        if type(current) is ConnectionError and (current.__cause__ or current.__context__):
            current = current.__cause__ or current.__context__
            continue
        if isinstance(current, ssl.SSLCertVerificationError):
            return {'code': 'certificate_verification', 'message': 'TLS certificate verification failed. Check the site certificate and hostname; verification remains required.'}
        if isinstance(current, (TimeoutError, socket.timeout)):
            return {'code': 'timeout', 'message': 'Secure connection timed out. Try again later or check network access.'}
        if isinstance(current, ConnectionRefusedError):
            return {'code': 'connection_refused', 'message': 'The destination refused the HTTPS connection.'}
        if isinstance(current, ssl.SSLError):
            return {'code': 'tls_handshake', 'message': 'TLS handshake failed. The connection was not trusted.'}
        if isinstance(current, ConnectionError):
            return {'code': 'unknown', 'message': 'Verified HTTPS connection failed. No security checks were bypassed.'}
        if isinstance(current, OSError):
            return {'code': 'network_error', 'message': 'Network connection failed before a verified HTTPS response.'}
        current = current.__cause__ or current.__context__
    return {'code': 'unknown', 'message': 'Verified HTTPS connection failed. No security checks were bypassed.'}
