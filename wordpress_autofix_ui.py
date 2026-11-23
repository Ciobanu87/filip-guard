"""WordPress AutoFix UI: explicit fail-closed status until secure auth is ready.

Never request application passwords while authenticated transport is disabled.
The public WordPress audit is available separately and needs no credentials.
"""
import streamlit as st

from wordpress_remote_readiness import assess_remote_readiness


def render_wordpress_autofix_ui(st_module=None):
    ui = st if st_module is None else st_module
    ui.divider()
    ui.subheader("WordPress AutoFix")
    ui.warning(
        "AutoFix is not available yet. Secure WordPress authentication and "
        "verified backup, approval, post-change checks and rollback must be "
        "completed before website changes can be enabled."
    )
    ui.info(
        "No WordPress username or Application Password is needed now. "
        "Use the public read-only WordPress audit above to review suggestions. "
        "No website changes are made."
    )
    readiness = assess_remote_readiness()
    if readiness["remote_write_authorized"] or readiness["changes_applied"]:
        raise RuntimeError("Unsafe AutoFix readiness state")
    return readiness
