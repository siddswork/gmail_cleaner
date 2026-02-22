"""
Unsubscribe — manage dead mailing list subscriptions.

Shows senders with unsubscribe URLs where every email is unread and the
most recent email is older than a configurable threshold. Offers one-click
POST unsubscribe (RFC 8058) or opens the unsubscribe URL in the browser.
"""
import streamlit as st

from analysis.insights import dead_subscriptions
from cache.database import _connect
from gmail.actions import unsubscribe_via_post

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Unsubscribe — Gmail Cleaner", layout="wide")

# ---------------------------------------------------------------------------
# Guard: require an active account
# ---------------------------------------------------------------------------

active = st.session_state.get("active_account")
if not active:
    st.warning("Connect a Gmail account from the main page first.")
    st.stop()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_size(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    if b >= 1_024:
        return f"{b / 1_024:.1f} KB"
    return f"{b} B"


def _fmt_ts(ts: int | None) -> str:
    if ts is None:
        return "—"
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %d, %Y")


def _get_unsub_post(sender_email: str) -> str | None:
    """Return the List-Unsubscribe-Post value from the most recent email for this sender."""
    conn = _connect(active)
    row = conn.execute(
        """
        SELECT unsubscribe_post FROM emails
        WHERE sender_email = ? AND unsubscribe_post IS NOT NULL
        ORDER BY date_ts DESC LIMIT 1
        """,
        (sender_email,),
    ).fetchone()
    conn.close()
    return row["unsubscribe_post"] if row else None


# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------

if "unsub_actioned" not in st.session_state:
    st.session_state["unsub_actioned"] = set()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    days = st.slider(
        "Inactive for at least (days)",
        min_value=7,
        max_value=365,
        value=30,
        step=7,
        help="Only show senders whose last email is older than this many days.",
    )
    if st.button("Reset actioned list"):
        st.session_state["unsub_actioned"] = set()
        st.rerun()

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("Unsubscribe")
st.caption(f"Account: {active}")

subs = dead_subscriptions(active, days=days)

# Filter out already actioned senders
actioned: set = st.session_state["unsub_actioned"]
pending = [s for s in subs if s["sender_email"] not in actioned]

if not subs:
    st.info(
        f"No dead subscriptions found. "
        f"A dead subscription is a sender with an unsubscribe link where "
        f"every email is unread and the last email arrived over {days} days ago."
    )
    st.stop()

col_total, col_pending, col_done = st.columns(3)
col_total.metric("Total dead subscriptions", len(subs))
col_pending.metric("Pending action", len(pending))
col_done.metric("Actioned this session", len(actioned))

st.caption(
    "Only senders with a List-Unsubscribe header, all emails unread, "
    f"and no email in the last {days} days. Starred and important emails excluded."
)

st.divider()

if not pending:
    st.success("All dead subscriptions have been actioned this session.")
    st.stop()

# ---------------------------------------------------------------------------
# Per-sender action rows
# ---------------------------------------------------------------------------

for sub in pending:
    sender = sub["sender_email"]
    name = sub.get("sender_name") or sender
    count = sub["count"]
    size = sub.get("total_size") or 0
    latest_ts = sub.get("latest_ts")
    unsub_url = sub.get("unsubscribe_url", "")

    with st.container(border=True):
        top, actions = st.columns([3, 2])

        with top:
            st.markdown(f"**{name}**")
            st.caption(f"{sender} · {count:,} unread emails · {_fmt_size(size)} · last: {_fmt_ts(latest_ts)}")

        with actions:
            btn_col1, btn_col2, btn_col3 = st.columns(3)

            # POST unsubscribe (RFC 8058) — only if unsubscribe_post is present
            unsub_post = _get_unsub_post(sender)
            with btn_col1:
                if unsub_post and unsub_url:
                    if st.button("POST unsub", key=f"post_{sender}", help="Send RFC 8058 one-click unsubscribe request"):
                        ok = unsubscribe_via_post(unsub_url, unsub_post)
                        if ok:
                            st.session_state["unsub_actioned"].add(sender)
                            st.toast(f"Unsubscribed from {sender}", icon="✅")
                            st.rerun()
                        else:
                            st.error("POST request failed — try opening the URL instead.")
                else:
                    st.button("POST unsub", key=f"post_{sender}", disabled=True,
                              help="No List-Unsubscribe-Post header for this sender.")

            # Open URL in browser
            with btn_col2:
                if unsub_url:
                    st.link_button("Open URL", url=unsub_url, help="Open unsubscribe page in browser")
                else:
                    st.button("Open URL", key=f"url_{sender}", disabled=True)

            # Skip (mark as actioned without doing anything)
            with btn_col3:
                if st.button("Skip", key=f"skip_{sender}", help="Hide this sender for this session"):
                    st.session_state["unsub_actioned"].add(sender)
                    st.rerun()
