"""Reserved WordPress authenticated HTTPS entry point.

Fail closed: no caller-controlled flag may enable authenticated networking.
Production integration requires a separate security review and approval.
"""

class AuthenticatedTransportDisabled(RuntimeError):
    """Authenticated transport has not been approved for use."""


def authenticated_wordpress_get(*args, **kwargs):
    """Reject every call without inspecting or logging credentials."""
    raise AuthenticatedTransportDisabled(
        "Authenticated WordPress transport remains disabled"
    )
