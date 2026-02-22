"""
Cleanup — bulk-trash emails by sender.

Flow:
  1. Pick a sender from the sidebar (pre-populated from top senders)
  2. Apply optional filters (date range, label, unread, min size)
  3. Preview the selected batch (count + size, starred/important excluded)
  4. Pass through safety guards (large-batch word confirm, preview dialog)
  5. Execute: incremental sync → live label check → trash → update cache
"""
import json

import pandas as pd
import streamlit as st

from analysis.aggregator import top_senders_by_count
from cache.database import _connect
from cache.sync import incremental_sync
from components.safety import (
    confirm_trash_dialog,
    is_large_batch,
    large_batch_guard,
    live_label_check,
)
from gmail.actions import trash_messages

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Cleanup — Gmail Cleaner", layout="wide")

# ---------------------------------------------------------------------------
# Guard: require an active account
# ---------------------------------------------------------------------------

active = st.session_state.get("active_account")
service = st.session_state.get("gmail_service")

if not active or not service:
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


def _query_messages(
    account_email: str,
    sender_email: str,
    start_ts: int | None,
    end_ts: int | None,
    labels: list[str],
    unread_only: bool,
    min_size: int,
) -> list[dict]:
    """
    Return message_id + size_estimate for emails matching the given filters.
    Always excludes starred and important emails.
    """
    clauses = [
        "sender_email = ?",
        "is_starred = 0",
        "is_important = 0",
    ]
    params: list = [sender_email]

    if start_ts:
        clauses.append("date_ts >= ?")
        params.append(start_ts)
    if end_ts:
        clauses.append("date_ts <= ?")
        params.append(end_ts)
    if unread_only:
        clauses.append("is_read = 0")
    if min_size:
        clauses.append("size_estimate >= ?")
        params.append(min_size)
    if labels:
        # Include email if it carries ANY of the selected labels
        label_clauses = " OR ".join(
            "JSON_EACH.value = ?" for _ in labels
        )
        clauses.append(
            f"message_id IN ("
            f"  SELECT emails.message_id FROM emails, JSON_EACH(emails.label_ids)"
            f"  WHERE {label_clauses}"
            f")"
        )
        params.extend(labels)

    sql = (
        "SELECT message_id, size_estimate FROM emails"
        f" WHERE {' AND '.join(clauses)}"
    )
    conn = _connect(account_email)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Sidebar — sender picker + filters
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Select sender")

    top_senders = top_senders_by_count(active, limit=50)
    sender_options = [""] + [s["sender_email"] for s in top_senders if s["sender_email"]]

    selected_sender = st.selectbox(
        "Top senders (by count)",
        options=sender_options,
        format_func=lambda x: x if x else "— choose a sender —",
        key="cleanup_sender",
    )

    custom_sender = st.text_input(
        "Or type a sender email",
        key="cleanup_custom_sender",
    ).strip().lower()

    sender = custom_sender if custom_sender else selected_sender

    st.divider()
    st.header("Filters")

    col_a, col_b = st.columns(2)
    with col_a:
        start_date = st.date_input("From date", value=None, key="cleanup_start")
    with col_b:
        end_date = st.date_input("To date", value=None, key="cleanup_end")

    start_ts = int(start_date.strftime("%s")) if start_date else None  # type: ignore[arg-type]
    end_ts = int(end_date.strftime("%s")) if end_date else None  # type: ignore[arg-type]

    label_choices = [
        "INBOX",
        "CATEGORY_PROMOTIONS",
        "CATEGORY_UPDATES",
        "CATEGORY_SOCIAL",
        "CATEGORY_FORUMS",
        "SENT",
    ]
    selected_labels = st.multiselect(
        "Label (any match)", label_choices, key="cleanup_labels"
    )

    unread_only = st.checkbox("Unread only", key="cleanup_unread")

    min_size_kb = st.number_input(
        "Min size (KB)", min_value=0, value=0, step=10, key="cleanup_min_size"
    )
    min_size = min_size_kb * 1024

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("Cleanup")
st.caption(f"Account: {active}")

# Show last action result (survives across reruns)
if st.session_state.get("last_trash_result"):
    res = st.session_state["last_trash_result"]
    st.success(
        f"Trashed {res['trashed']:,} emails — "
        f"reclaimed {_fmt_size(res['size_reclaimed'])}."
    )
    if res.get("blocked"):
        st.info(f"{res['blocked']} email(s) skipped — starred or important (protected).")
    if res.get("errors"):
        st.warning(f"{res['errors']} email(s) skipped — API error during label check.")
    if st.button("Clear result"):
        st.session_state["last_trash_result"] = None
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Top senders reference table
# ---------------------------------------------------------------------------

