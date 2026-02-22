"""
Dashboard — storage analysis for the active Gmail account.

Shows:
  - Overall stats header (total emails, total size, read/unread, date range)
  - Top senders by count and by size
  - Category breakdown
  - Email volume over time
"""
import pandas as pd
import streamlit as st

from analysis.aggregator import (
    category_breakdown,
    overall_stats,
    storage_timeline,
    top_senders_by_count,
    top_senders_by_size,
)
from components.charts import category_bar, senders_bar, timeline_line
from components.filters import (
    apply_filters,
    date_range_filter,
    label_filter,
    sender_filter,
    size_filter,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Dashboard — Gmail Cleaner", layout="wide")

# ---------------------------------------------------------------------------
# Guard: require an active account
# ---------------------------------------------------------------------------

active = st.session_state.get("active_account")
if not active:
    st.warning("Connect a Gmail account from the main page first.")
    st.stop()

# ---------------------------------------------------------------------------
# Overall stats header
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
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %Y")


st.title("Dashboard")
st.caption(f"Account: {active}")

stats = overall_stats(active)

if stats["total_count"] == 0:
    st.info(
        "No emails cached yet. Run a sync from the main page to populate the dashboard."
    )
    st.stop()

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Total emails", f"{stats['total_count']:,}")
col2.metric("Total size", _fmt_size(stats["total_size"]))
col3.metric("Unread", f"{stats['unread_count']:,}")
col4.metric("Starred", f"{stats['starred_count']:,}")
col5.metric(
    "Date range",
    f"{_fmt_ts(stats['oldest_ts'])} – {_fmt_ts(stats['newest_ts'])}",
)

st.divider()

# ---------------------------------------------------------------------------
# Sidebar filters (applied to the senders tables)
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Filters")
    start_ts, end_ts = date_range_filter()
    sender_q = sender_filter()
    selected_labels = label_filter(
        ["INBOX", "CATEGORY_PROMOTIONS", "CATEGORY_UPDATES",
         "CATEGORY_SOCIAL", "CATEGORY_FORUMS", "SENT"]
    )
    min_size, max_size = size_filter()
    unread_only = st.checkbox("Unread only", key="filter_unread")

active_filters = {
    "start_ts": start_ts,
    "end_ts": end_ts,
    "sender": sender_q,
    "labels": selected_labels,
    "min_size": min_size,
    "max_size": max_size,
    "unread_only": unread_only,
}

# ---------------------------------------------------------------------------
# Top senders
# ---------------------------------------------------------------------------

st.subheader("Top Senders")

tab_count, tab_size = st.tabs(["By email count", "By total size"])

with tab_count:
    raw = top_senders_by_count(active, limit=50)
    df = pd.DataFrame(raw) if raw else pd.DataFrame()
    df = apply_filters(df, active_filters) if not df.empty else df
    st.plotly_chart(
        senders_bar(df.to_dict("records") if not df.empty else [], metric="count",
                    title="Top Senders by Email Count"),
        use_container_width=True,
    )
    if not df.empty:
        st.dataframe(
            df[["sender_email", "sender_name", "count", "total_size"]]
            .rename(columns={"sender_email": "Email", "sender_name": "Name",
                             "count": "Emails", "total_size": "Total Size (bytes)"}),
            hide_index=True,
            use_container_width=True,
        )

with tab_size:
    raw = top_senders_by_size(active, limit=50)
    df = pd.DataFrame(raw) if raw else pd.DataFrame()
    df = apply_filters(df, active_filters) if not df.empty else df
    st.plotly_chart(
        senders_bar(df.to_dict("records") if not df.empty else [], metric="total_size",
                    title="Top Senders by Total Size"),
        use_container_width=True,
    )
    if not df.empty:
        st.dataframe(
            df[["sender_email", "sender_name", "total_size", "count"]]
            .rename(columns={"sender_email": "Email", "sender_name": "Name",
                             "total_size": "Total Size (bytes)", "count": "Emails"}),
            hide_index=True,
            use_container_width=True,
        )

st.divider()

# ---------------------------------------------------------------------------
# Category breakdown
# ---------------------------------------------------------------------------

st.subheader("Emails by Category")

cat_data = category_breakdown(active)

if cat_data:
    c1, c2 = st.columns(2)
    with c1:
        st.plotly_chart(
            category_bar(cat_data, metric="count", title="Count per Category"),
            use_container_width=True,
        )
    with c2:
        st.plotly_chart(
            category_bar(cat_data, metric="total_size", title="Size per Category"),
            use_container_width=True,
        )
else:
    st.info("No category data available.")

st.divider()

# ---------------------------------------------------------------------------
# Storage timeline
# ---------------------------------------------------------------------------

st.subheader("Email Volume Over Time")

granularity = st.radio(
    "Granularity", ["month", "year"], horizontal=True, key="timeline_granularity"
)
timeline_data = storage_timeline(active, granularity=granularity)
st.plotly_chart(
    timeline_line(timeline_data, title="Email Volume Over Time"),
    use_container_width=True,
)
