"""Validate bounded, read-only WordPress REST responses; no network or secrets."""
import json
from wordpress_secure_https import ValidatedHTTPResponse, MAX_RESPONSE_SIZE


class InvalidWordPressResponse(ValueError):
    """The response cannot be trusted as the expected REST resource."""


def validate_wordpress_response(response, resource):
    """Return a validated JSON object/list for verify, posts or pages.

    The caller must already use the strict HTTPS response parser. This layer
    enforces the expected REST representation, not authorization or transport.
    """
    if resource not in ("verify", "posts", "pages") or not isinstance(resource, str):
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
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        raise InvalidWordPressResponse("Invalid WordPress JSON") from exc
    if resource == "verify":
        if (not isinstance(payload, dict) or type(payload.get("id")) is not int
                or payload["id"] <= 0 or not isinstance(payload.get("slug"), str)
                or not payload["slug"] or len(payload["slug"]) > 200):
            raise InvalidWordPressResponse("Invalid user verification response")
    else:
        if not isinstance(payload, list) or len(payload) > 100:
            raise InvalidWordPressResponse("Invalid WordPress collection")
        ids = set()
        for item in payload:
            if (not isinstance(item, dict) or type(item.get("id")) is not int
                    or item["id"] <= 0 or item["id"] in ids
                    or item.get("status") != "publish"
                    or not isinstance(item.get("link"), str)
                    or not item["link"].startswith("https://")
                    or len(item["link"]) > 4096):
                raise InvalidWordPressResponse("Invalid published item")
            ids.add(item["id"])
    return payload
