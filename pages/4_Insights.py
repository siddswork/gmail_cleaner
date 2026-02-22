"""
Insights — read behaviour and engagement analysis.

Shows:
  - Read rate per sender (who do you actually read?)
  - Unread breakdown by Gmail category
  - Oldest unread senders (who's been piling up the longest?)
"""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from analysis.insights import read_rate_by_sender, unread_by_label
from cache.database import _connect

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Insights — Gmail Cleaner", layout="wide")

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


def _oldest_unread_senders(account_email: str, limit: int = 20) -> list[dict]:
    """Senders with the oldest most-recent-unread email, excluding starred/important."""
    conn = _connect(account_email)
    rows = conn.execute(
        """
        SELECT
            sender_email,
            sender_name,
            COUNT(*)       AS unread_count,
            SUM(size_estimate) AS total_size,
            MAX(date_ts)   AS latest_unread_ts
        FROM emails
        WHERE is_read = 0
          AND is_starred = 0
          AND is_important = 0
        GROUP BY sender_email
        ORDER BY latest_unread_ts ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

st.title("Insights")
st.caption(f"Account: {active}")

# ---------------------------------------------------------------------------
# Section 1: Read rate by sender
# ---------------------------------------------------------------------------

st.subheader("Read Rate by Sender")
st.caption("How often do you read emails from each sender? Ordered by volume (most emails first).")

with st.sidebar:
    st.header("Filters")
    rr_limit = st.slider("Senders to show", min_value=10, max_value=100, value=50, step=10)

read_rate_data = read_rate_by_sender(active, limit=rr_limit)

if not read_rate_data:
    st.info("No email data cached yet — run a sync from the main page first.")
    st.stop()

df_rr = pd.DataFrame(read_rate_data)
df_rr["read_rate_pct"] = (df_rr["read_rate"] * 100).round(1)
df_rr["unread_count"] = df_rr["total_count"] - df_rr["read_count"]
df_rr["total_size_fmt"] = df_rr.get("total_size", pd.Series([0] * len(df_rr))).apply(
    lambda x: _fmt_size(int(x)) if pd.notna(x) else "—"
)

tab_chart, tab_table = st.tabs(["Chart", "Table"])

with tab_chart:
    labels = [
        f"{r['sender_name'] or r['sender_email']} <{r['sender_email']}>"
        if r.get("sender_name") and r["sender_name"] != r["sender_email"]
        else r["sender_email"]
        for r in read_rate_data
    ]
    hover = [
        f"{r['read_count']:,} read / {r['total_count']:,} total ({r['read_rate'] * 100:.1f}%)"
        for r in read_rate_data
    ]
    # Colour-code by read rate: green = high, red = low
    colors = [
        f"rgba({int(255 * (1 - r['read_rate']))}, {int(180 * r['read_rate'])}, 80, 0.8)"
        for r in read_rate_data
    ]
    fig = go.Figure(go.Bar(
        x=[r["read_rate"] * 100 for r in read_rate_data],
        y=labels,
        orientation="h",
        hovertext=hover,
        hoverinfo="text",
        marker_color=colors,
    ))
    fig.update_layout(
        xaxis_title="Read Rate (%)",
        xaxis={"range": [0, 100]},
        yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
        height=max(300, len(read_rate_data) * 26),
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(fig, use_container_width=True)

with tab_table:
    display_df = df_rr[["sender_email", "sender_name", "total_count", "read_count", "unread_count", "read_rate_pct"]].rename(columns={
        "sender_email": "Email",
        "sender_name": "Name",
        "total_count": "Total",
        "read_count": "Read",
        "unread_count": "Unread",
        "read_rate_pct": "Read Rate (%)",
    })
    st.dataframe(display_df, hide_index=True, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# Section 2: Unread by label
# ---------------------------------------------------------------------------

st.subheader("Unread Emails by Category")
st.caption("How many unread emails are sitting in each Gmail category?")

label_data = unread_by_label(active)

if label_data:
    c1, c2 = st.columns(2)

    clean_labels = [r["category"].replace("CATEGORY_", "").title() for r in label_data]
    hover_labels = [
        f"{lbl}: {r['unread_count']:,} unread · {_fmt_size(r['total_size'])}"
        for lbl, r in zip(clean_labels, label_data)
    ]

    with c1:
        fig_count = go.Figure(go.Bar(
            x=clean_labels,
            y=[r["unread_count"] for r in label_data],
            hovertext=hover_labels,
            hoverinfo="text",
            marker_color="#E8844C",
        ))
        fig_count.update_layout(
            title="Unread Count per Category",
            yaxis_title="Unread emails",
            height=350,
            margin={"l": 20, "r": 20, "t": 40, "b": 20},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_count, use_container_width=True)

    with c2:
        fig_size = go.Figure(go.Bar(
            x=clean_labels,
            y=[r["total_size"] for r in label_data],
            hovertext=[
                f"{lbl}: {_fmt_size(r['total_size'])} · {r['unread_count']:,} emails"
                for lbl, r in zip(clean_labels, label_data)
            ],
            hoverinfo="text",
            marker_color="#7B68EE",
        ))
        fig_size.update_layout(
            title="Unread Size per Category",
            yaxis_title="Total size (bytes)",
            height=350,
            margin={"l": 20, "r": 20, "t": 40, "b": 20},
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_size, use_container_width=True)

    df_labels = pd.DataFrame(label_data)
    df_labels["category"] = df_labels["category"].str.replace("CATEGORY_", "").str.title()
    df_labels["total_size"] = df_labels["total_size"].apply(lambda x: _fmt_size(int(x)))
    st.dataframe(
        df_labels.rename(columns={
            "category": "Category",
            "unread_count": "Unread",
            "total_size": "Total Size",
        }),
        hide_index=True,
        use_container_width=True,
    )
else:
    st.info("No unread emails in any category.")

st.divider()

# ---------------------------------------------------------------------------
# Section 3: Oldest unread senders
# ---------------------------------------------------------------------------

st.subheader("Oldest Unread Senders")
st.caption(
    "Senders whose most recent unread email is the oldest — "
    "you haven't touched their emails in the longest time."
)

oldest = _oldest_unread_senders(active, limit=20)

if oldest:
    df_old = pd.DataFrame(oldest)
    df_old["latest_unread"] = df_old["latest_unread_ts"].apply(_fmt_ts)
    df_old["total_size"] = df_old["total_size"].apply(lambda x: _fmt_size(int(x)) if pd.notna(x) else "—")
    st.dataframe(
        df_old[["sender_email", "sender_name", "unread_count", "total_size", "latest_unread"]].rename(columns={
            "sender_email": "Email",
            "sender_name": "Name",
            "unread_count": "Unread",
            "total_size": "Size",
            "latest_unread": "Last Unread",
        }),
        hide_index=True,
        use_container_width=True,
    )
    st.caption("Tip: senders with an unsubscribe link appear on the Unsubscribe page.")
else:
    st.info("No unread emails found.")
