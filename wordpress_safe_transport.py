
"""FILIP GUARD - WordPress safe transport.

Disabled until secure HTTPS transport
is implemented and tested.
"""


class SafeTransportUnavailable(RuntimeError):
    pass


def create_safe_session():
    raise SafeTransportUnavailable(
        "Secure WordPress transport is not ready. "
        "Connections are disabled."
    )