st.subheader("Top Senders")
if top_senders:
    df = pd.DataFrame(top_senders)
    df["total_size_fmt"] = df["total_size"].apply(_fmt_size)
    st.dataframe(
        df[["sender_email", "sender_name", "count", "total_size_fmt"]].rename(
            columns={
                "sender_email": "Email",
                "sender_name": "Name",
                "count": "Emails",
                "total_size_fmt": "Total Size",
            }
        ),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No emails cached yet — run a sync from the main page first.")
    st.stop()

st.divider()

# ---------------------------------------------------------------------------
# Preview section — shown when a sender is selected
# ---------------------------------------------------------------------------

if not sender:
    st.info("Select a sender from the sidebar to preview and delete their emails.")
    st.stop()

messages = _query_messages(
    active, sender, start_ts, end_ts, selected_labels, unread_only, min_size
)
count = len(messages)
total_size = sum(m["size_estimate"] or 0 for m in messages)

st.subheader(f"Preview: {sender}")

if count == 0:
    st.info(
        "No emails match the current filters for this sender "
        "(starred and important are always excluded)."
    )
    st.stop()

col1, col2 = st.columns(2)
col1.metric("Emails to trash", f"{count:,}")
col2.metric("Space to reclaim", _fmt_size(total_size))
st.caption("Starred and important emails are always excluded and will never be trashed.")

# Warn before entering confirmation flow for very large batches
if count > 5_000:
    st.warning(
        f"This will run a live label check on {count:,} emails via the Gmail API "
        f"(~{count // 150 + 1}s). Consider narrowing with filters first."
    )

# Button to move into confirmation state
pending = st.session_state.get("pending_trash", [])
if not pending:
    if st.button(f"Select {count:,} emails for deletion", type="primary"):
        st.session_state["pending_trash"] = [m["message_id"] for m in messages]
        st.session_state["pending_trash_size"] = total_size
        st.session_state["trash_confirmed"] = False
        st.rerun()
    st.stop()

# ---------------------------------------------------------------------------
# Confirmation flow
# ---------------------------------------------------------------------------

pending_ids: list[str] = st.session_state["pending_trash"]
pending_size: int = st.session_state.get("pending_trash_size", 0)
pending_count = len(pending_ids)

st.divider()
st.subheader("Confirm Deletion")

# Cancel button — always visible during confirmation
if st.button("Cancel", key="cancel_btn"):
    st.session_state["pending_trash"] = []
    st.session_state["trash_confirmed"] = False
    st.rerun()

# Large-batch guard (requires typing "DELETE" if > 500)
guard_ok = large_batch_guard(pending_count)

if guard_ok:
    confirmed = confirm_trash_dialog(pending_count, pending_size)
    if confirmed:
        st.session_state["trash_confirmed"] = True
        st.rerun()

# ---------------------------------------------------------------------------
# Execution — runs on the rerun after trash_confirmed is set
# ---------------------------------------------------------------------------

if not st.session_state.get("trash_confirmed"):
    st.stop()

pending_ids = st.session_state["pending_trash"]

# Step 1: incremental sync to bring cache up to date
with st.spinner("Syncing mailbox before cleanup..."):
    try:
        incremental_sync(active, service)
    except RuntimeError:
        # No history ID yet (edge case: full sync never completed)
        st.warning(
            "Could not run incremental sync (no history ID stored). "
            "Proceeding with cache as-is."
        )

# Step 2: live label check
with st.spinner(f"Checking labels for {len(pending_ids):,} emails..."):
    check = live_label_check(service, pending_ids)

safe_ids = check["safe"]
blocked_count = len(check["blocked"])
error_count = len(check["errors"])

# Step 3: trash safe messages
if safe_ids:
    with st.spinner(f"Trashing {len(safe_ids):,} emails..."):
        result = trash_messages(active, service, safe_ids)
else:
    result = {"trashed": 0, "size_reclaimed": 0}

# Store result and reset state
st.session_state["last_trash_result"] = {
    "trashed": result["trashed"],
    "size_reclaimed": result["size_reclaimed"],
    "blocked": blocked_count,
    "errors": error_count,
}
st.session_state["pending_trash"] = []
st.session_state["pending_trash_size"] = 0
st.session_state["trash_confirmed"] = False

st.rerun()
