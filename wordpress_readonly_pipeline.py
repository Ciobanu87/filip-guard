"""Offline composition of the approved WordPress read-only endpoint and response validators.

No credentials, sockets, adapter access, or production authentication are enabled.
"""
from wordpress_readonly_endpoints import readonly_path
from wordpress_rest_validation import validate_wordpress_response
from wordpress_secure_https import parse_http_response


def validate_readonly_exchange(resource, raw_response, *, per_page=20):
    """Return (allowed_path, validated_data) for a previously captured HTTP response.

    This function never performs an HTTP request. Only a trusted caller may
    provide raw_response; it is still strictly parsed and validated here.
    """
    path = readonly_path(resource, per_page=per_page)
    if not isinstance(raw_response, bytes):
        raise ValueError("Expected raw HTTP response bytes")
    response = parse_http_response(raw_response)
    data = validate_wordpress_response(response, resource)
    return path, data
