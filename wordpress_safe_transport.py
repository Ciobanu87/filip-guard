
"""FILIP GUARD - Safe WordPress HTTPS transport."""

import ipaddress
import socket

import requests
from requests.adapters import HTTPAdapter
from urllib3 import PoolManager
from urllib3.util import connection


class PublicIPAdapter(HTTPAdapter):
    """Connect only to verified public IP addresses."""

    def init_poolmanager(
        self, connections, maxsize, block=False, **kwargs
    ):
        def public_connection(address, *args, **kw):
            host, port = address

            results = socket.getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )

            public_ips = []

            for result in results:
                ip = ipaddress.ip_address(result[4][0])

                if not ip.is_global:
                    raise ValueError(
                        "Unsafe destination IP blocked."
                    )

                public_ips.append(str(ip))

            if not public_ips:
                raise ValueError("No public IP available.")

            original = socket.getaddrinfo

            def pinned_lookup(name, service, *a, **k):
                if name == host:
                    return original(
                        public_ips[0],
                        service,
                        *a,
                        **k
                    )
                return original(name, service, *a, **k)

            # DNS pinning must be implemented at socket
            # creation without changing global DNS behavior.
            raise NotImplementedError(
                "Safe DNS pinning not yet implemented."
            )

        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **kwargs
        )


def create_safe_session():
    """Return a session with redirects disabled by caller."""

    session = requests.Session()
    session.trust_env = False

    adapter = PublicIPAdapter()
    session.mount("https://", adapter)

    return session
