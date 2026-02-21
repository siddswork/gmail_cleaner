"""
Gmail Cleaner — main entry point.

Run with:
    streamlit run app.py
"""
import streamlit as st

from auth.oauth import get_authenticated_service
from cache.database import init_db

# ---------------------------------------------------------------------------
# Page config (must be the first Streamlit call)
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Gmail Cleaner",
    page_icon="📧",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

def _init_session_state() -> None:
    defaults = {
        "gmail_service": None,
        "active_account": None,
        "accounts": [],          # list of authenticated account emails
        "last_sync": None,
        "sync_in_progress": False,
        "pending_trash": [],
        "trash_confirmed": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


_init_session_state()

# ---------------------------------------------------------------------------
# Sidebar — account switcher
# ---------------------------------------------------------------------------

def _render_sidebar() -> None:
    st.sidebar.title("Gmail Cleaner")

    accounts = st.session_state["accounts"]
    active = st.session_state["active_account"]

    # Account selector
    if accounts:
        selected = st.sidebar.selectbox(
            "Active account",
            options=accounts,
            index=accounts.index(active) if active in accounts else 0,
        )
        if selected != active:
            _switch_account(selected)

    # Add account
    st.sidebar.divider()
    with st.sidebar.expander("Add account"):
        if st.button("Connect a Gmail account", use_container_width=True):
            _add_account()

    # Remove active account
    if active:
        st.sidebar.divider()
        if st.sidebar.button("Remove this account", type="secondary"):
            _remove_account(active)

    # Sync status
    if active:
        st.sidebar.divider()
        st.sidebar.caption("Last sync")
        if st.session_state["last_sync"]:
            st.sidebar.caption(str(st.session_state["last_sync"]))
        else:
            st.sidebar.caption("Never")

        if st.session_state["sync_in_progress"]:
            st.sidebar.info("Sync in progress...")


def _add_account() -> None:
    """Trigger OAuth flow for a new account and register it."""
    try:
        # The OAuth flow opens a browser window; the email is extracted
        # from the service after authentication.
        service = get_authenticated_service.__wrapped__ if hasattr(
            get_authenticated_service, "__wrapped__"
        ) else get_authenticated_service

        # We need a placeholder email during the flow; after auth we
        # query the profile to get the real address.
        with st.spinner("Opening browser for Google sign-in..."):
            # Use a temporary key; replaced once we know the real email.
            tmp_service = get_authenticated_service("__new__")
            profile = tmp_service.users().getProfile(userId="me").execute()
            email = profile["emailAddress"]

        # Re-authenticate under the real email so the token is stored correctly.
        real_service = get_authenticated_service(email)
        init_db(email)

        if email not in st.session_state["accounts"]:
            st.session_state["accounts"].append(email)

        _switch_account(email)
        st.success(f"Connected: {email}")
        st.rerun()

    except Exception as exc:
        st.error(f"Authentication failed: {exc}")


def _switch_account(email: str) -> None:
    """Switch the active account and load its Gmail service."""
    try:
        service = get_authenticated_service(email)
        st.session_state["active_account"] = email
        st.session_state["gmail_service"] = service
        st.session_state["last_sync"] = None
    except Exception as exc:
        st.error(f"Could not connect to {email}: {exc}")


def _remove_account(email: str) -> None:
    """Remove an account from the session (does not delete local data)."""
    accounts = st.session_state["accounts"]
    if email in accounts:
        accounts.remove(email)
    st.session_state["active_account"] = accounts[0] if accounts else None
    st.session_state["gmail_service"] = None
    st.rerun()


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

_render_sidebar()

active = st.session_state["active_account"]

if not active:
    st.title("Welcome to Gmail Cleaner")
    st.markdown(
        """
        Connect a Gmail account using the sidebar to get started.

        **What this tool does:**
        - Shows you where your storage is going (top senders, large threads, old newsletters)
        - Lets you bulk-delete unwanted mail with a preview before anything is removed
        - Helps you unsubscribe from mailing lists

        **What it never does:**
        - Permanently delete email (everything goes to Trash — 30-day recovery window)
        - Touch starred or important messages
        - Act without your explicit confirmation
        """
    )
else:
    st.title(f"Gmail Cleaner — {active}")
    st.info(
        "Use the pages in the sidebar to explore your mailbox, run cleanup, "
        "or manage subscriptions."
    )
