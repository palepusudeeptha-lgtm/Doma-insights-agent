"""Plotly chart builders for the operations dashboard."""

import datetime

import plotly.graph_objects as go

from metrics import order_volume_sla_sql, tat_by_decision_sql

# Shared height for the 3 dashboard chart/table cards so they line up evenly
# in their row regardless of content (2 Plotly figures + 1 st.dataframe).
# Chosen to be a clean fit for the state table's header + 6 rows (~35px each)
# so it doesn't show a half-empty trailing row -- the remaining 4 states
# scroll within the fixed-height table rather than growing the card.
DASHBOARD_CARD_HEIGHT = 245

# Matches the app-wide CSS font (app.py). Set explicitly on every chart's own
# layout.font -- rather than relying on the page's CSS to reskin the chart
# after the fact -- so Plotly calculates its own label/margin sizing against
# the font it will actually render, instead of clipping a label that renders
# wider under the CSS-swapped font than Plotly reserved room for.
CHART_FONT = "IBM Plex Sans, system-ui, sans-serif"

# Matches app.py's ACCENT -- keep both in sync. A softened, warm-leaning blue
# instead of Plotly/Streamlit's more vivid default, to suit the warm-neutral
# background. _LIGHT is used only where a second series overlays the bars
# (the SLA % line) and needs to read as a distinct trace, not a new hue.
CHART_ACCENT = "#4F6FA8"
CHART_ACCENT_LIGHT = "#93AAC9"


def order_volume_sla_chart(con, where_sql: str, params: list):
    """Bar chart of monthly order volume with SLA compliance % as a line overlay."""
    rows = con.execute(order_volume_sla_sql(where_sql), params).fetchall()

    months = [r[0] for r in rows]
    volumes = [r[1] for r in rows]
    sla = [r[2] for r in rows]

    fig = go.Figure()
    fig.add_bar(x=months, y=volumes, name="Order Volume", yaxis="y1", marker_color=CHART_ACCENT)
    fig.add_trace(
        go.Scatter(
            x=months, y=sla, name="SLA Compliance %", yaxis="y2", mode="lines+markers",
            line=dict(color=CHART_ACCENT_LIGHT, width=2), marker=dict(color=CHART_ACCENT_LIGHT),
        )
    )
    fig.update_layout(
        yaxis=dict(title="Order Volume"),
        yaxis2=dict(title="SLA Compliance %", overlaying="y", side="right", range=[0, 100]),
        legend=dict(orientation="h", y=1.15),
        margin=dict(t=30, b=30),
        height=DASHBOARD_CARD_HEIGHT,
        font=dict(family=CHART_FONT),
    )
    return fig


def tat_by_decision_chart(con, where_sql: str, params: list):
    """Horizontal bar chart of average turnaround time by decision type."""
    rows = con.execute(tat_by_decision_sql(where_sql), params).fetchall()

    labels = [r[0] for r in rows]
    values = [r[1] for r in rows]

    fig = go.Figure(
        go.Bar(
            x=values,
            y=labels,
            orientation="h",
            text=[f"{v:.1f}" for v in values],
            textposition="outside",
            marker_color=CHART_ACCENT,
        )
    )
    fig.update_layout(
        xaxis_title="Avg Turnaround Time (hrs)",
        # automargin: without it, Plotly's default left margin doesn't
        # reserve enough room for the longest y-axis label ("Automated
        # Review") and clips it -- automargin resizes to fit instead of a
        # fixed guess, which also holds up if a label changes length later.
        yaxis=dict(automargin=True),
        margin=dict(t=30, b=30),
        height=DASHBOARD_CARD_HEIGHT,
        font=dict(family=CHART_FONT),
    )
    return fig


def _is_time_like(values: list) -> bool:
    return bool(values) and all(isinstance(v, (datetime.date, datetime.datetime)) for v in values)


def _is_numeric(values: list) -> bool:
    return bool(values) and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values)


