"""
Plotly chart wrappers for the Dashboard.

All functions accept aggregated data (list[dict]) and return Plotly figures.
No Streamlit dependency — call st.plotly_chart(fig) in the page layer.
"""
import plotly.graph_objects as go


def _fmt_size(bytes_val: int) -> str:
    """Human-readable size label for hover text."""
    if bytes_val >= 1_073_741_824:
        return f"{bytes_val / 1_073_741_824:.1f} GB"
    if bytes_val >= 1_048_576:
        return f"{bytes_val / 1_048_576:.1f} MB"
    if bytes_val >= 1_024:
        return f"{bytes_val / 1_024:.1f} KB"
    return f"{bytes_val} B"


def senders_bar(
    data: list[dict],
    metric: str = "count",
    title: str = "Top Senders",
) -> go.Figure:
    """
    Horizontal bar chart of top senders.

    Args:
        data:   list of dicts with keys sender_email, sender_name, count, total_size
        metric: "count" or "total_size"
        title:  chart title
    """
    if not data:
        return _empty_figure(title)

    labels = [
        f"{r['sender_name'] or r['sender_email']} <{r['sender_email']}>"
        if r.get("sender_name") and r["sender_name"] != r["sender_email"]
        else r["sender_email"]
        for r in data
    ]
    values = [r[metric] for r in data]

    if metric == "total_size":
        hover = [
            f"{_fmt_size(r['total_size'])} · {r['count']} emails"
            for r in data
        ]
        x_title = "Total Size"
    else:
        hover = [
            f"{r['count']} emails · {_fmt_size(r['total_size'])}"
            for r in data
        ]
        x_title = "Email Count"

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        hovertext=hover,
        hoverinfo="text",
        marker_color="#4C9BE8",
    ))
    fig.update_layout(
        title=title,
        xaxis_title=x_title,
        yaxis={"autorange": "reversed", "tickfont": {"size": 11}},
        height=max(300, len(data) * 28),
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def category_bar(
    data: list[dict],
    metric: str = "count",
    title: str = "Emails by Category",
) -> go.Figure:
    """
    Bar chart of email count or size per Gmail category.

    Args:
        data:   list of dicts with keys category, count, total_size
        metric: "count" or "total_size"
        title:  chart title
    """
    if not data:
        return _empty_figure(title)

    # Strip "CATEGORY_" prefix for display
    labels = [r["category"].replace("CATEGORY_", "").title() for r in data]
    values = [r[metric] for r in data]

    if metric == "total_size":
        hover = [
            f"{label}: {_fmt_size(r['total_size'])} · {r['count']} emails"
            for label, r in zip(labels, data)
        ]
        y_title = "Total Size (bytes)"
    else:
        hover = [
            f"{label}: {r['count']} emails · {_fmt_size(r['total_size'])}"
            for label, r in zip(labels, data)
        ]
        y_title = "Email Count"

    fig = go.Figure(go.Bar(
        x=labels,
        y=values,
        hovertext=hover,
        hoverinfo="text",
        marker_color="#7B68EE",
    ))
    fig.update_layout(
        title=title,
        yaxis_title=y_title,
        height=350,
        margin={"l": 20, "r": 20, "t": 40, "b": 20},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def timeline_line(
    data: list[dict],
    title: str = "Email Volume Over Time",
) -> go.Figure:
    """
    Dual-axis line chart: email count (left axis) and cumulative size (right axis).

    Args:
        data:  list of dicts with keys period, count, total_size — ordered chronologically
        title: chart title
    """
    if not data:
        return _empty_figure(title)

    periods = [r["period"] for r in data]
    counts = [r["count"] for r in data]
    sizes = [r["total_size"] for r in data]

    cumulative_sizes = []
    running = 0
    for s in sizes:
        running += s
        cumulative_sizes.append(running)

    hover_counts = [f"{p}: {c} emails" for p, c in zip(periods, counts)]
    hover_sizes = [f"{p}: {_fmt_size(s)} cumulative" for p, s in zip(periods, cumulative_sizes)]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=periods,
        y=counts,
        name="Emails / period",
        mode="lines+markers",
        hovertext=hover_counts,
        hoverinfo="text",
        line={"color": "#4C9BE8", "width": 2},
        marker={"size": 4},
    ))

    fig.add_trace(go.Scatter(
        x=periods,
        y=cumulative_sizes,
        name="Cumulative size",
        mode="lines",
        hovertext=hover_sizes,
        hoverinfo="text",
        line={"color": "#FF7F7F", "width": 2, "dash": "dot"},
        yaxis="y2",
    ))

    fig.update_layout(
        title=title,
        xaxis_title="Period",
        yaxis={"title": "Email Count", "side": "left"},
        yaxis2={
            "title": "Cumulative Size (bytes)",
            "side": "right",
            "overlaying": "y",
        },
        legend={"orientation": "h", "y": -0.2},
        height=380,
        margin={"l": 20, "r": 60, "t": 40, "b": 60},
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
    )
    return fig


def _empty_figure(title: str) -> go.Figure:
    """Return a blank figure with a 'No data' annotation."""
    fig = go.Figure()
    fig.update_layout(
        title=title,
        height=300,
        annotations=[{
            "text": "No data — run a sync first",
            "xref": "paper", "yref": "paper",
            "x": 0.5, "y": 0.5,
            "showarrow": False,
            "font": {"size": 14, "color": "gray"},
        }],
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig
