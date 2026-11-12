
"""FILIP GUARD - WordPress connection verification.

Read-only connection checks.
No credentials are stored by this module.
No website changes are performed.
"""

from urllib.parse import urlparse

from wordpress_adapter import WordPressAdapter
from wordpress_security import validate_public_wordpress_url


class WordPressConnection:
    def __init__(self, adapter_class=WordPressAdapter):
        self.adapter_class = adapter_class

    @staticmethod
    def validate_url(site_url):
        if not isinstance(site_url, str):
            raise ValueError("Invalid website URL.")

        parsed = urlparse(site_url.strip())

        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ("", "/")
        ):
            raise ValueError(
                "A valid HTTPS WordPress site URL is required."
            )

        return parsed.geturl().rstrip("/")

    def verify(self, site_url, username, app_password):
        """Verify credentials without changing WordPress."""

        validated_url = validate_public_wordpress_url(
    self.validate_url(site_url)
)

        if not isinstance(username, str) or not username.strip():
            raise ValueError("Username is required.")

        if not isinstance(app_password, str) or not app_password.strip():
            raise ValueError(
                "WordPress application password is required."
            )

        adapter = self.adapter_class(
            validated_url,
            username,
            app_password,
        )

        try:
            result = adapter.verify_connection()

            if (
                not isinstance(result, dict)
                or result.get("connected") is not True
                or not result.get("user_id")
            ):
                raise ConnectionError(
                    "WordPress verification failed."
                )

            return {
                "connected": True,
                "site_url": validated_url,
                "user_id": result["user_id"],
                "username": result.get("username"),
                "read_only_check": True,
            }
        finally:
            adapter.close()
