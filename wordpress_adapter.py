
"""Read-only WordPress REST API adapter."""

from urllib.parse import urlparse, urljoin
import requests


class WordPressAdapter:
    def __init__(self, site_url, username, app_password):
        parsed = urlparse(site_url.strip())

        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("A valid HTTPS WordPress URL is required.")

        if not username or not app_password:
            raise ValueError("WordPress credentials are required.")

        self.site_url = site_url.rstrip("/") + "/"
        self.session = requests.Session()
        self.session.auth = (username, app_password)
        self.session.headers.update({
            "Accept": "application/json"
        })

    def _get(self, endpoint, params=None):
        url = urljoin(self.site_url, endpoint)

        response = self.session.get(
            url,
            params=params,
            timeout=15,
            allow_redirects=False
        )
        response.raise_for_status()
        return response.json()

    def verify_connection(self):
        user = self._get("wp-json/wp/v2/users/me")

        return {
            "connected": True,
            "user_id": user.get("id"),
            "username": user.get("slug"),
        }

    def get_posts(self, per_page=20):
        return self._get(
            "wp-json/wp/v2/posts",
            params={
                "per_page": min(max(int(per_page), 1), 100),
                "status": "publish",
                "context": "view",
            }
        )

    def get_pages(self, per_page=20):
        return self._get(
            "wp-json/wp/v2/pages",
            params={
                "per_page": min(max(int(per_page), 1), 100),
                "status": "publish",
                "context": "view",
            }
        )

    def close(self):
        self.session.close()