def sort_for_display(columns: list, rows: list) -> list:
    """
    Sort an AI answer's rows for consistent table + chart display.

    The LLM doesn't always include an ORDER BY, so row order can't be
    trusted as-is. A date/timestamp label column (index 0) sorts
    chronologically ascending, so a trend reads left-to-right in time
    order -- sorting it by value instead would scramble a weekly/monthly
    trend into a meaningless order. Otherwise, when the value column
    (index 1) is numeric, sorts descending so the largest value leads,
    matching "top N" / ranking questions. Anything else keeps the SQL's
    own row order.
    """
    if not rows or len(columns) < 2:
        return rows

    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]

    if _is_time_like(labels):
        return sorted(rows, key=lambda row: row[0])
    if _is_numeric(values):
        return sorted(rows, key=lambda row: row[1], reverse=True)
    return rows


def classify_response_shape(columns: list, rows: list) -> str:
    """
    Classify an AI answer's result shape for adaptive-response decisions.

    This is the single source of truth `auto_chart` builds on, and later
    steps (e.g. deciding whether a "Key Drivers" section makes sense) reuse
    it too -- so the definition of "this looks like a trend" etc. only
    lives in one place. Returns one of:

      "single_value"  -- 0 or 1 rows: a KPI-style answer (e.g. "what is our
                         SLA compliance?"). No chart adds anything here.
      "time_series"   -- a date/timestamp label column + numeric value,
                         a sane number of points: a trend over time.
      "categorical"   -- a categorical (string) label + numeric value, few
                         enough rows to read as a chart: a ranking or
                         breakdown ("top N" / "X by Y" style questions).
      "record_table"  -- anything else: too many columns, too many rows,
                         a non-numeric value column, or only one column
                         across many rows. A record-level lookup where the
                         table alone already tells the story.
    """
    if len(rows) < 2:
        return "single_value"
    if len(columns) < 2:
        return "record_table"

    labels = [row[0] for row in rows]
    values = [row[1] for row in rows]

    if not _is_numeric(values):
        return "record_table"
    if _is_time_like(labels):
        return "time_series" if len(rows) <= 200 else "record_table"
    if all(isinstance(v, str) for v in labels) and len(rows) <= 25:
        return "categorical"
    return "record_table"


def auto_chart(columns: list, rows: list):
    """
    Best-effort chart for an AI answer, based on classify_response_shape():

    - "time_series" -> line chart, chronological left to right
    - "categorical" -> horizontal bar chart ("top N" / "X by Y" questions)
    - anything else -> None (no chart) -- the table alone already tells
      the story for a single-value KPI answer or a record-level lookup.

    Assumes `rows` is already in the desired display order (see
    sort_for_display) -- this function doesn't re-sort.
    """
    shape = classify_response_shape(columns, rows)

    if shape == "time_series":
        labels = [row[0] for row in rows]
        values = [row[1] for row in rows]
        fig = go.Figure(
            go.Scatter(
                x=labels, y=values, mode="lines+markers",
                line=dict(width=2, color=CHART_ACCENT), marker=dict(size=8, color=CHART_ACCENT),
            )
        )
        fig.update_layout(
            xaxis_title=columns[0],
            yaxis_title=columns[1],
            margin=dict(t=30, b=30),
            font=dict(family=CHART_FONT),
        )
        return fig

    if shape == "categorical":
        labels = [row[0] for row in rows]
        values = [row[1] for row in rows]
        fig = go.Figure(
            go.Bar(
                x=values,
                y=labels,
                orientation="h",
                text=[f"{v:,.2f}" if isinstance(v, float) else f"{v:,}" for v in values],
                textposition="outside",
                marker_color=CHART_ACCENT,
            )
        )
        fig.update_layout(
            xaxis_title=columns[1],
            # autorange="reversed" keeps the given row order (already sorted
            # "top N" style by sort_for_display) reading top-to-bottom
            # instead of Plotly's default bottom-to-top for bars.
            # automargin=True: these labels are arbitrary AI-answer category
            # names of unpredictable length (a state code, a full vendor
            # name, an exception type) -- a fixed margin guess would either
            # clip a long one or waste space on a short one.
            yaxis=dict(autorange="reversed", automargin=True),
            margin=dict(t=30, b=30),
            font=dict(family=CHART_FONT),
        )
        return fig

    return None


def format_row_for_display(row: tuple) -> tuple:
    """Render date/timestamp values as plain ISO dates (no time-of-day) for text display."""
    return tuple(
        v.strftime("%Y-%m-%d") if isinstance(v, (datetime.date, datetime.datetime)) else v
        for v in row
    )
