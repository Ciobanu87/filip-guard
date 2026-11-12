
import streamlit as st

from wordpress_connection import WordPressConnection


def render_wordpress_autofix_ui():
    st.divider()
    st.subheader("WordPress AutoFix")
    st.caption(
        "Beta: verificare conexiune. "
        "Nu se modifica site-ul."
    )

    with st.form("wordpress_connection_form"):
        site_url = st.text_input(
            "WordPress URL",
            placeholder="https://example.com",
        )

        username = st.text_input(
            "WordPress username"
        )

        app_password = st.text_input(
            "Application Password",
            type="password",
        )

        submitted = st.form_submit_button(
            "Verifica conexiunea"
        )

    if submitted:
        if not site_url or not username or not app_password:
            st.warning("Completeaza toate campurile.")
            return

        try:
            connection = WordPressConnection()
            result = connection.verify(
                site_url, username, app_password
            )

            if result.get("connected") is True:
                st.success("Conexiune WordPress reusita!")
                st.info(
                    "Modul read-only. "
                    "Nicio reparatie nu a fost aplicata."
                )
            else:
                st.error("Conexiunea nu a fost confirmata.")

        except Exception:
            st.error(
                "Verificarea conexiunii a esuat. "
                "Controleaza URL-ul si credentialele."
            )
