"""Validate bounded, read-only WordPress REST responses; no network or secrets."""
import json
import ipaddress
import re
from urllib.parse import urlsplit
from wordpress_secure_https import ValidatedHTTPResponse, MAX_RESPONSE_SIZE


class InvalidWordPressResponse(ValueError):
    """The response cannot be trusted as the expected REST resource."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidWordPressResponse("Duplicate JSON object key")
        result[key] = value
    return result


def _safe_public_https_url(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 4096:
        return False
    if re.search(r"[\x00-\x20\x7f\\]", value):
        return False
    try:
        parsed = urlsplit(value)
        if (parsed.scheme != "https" or not parsed.netloc or parsed.username is not None
                or parsed.password is not None or parsed.fragment or parsed.port not in (None, 443)):
            return False
        host = parsed.hostname
        if not host or len(host) > 253 or '%' in host:
            return False
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            labels = host.removesuffix('.').split('.')
            return len(labels) >= 2 and all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
        return ip.is_global
    except ValueError:
        return False


def validate_wordpress_response(response, resource):
    """Return validated JSON for verify, posts or pages; never perform I/O."""
    if type(resource) is not str or resource not in ("verify", "posts", "pages"):
        raise InvalidWordPressResponse("Unsupported resource")
    if not isinstance(response, ValidatedHTTPResponse):
        raise InvalidWordPressResponse("Expected validated HTTPS response")
    if response.status != 200:
        raise InvalidWordPressResponse("WordPress returned an unexpected HTTP status")
    if not isinstance(response.body, bytes) or len(response.body) > MAX_RESPONSE_SIZE:
        raise InvalidWordPressResponse("Invalid WordPress response size")
    headers = response.headers
    if not isinstance(headers, tuple):
        raise InvalidWordPressResponse("Invalid response headers")
    types = [value for key, value in headers if key == "content-type"]
    if len(types) != 1 or not isinstance(types[0], str):
        raise InvalidWordPressResponse("Missing or duplicate JSON content type")
    parts = [part.strip().lower() for part in types[0].split(";")]
    if parts[0] != "application/json" or any(part not in ("charset=utf-8", "charset=utf8") for part in parts[1:]):
        raise InvalidWordPressResponse("Unexpected content type")
    try:
        payload = json.loads(response.body.decode("utf-8"), object_pairs_hook=_unique_object,
                             parse_constant=lambda _: (_ for _ in ()).throw(InvalidWordPressResponse("Non-finite JSON number")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise InvalidWordPressResponse("Invalid WordPress JSON") from exc
    if resource == "verify":
        slug = payload.get("slug") if isinstance(payload, dict) else None
        if (not isinstance(payload, dict) or type(payload.get("id")) is not int
                or payload["id"] <= 0 or not isinstance(slug, str)
                or not slug or len(slug) > 200 or re.search(r"[\x00-\x1f\x7f]", slug)):
            raise InvalidWordPressResponse("Invalid user verification response")
    else:
        if not isinstance(payload, list) or len(payload) > 100:
            raise InvalidWordPressResponse("Invalid WordPress collection")
        ids = set()
        for item in payload:
            if (not isinstance(item, dict) or type(item.get("id")) is not int
                    or item["id"] <= 0 or item["id"] in ids
                    or item.get("status") != "publish"
                    or not _safe_public_https_url(item.get("link"))):
                raise InvalidWordPressResponse("Invalid published item")
            ids.add(item["id"])
    return payload
