"""Doma Title Operations Insights -- Streamlit dashboard."""

import base64
from datetime import timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

import charts
from agent import ask
from database import get_connection
from metrics import METRIC_DEFINITIONS, kpi_summary_sql, ta_eligibility_by_state_sql

LOGO_B64 = base64.b64encode(Path(__file__).parent.joinpath("doma_logo.png").read_bytes()).decode()

# --- Design tokens: warm-neutral palette, one restrained accent (unchanged
# Doma blue), status colors reserved for real signal (trend arrows only). ---
BG_PAGE = "#F7F5F1"
BG_CARD = "#FFFFFF"
BG_INPUT = "#FAF9F6"  # filters + the question input + the "how calculated" expander
BORDER = "#E7E2D9"
TEXT_PRIMARY = "#1C1917"
TEXT_BODY = "#44403C"
TEXT_SECONDARY = "#6B6459"
TEXT_TERTIARY = "#8B8377"
ACCENT = "#2563EB"
SUCCESS = "#15803D"
DANGER = "#B42318"
ICON_BG = "#F1EDE5"
ICON_COLOR = "#1C1917"

_ARROW_UP = '<svg width="9" height="9" viewBox="0 0 10 10" fill="currentColor"><path d="M5 1l4 6H1z"/></svg>'
_ARROW_DOWN = '<svg width="9" height="9" viewBox="0 0 10 10" fill="currentColor"><path d="M5 9L1 3h8z"/></svg>'

# Single-weight line icons (no per-card color) -- replaces the earlier emoji set.
_ICON_TOTAL_ORDERS = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M7 3h7l4 4v13a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/>'
    '<path d="M14 3v4h4"/><path d="M9 12h6M9 16h6"/></svg>'
)
_ICON_SLA = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M8.5 12.5l2.5 2.5 4.5-5"/></svg>'
)
_ICON_CLOCK = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/></svg>'
)
_ICON_GEAR = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/>'
    '<path d="M12 3.5v2M12 18.5v2M20.5 12h-2M5.5 12h-2M17.8 6.2l-1.4 1.4M7.6 16.4l-1.4 1.4M17.8 17.8l-1.4-1.4M7.6 7.6L6.2 6.2"/></svg>'
)
_ICON_ALERT = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M12 4.5l9 15.5H3l9-15.5z"/><path d="M12 10v3.2"/>'
    '<circle cx="12" cy="16.6" r="0.9" fill="currentColor" stroke="none"/></svg>'
)
_ICON_SAVINGS = (
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" '
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/>'
    '<path d="M12 7.5v9M14.5 9.5c0-1-1-1.5-2.5-1.5s-2.5.6-2.5 1.6c0 2.2 5 1 5 3.2 0 1-1 1.7-2.5 1.7s-2.5-.6-2.5-1.6"/></svg>'
)

KPI_FIELDS = [
    "total_orders",
    "sla_compliance_pct",
    "avg_turnaround_hours",
    "automation_rate_pct",
    "exception_rate_pct",
    "estimated_borrower_savings",
]

# label, icon, value formatter, higher-is-better (for trend color: e.g. a
# turnaround-time *increase* is bad, so it renders red)
KPI_DISPLAY = [
    ("total_orders", "Total Orders", _ICON_TOTAL_ORDERS, lambda v: f"{v:,}", True),
    ("sla_compliance_pct", "SLA Compliance", _ICON_SLA, lambda v: f"{v:.1f}%", True),
    ("avg_turnaround_hours", "Avg Turnaround Time", _ICON_CLOCK, lambda v: f"{v:.1f} hrs", False),
    ("automation_rate_pct", "Automation Rate", _ICON_GEAR, lambda v: f"{v:.1f}%", True),
    ("exception_rate_pct", "Exception Rate", _ICON_ALERT, lambda v: f"{v:.1f}%", False),
    ("estimated_borrower_savings", "Est. Borrower Savings", _ICON_SAVINGS, lambda v: f"${v / 1_000_000:.1f}M", True),
]

