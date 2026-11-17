"""Strict offline WordPress REST path builder; no networking or credentials."""
from urllib.parse import urlencode

class InvalidWordPressEndpoint(ValueError):
    pass

def readonly_path(resource, *, per_page=20):
    """Allow only explicitly reviewed read-only WordPress REST endpoints."""
    if not isinstance(resource, str) or type(resource) is not str:
        raise InvalidWordPressEndpoint("Unsupported WordPress resource")
    if resource == "verify":
        return "/wp-json/wp/v2/users/me"
    if resource not in ("posts", "pages"):
        raise InvalidWordPressEndpoint("Unsupported WordPress resource")
    if type(per_page) is not int or not 1 <= per_page <= 100:
        raise InvalidWordPressEndpoint("Invalid WordPress page size")
    return "/wp-json/wp/v2/" + resource + "?" + urlencode(
        (("per_page", per_page), ("status", "publish"), ("context", "view"))
    )