EXAMPLE_QUESTIONS = [
    "What are the top 5 vendors by order volume?",
    "Why did exception rate increase this month?",
    "Show SLA compliance by state.",
    "Which orders are at risk of missing SLA?",
    "What is the average turnaround time by lender?",
]


def render_kpi_card(icon_svg: str, label: str, value: str, delta_pct, higher_is_better: bool) -> None:
    """One KPI card: neutral icon badge, label, big value, and a colored vs.-prior-week trend line."""
    if delta_pct is None:
        trend_html = f'<div style="font-size:12px;color:{TEXT_TERTIARY};">No prior-week data</div>'
    else:
        if delta_pct > 0:
            arrow, favorable = _ARROW_UP, higher_is_better
        elif delta_pct < 0:
            arrow, favorable = _ARROW_DOWN, not higher_is_better
        else:
            arrow, favorable = "–", None
        color = TEXT_TERTIARY if favorable is None else (SUCCESS if favorable else DANGER)
        trend_html = (
            f'<div style="display:flex;align-items:center;gap:5px;font-size:13px;color:{color};font-weight:600;">'
            f'{arrow}{abs(delta_pct):.1f}% <span style="color:{TEXT_TERTIARY};font-weight:400;">vs. prior week</span></div>'
        )

    st.markdown(
        f"""
        <div style="background:{BG_CARD};border:1px solid {BORDER};border-radius:12px;padding:18px 20px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
            <div style="width:38px;height:38px;min-width:38px;border-radius:50%;background:{ICON_BG};
                        display:flex;align-items:center;justify-content:center;color:{ICON_COLOR};">{icon_svg}</div>
            <div style="font-size:13px;color:{TEXT_SECONDARY};font-weight:500;">{label}</div>
          </div>
          <div style="font-size:28px;font-weight:700;color:{TEXT_PRIMARY};margin-bottom:8px;letter-spacing:-0.01em;">{value}</div>
          {trend_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_observability(obs: dict) -> None:
    """
    UX Step 5: per-response technical metadata -- model, token usage, cost,
    rows analyzed, and latency. Every value here is captured from the real
    pipeline (agent.py's `observability` dict, itself built from
    response.usage and time.perf_counter() at each stage) -- nothing here
    is a placeholder or hardcoded figure. "Rows Analyzed" shows "-" when
    unavailable (a rejected question never executed a query; a failed
    query has no row count) rather than a fabricated number.
    """
    total_tokens = obs["total_input_tokens"] + obs["total_output_tokens"]
    rows_analyzed = obs.get("sql_execution", {}).get("rows_returned")

    m1, m2, m3, m4, m5, m6, m7 = st.columns([1.3, 1, 1, 1, 1, 1, 1])
    m1.metric("Model", obs["model"])
    m2.metric("Rows Analyzed", f"{rows_analyzed:,}" if rows_analyzed is not None else "—")
    m3.metric("Input Tokens", f"{obs['total_input_tokens']:,}")
    m4.metric("Output Tokens", f"{obs['total_output_tokens']:,}")
    m5.metric("Total Tokens", f"{total_tokens:,}")
    m6.metric("Cost", f"${obs['total_cost_usd']:.4f}")
    m7.metric("Latency", f"{obs['total_latency_seconds']:.2f}s")

    detail_lines = [
        f"- SQL generation: {obs['sql_generation']['input_tokens']:,} in / "
        f"{obs['sql_generation']['output_tokens']:,} out tokens, "
        f"{obs['sql_generation']['latency_seconds']:.2f}s"
    ]
    if "sql_execution" in obs:
        detail_lines.append(f"- Query execution: {obs['sql_execution']['latency_seconds']:.3f}s")
    if "explanation" in obs:
        detail_lines.append(
            f"- Result explanation: {obs['explanation']['input_tokens']:,} in / "
            f"{obs['explanation']['output_tokens']:,} out tokens, "
            f"{obs['explanation']['latency_seconds']:.2f}s"
        )
    st.caption("\n".join(detail_lines))

st.set_page_config(page_title="Doma Title Operations Insights", layout="wide")

# Page-level styling: pale blue page background with the card sections (charts,
# Ask Doma AI) kept white for contrast, plus the pill/send-button/font tweaks
# requested for the Ask Doma AI section. Cards are targeted via `key=` on their
# st.container(border=True) calls below, which Streamlit turns into a stable
# `st-key-<key>` class -- the alternative (Streamlit's own auto-generated
# emotion-cache classes) changes across sessions/versions, so it isn't safe to
# select directly.
st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

    /* One deliberate typeface app-wide, excluding code blocks (need a
       monospace font), the Material icon glyph (needs its icon font --
       overriding it would render literal text like "send" instead), and
       Plotly charts (they get the same font explicitly via each chart's
       own layout.font in charts.py instead -- a CSS override here would
       swap the rendered font AFTER Plotly has already calculated its
       margins for a different font's character widths, clipping labels
       that render wider than Plotly reserved space for). */
    [data-testid="stAppViewContainer"] *:not(code):not(pre):not(pre *):not([data-testid="stIconMaterial"]):not([data-testid="stPlotlyChart"] *) {{
        font-family: 'IBM Plex Sans', system-ui, -apple-system, sans-serif !important;
    }}

    [data-testid="stAppViewContainer"] {{
        background-color: {BG_PAGE};
    }}
    .st-key-header_card, .st-key-chart_card_1, .st-key-chart_card_2, .st-key-chart_card_3, .st-key-ask_doma_card {{
        background-color: {BG_CARD} !important;
        border: 1px solid {BORDER} !important;
        box-shadow: 0 2px 8px rgba(28, 25, 23, 0.08);
        border-radius: 14px !important;
    }}
    .st-key-ask_doma_card {{
        padding: 34px 38px !important;
    }}
    .st-key-header_card [data-testid="stSelectbox"] [role="group"],
    .st-key-header_card [data-testid="stDateInputField"] {{
        background-color: {BG_INPUT} !important;
    }}
    .st-key-ask_doma_card [data-testid="stCaptionContainer"] p {{
        font-size: 15px !important;
    }}
    /* Question input + send button, merged into one pill: the container
       carries the shared background/border, the input itself goes
       transparent so it reads as one control instead of two adjacent ones. */
    .st-key-ask_input_row {{
        background-color: {BG_INPUT} !important;
        border: 1px solid {BORDER} !important;
        border-radius: 999px !important;
        padding: 6px 6px 6px 22px !important;
    }}
    .st-key-ask_input_row [data-testid="stTextInputRootElement"] {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
    }}
    .st-key-ask_input_row input {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding-left: 0 !important;
        font-size: 18px !important;
    }}
    /* "How this answer was calculated" expander: match the question
       input's fill and font size, so it reads as part of the same section
       instead of a visually distinct default Streamlit expander. */
    .st-key-ask_doma_card [data-testid="stExpander"] {{
        background-color: {BG_INPUT} !important;
        border-radius: 10px !important;
    }}
    .st-key-ask_doma_card [data-testid="stExpander"] summary {{
        background-color: {BG_INPUT} !important;
        font-size: 17px !important;
        border-radius: 10px !important;
    }}
    .st-key-ask_doma_card [data-testid="stExpander"] p {{
        font-size: 17px !important;
    }}
    button[data-variant="pills"] {{
        background-color: #F3F6FE !important;
        border-color: #DCE5FB !important;
    }}
    button[data-variant="pills"] span {{
        color: {ACCENT} !important;
        font-weight: 600 !important;
    }}
    .st-key-ask_send_btn button {{
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
        min-width: 40px !important;
        padding: 0 !important;
        background-color: {ACCENT} !important;
        border-color: {ACCENT} !important;
    }}
    .st-key-ask_send_btn button span {{
        color: #FFFFFF !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

con = get_connection(read_only=True)

lenders = [r[0] for r in con.execute("SELECT DISTINCT lender FROM title_orders ORDER BY lender").fetchall()]
states = [r[0] for r in con.execute("SELECT DISTINCT state FROM title_orders ORDER BY state").fetchall()]
vendors = [r[0] for r in con.execute("SELECT DISTINCT vendor_name FROM title_orders ORDER BY vendor_name").fetchall()]
property_types = [r[0] for r in con.execute("SELECT DISTINCT property_type FROM title_orders ORDER BY property_type").fetchall()]
min_date, max_date = con.execute("SELECT MIN(order_date), MAX(order_date) FROM title_orders").fetchone()

# --- Header + filters (boxed together, separated from the rest of the page) ---
with st.container(border=True, key="header_card"):
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:20px; padding:4px 0 16px 0;">
          <img src="data:image/png;base64,{LOGO_B64}" style="height:40px; width:auto;" alt="doma" />
          <div>
            <div style="font-size:32px; font-weight:700; color:{TEXT_PRIMARY}; line-height:1.15; letter-spacing:-0.01em;">Title Operations Insights</div>
            <div style="font-size:15px; color:{TEXT_SECONDARY};">Ask questions. Get real answers. Powered by your data.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    f1, f2, f3, f4, f5 = st.columns(5)
    date_range = f1.date_input(
        "Date Range",
        value=(min_date.date(), max_date.date()),
        min_value=min_date.date(),
        max_value=max_date.date(),
    )
    lender_filter = f2.selectbox("Lender", ["All Lenders"] + lenders)
    state_filter = f3.selectbox("State", ["All States"] + states)
    vendor_filter = f4.selectbox("Vendor", ["All Vendors"] + vendors)
    property_type_filter = f5.selectbox("Property Type", ["All Property Types"] + property_types)

# --- Build WHERE clause from filters ---
# where_sql is built entirely from our own code (never raw user text), so
# it's safe to interpolate into the query string. The actual filter
# *values* the user picked go through ? placeholders below.
where_clauses = ["order_date BETWEEN ? AND ?"]
params = [date_range[0], date_range[1]] if len(date_range) == 2 else [min_date.date(), max_date.date()]
if lender_filter != "All Lenders":
    where_clauses.append("lender = ?")
    params.append(lender_filter)
if state_filter != "All States":
    where_clauses.append("state = ?")
    params.append(state_filter)
if vendor_filter != "All Vendors":
    where_clauses.append("vendor_name = ?")
    params.append(vendor_filter)
if property_type_filter != "All Property Types":
    where_clauses.append("property_type = ?")
    params.append(property_type_filter)
where_sql = " AND ".join(where_clauses)

# --- KPI row ---
kpi_values = dict(zip(KPI_FIELDS, con.execute(kpi_summary_sql(where_sql, KPI_FIELDS), params).fetchone()))

# "vs. prior week" trend: anchored on the selected date range's end date (not
# its start), so narrowing/widening the range doesn't change what "current"
# means -- current week = the 7 days ending there, prior week = the 7 before
# that. Lender/State filters still apply, so a filtered view gets its own trend.
week_end = date_range[1] if len(date_range) == 2 else max_date.date()
current_week = (week_end - timedelta(days=6), week_end)
prior_week = (current_week[0] - timedelta(days=7), current_week[0] - timedelta(days=1))

trend_base_clauses, trend_base_params = [], []
if lender_filter != "All Lenders":
    trend_base_clauses.append("lender = ?")
    trend_base_params.append(lender_filter)
if state_filter != "All States":
    trend_base_clauses.append("state = ?")
    trend_base_params.append(state_filter)
if vendor_filter != "All Vendors":
    trend_base_clauses.append("vendor_name = ?")
    trend_base_params.append(vendor_filter)
if property_type_filter != "All Property Types":
    trend_base_clauses.append("property_type = ?")
    trend_base_params.append(property_type_filter)


def _week_kpis(start, end):
    week_where = " AND ".join(["order_date BETWEEN ? AND ?"] + trend_base_clauses)
    week_params = [start, end] + trend_base_params
    row = con.execute(kpi_summary_sql(week_where, KPI_FIELDS), week_params).fetchone()
    return dict(zip(KPI_FIELDS, row))


current_week_kpis = _week_kpis(*current_week)
prior_week_kpis = _week_kpis(*prior_week)

st.divider()
kpi_cols = st.columns(6)
for col, (field, label, icon, fmt, higher_is_better) in zip(kpi_cols, KPI_DISPLAY):
    current_val, prior_val = current_week_kpis[field], prior_week_kpis[field]
    delta_pct = (
        (current_val - prior_val) / prior_val * 100
        if current_val is not None and prior_val
        else None
    )
    with col:
        render_kpi_card(icon, label, fmt(kpi_values[field]), delta_pct, higher_is_better)

def render_chart_title(text: str) -> None:
    """Chart-card title, sized to fit the smaller chart cards."""
    st.markdown(
        f'<div style="font-size:18px; font-weight:600; color:{TEXT_PRIMARY}; margin-bottom:8px; letter-spacing:-0.005em;">{text}</div>',
        unsafe_allow_html=True,
    )


# --- Charts + Title Acceptance Eligibility by State (same row) ---
st.divider()
c1, c2, c3 = st.columns(3)
with c1, st.container(border=True, key="chart_card_1"):
    render_chart_title("Order Volume & SLA Compliance")
    st.plotly_chart(charts.order_volume_sla_chart(con, where_sql, params), width="stretch")
with c2, st.container(border=True, key="chart_card_2"):
    render_chart_title("Turnaround Time by Decision Type")
    st.plotly_chart(charts.tat_by_decision_chart(con, where_sql, params), width="stretch")
with c3, st.container(border=True, key="chart_card_3"):
    render_chart_title("Title Acceptance Eligibility by State")
    state_rows = con.execute(ta_eligibility_by_state_sql(where_sql), params).fetchall()
    state_df = pd.DataFrame(state_rows, columns=["State", "Total Orders", "Title Acceptance Eligible %"])
    state_df["Title Acceptance Eligible %"] = state_df["Title Acceptance Eligible %"].map("{:.2f}%".format)
    st.dataframe(state_df, width="stretch", hide_index=True, height=charts.DASHBOARD_CARD_HEIGHT)

def _apply_example_question():
    picked = st.session_state.get("example_pills")
    if picked:
        st.session_state["question_input"] = picked
        st.session_state["example_pills"] = None


def _format_row_for_table(row):
    row = charts.format_row_for_display(row)  # dates -> "YYYY-MM-DD", no time-of-day
    return tuple(f"{v:.2f}" if isinstance(v, float) else v for v in row)


SUPPORTING_TABLE_ROW_CAP = 10


def render_supporting_table(columns: list, display_rows: list) -> None:
    """
    UX Step 3: show only the first N rows inline as a small supporting
    table, with a "View supporting data" expander holding the complete
    result when there are more rows than that -- avoids dumping a huge raw
    table into the main response by default. `display_rows` is expected to
    already be sorted (see sort_for_display), so "first N" means "most
    relevant N" for ranking-shaped answers (highest values first) and
    "earliest N" for a time series.
    """
    table_rows = [_format_row_for_table(row) for row in display_rows]
    answer_df = pd.DataFrame(table_rows, columns=columns)

    if len(answer_df) > SUPPORTING_TABLE_ROW_CAP:
        st.caption(f"Supporting Data -- top {SUPPORTING_TABLE_ROW_CAP} of {len(answer_df)} rows")
        st.dataframe(answer_df.head(SUPPORTING_TABLE_ROW_CAP), width="stretch", hide_index=True)
        with st.expander(f"View supporting data ({len(answer_df)} rows)"):
            st.dataframe(answer_df, width="stretch", hide_index=True)
    else:
        st.caption("Supporting Data")
        st.dataframe(answer_df, width="stretch", hide_index=True)


def render_how_calculated(result: dict) -> None:
    """
    UX Step 4: "How this answer was calculated" -- metric definitions
    actually used, the active filters, the generated SQL, and the
    observability metrics from the existing pipeline.

    Metric matching is by column name against the same governed
    METRIC_DEFINITIONS the SQL-generation prompt is given as expected
    aliases (see agent.SYSTEM_PROMPT) -- so this reuses the one existing
    source of truth rather than asking the model to describe its own
    metrics. A column the model aliased differently just shows no matched
    definition, rather than guessing one.
    """
    if result["status"] == "ok":
        used_metrics = [METRIC_DEFINITIONS[col] for col in result["columns"] if col in METRIC_DEFINITIONS]
        if used_metrics:
            st.markdown("**Metric Definitions Used**")
            for m in used_metrics:
                st.markdown(f"- **{m['label']}** -- {m['description']}")

    st.markdown("**Filters**")
    date_label = f"{date_range[0]} to {date_range[1]}" if len(date_range) == 2 else str(date_range[0])
    st.markdown(
        f"- **Date:** {date_label}\n"
        f"- **Lender:** {lender_filter}\n"
        f"- **State:** {state_filter}\n"
        f"- **Vendor:** {vendor_filter}\n"
        f"- **Property Type:** {property_type_filter}"
    )

    if result["status"] != "rejected":
        st.markdown("**Generated SQL**")
        st.code(result["sql"], language="sql")

    render_observability(result["observability"])


def _escape_dollars(text: str) -> str:
    """Avoid a literal '$' in LLM-generated prose (e.g. "$513K") being parsed as a LaTeX math delimiter by st.markdown."""
    return text.replace("$", "\\$")


def render_key_insight(explanation: dict) -> None:
    """
    UX Step 6: headline + supporting detail, now sourced directly from the
    model's own structured output (agent.explain_results_with_meta) instead
    of the Step 1 regex split of a single prose string -- the model is
    asked to produce these as distinct fields on purpose.
    """
    headline = _escape_dollars(explanation.get("headline", ""))
    detail = _escape_dollars(explanation.get("detail", ""))

    st.markdown(
        f"""
        <div style="border-left:3px solid {ACCENT}; padding-left:16px; margin:4px 0 20px 0;">
          <div style="font-size:11px; font-weight:700; color:{ACCENT}; letter-spacing:0.06em; margin-bottom:6px;">
            KEY INSIGHT
          </div>
          <div style="font-size:19px; font-weight:700; color:{TEXT_PRIMARY}; margin-bottom:6px; line-height:1.35;">
            {headline}
          </div>
          <div style="font-size:15px; color:{TEXT_BODY}; line-height:1.5;">
            {detail}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_key_drivers(drivers: list) -> None:
    """
    UX Step 6: 0-3 short, associatively-worded contributing factors, shown
    only when agent.py's explanation step decided the question/data
    actually supports naming some (an empty list is the normal case for a
    plain ranking or single-KPI answer -- this renders nothing then).
    """
    if not drivers:
        return
    st.markdown(
        f'<div style="font-size:11px; font-weight:700; color:{TEXT_PRIMARY}; letter-spacing:0.06em; margin:20px 0 10px 0;">KEY DRIVERS</div>',
        unsafe_allow_html=True,
    )
    for i, driver in enumerate(drivers, 1):
        st.markdown(
            f'<div style="display:flex; gap:10px; margin-bottom:8px;">'
            f'<div style="font-weight:700; color:{ACCENT}; min-width:18px;">{i}.</div>'
            f'<div style="color:{TEXT_BODY}; line-height:1.5;">{_escape_dollars(driver)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )


def _apply_followup_question() -> None:
    picked = st.session_state.get("followup_pills")
    if picked:
        st.session_state["pending_followup"] = picked
        st.session_state["question_input"] = picked
        st.session_state["followup_pills"] = None


def render_follow_up_questions(follow_ups: list) -> None:
    """
    UX Step 6: 2-3 contextual next questions from the model's own
    structured output. Unlike the top example-question pills (which only
    fill the input for review), clicking one of these both fills the input
    AND sets "pending_followup" so the main control flow below submits it
    immediately -- matching the design spec's "clicking a follow-up should
    submit it as the next question."
    """
    if not follow_ups:
        return
    st.markdown(
        f'<div style="font-size:11px; font-weight:700; color:{TEXT_PRIMARY}; letter-spacing:0.06em; margin:20px 0 10px 0;">EXPLORE FURTHER</div>',
        unsafe_allow_html=True,
    )
    st.pills(
        "Follow-up questions",
        follow_ups,
        key="followup_pills",
        on_change=_apply_followup_question,
        label_visibility="collapsed",
    )


def render_rejected_message(raw_message: str) -> None:
    """
    UX Step 7: a declined question always comes back as agent.py's
    "NO_SQL: ..." sentinel -- strip that internal prefix before showing it
    to a user, and distinguish the two response styles the guardrail
    prompt is now asked to produce (agent.SYSTEM_PROMPT): a one-sentence
    "I don't have enough information..." statement when the question truly
    can't be answered from this data, versus a single clarifying question
    when it's just ambiguous. Detecting which one this is by checking for
    a trailing "?" is a cheap, reliable proxy for the model's own
    two-style prompt instruction -- no extra field or second call needed.
    """
    message = raw_message.removeprefix("NO_SQL:").strip()
    if message.endswith("?"):
        st.info(f"**To answer that, I need a bit more detail:** {message}")
    else:
        st.warning(message)


# --- Ask Doma AI (Phase 6-9: NL -> SQL -> validate -> execute -> explain) ---
st.divider()
with st.container(border=True, key="ask_doma_card"):
    st.markdown(
        f"""
        <div style="display:flex; align-items:center; gap:10px;">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="{ACCENT}" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C12.5 7 14.5 9.5 20 10C14.5 10.5 12.5 13 12 18C11.5 13 9.5 10.5 4 10C9.5 9.5 11.5 7 12 2Z"/>
          </svg>
          <span style="font-size:28px; font-weight:700; color:{TEXT_PRIMARY};">Ask Doma AI</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Get insights from your title operations data. Ask a question in plain English.")
    st.caption(
        "AI-generated insights may contain errors. "
        "Verify important business decisions against governed reporting."
    )

    with st.container(key="ask_input_row"):
        input_col, send_col = st.columns([20, 1.4], vertical_alignment="center")
        with input_col:
            question = st.text_input(
                "Ask about title operations",
                placeholder="Ask a question about your data...",
                label_visibility="collapsed",
                key="question_input",
            )
        with send_col:
            send_clicked = st.button("", icon=":material/send:", key="ask_send_btn", type="primary")

    st.pills(
        "Example questions",
        EXAMPLE_QUESTIONS,
        key="example_pills",
        on_change=_apply_example_question,
        label_visibility="collapsed",
    )

    # A follow-up pill click (see _apply_followup_question) sets
    # "pending_followup" and reruns the script; a fresh send-button click
    # takes priority if both somehow fired the same rerun. Either way,
    # popping it means a follow-up only ever fires once, not on every
    # subsequent rerun of the page (e.g. touching an unrelated filter).
    if send_clicked and question:
        question_to_run = question
    else:
        question_to_run = st.session_state.pop("pending_followup", None)

    if question_to_run:
        with st.spinner("Analyzing your title operations data..."):
            result = ask(question_to_run)

        if result["status"] == "ok":
            render_key_insight(result["explanation"])

            # Sort once, here, and feed the same rows to both the chart and
            # the table so they always agree with each other. The chart
            # keeps real datetime/float values (for a proper date axis and
            # unrounded hover precision); the table gets display formatting.
            display_rows = charts.sort_for_display(result["columns"], result["rows"])

            answer_chart = charts.auto_chart(result["columns"], display_rows)
            if answer_chart is not None:
                st.plotly_chart(answer_chart, width="stretch")

            render_key_drivers(result["explanation"].get("drivers", []))
            render_follow_up_questions(result["explanation"].get("follow_up_questions", []))

            with st.expander("How this answer was calculated"):
                render_how_calculated(result)

            render_supporting_table(result["columns"], display_rows)
        elif result["status"] == "rejected":
            render_rejected_message(result["message"])
            with st.expander("How this answer was calculated"):
                render_how_calculated(result)
        else:
            st.error(result["message"])
            with st.expander("How this answer was calculated"):
                render_how_calculated(result)

con.close()
