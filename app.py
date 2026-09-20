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

KPI_FIELDS = [
    "total_orders",
    "sla_compliance_pct",
    "avg_turnaround_hours",
    "automation_rate_pct",
    "exception_rate_pct",
    "estimated_borrower_savings",
]

# label, icon, icon background, icon color, value formatter, higher-is-better
# (for trend color: e.g. a turnaround-time *increase* is bad, so it renders red)
KPI_DISPLAY = [
    ("total_orders", "Total Orders", "\U0001F4C4", "#EFF6FF", "#2563EB", lambda v: f"{v:,}", True),
    ("sla_compliance_pct", "SLA Compliance", "✅", "#ECFDF5", "#059669", lambda v: f"{v:.1f}%", True),
    ("avg_turnaround_hours", "Avg Turnaround Time", "\U0001F550", "#F5F3FF", "#7C3AED", lambda v: f"{v:.1f} hrs", False),
    ("automation_rate_pct", "Automation Rate", "⚙️", "#EFF6FF", "#2563EB", lambda v: f"{v:.1f}%", True),
    ("exception_rate_pct", "Exception Rate", "⚠️", "#FEF2F2", "#DC2626", lambda v: f"{v:.1f}%", False),
    ("estimated_borrower_savings", "Est. Borrower Savings", "\U0001F4B0", "#FFFBEB", "#D97706", lambda v: f"${v / 1_000_000:.1f}M", True),
]

EXAMPLE_QUESTIONS = [
    "What are the top 5 vendors by order volume?",
    "Why did exception rate increase this month?",
    "Show SLA compliance by state.",
    "Which orders are at risk of missing SLA?",
    "What is the average turnaround time by lender?",
]


def render_kpi_card(icon: str, icon_bg: str, icon_color: str, label: str, value: str, delta_pct, higher_is_better: bool) -> None:
    """One KPI card: icon badge, label, big value, and a colored vs.-prior-week trend line."""
    if delta_pct is None:
        trend_html = '<div style="font-size:12px;color:#9CA3AF;">No prior-week data</div>'
    else:
        if delta_pct > 0:
            arrow, favorable = "▲", higher_is_better
        elif delta_pct < 0:
            arrow, favorable = "▼", not higher_is_better
        else:
            arrow, favorable = "–", None
        color = "#9CA3AF" if favorable is None else ("#059669" if favorable else "#DC2626")
        trend_html = (
            f'<div style="font-size:14px;color:{color};font-weight:600;">'
            f'{arrow} {abs(delta_pct):.1f}% <span style="color:#9CA3AF;font-weight:400;">vs. prior week</span></div>'
        )

    st.markdown(
        f"""
        <div style="background:#FFFFFF;border:1px solid #E5E7EB;border-radius:12px;padding:18px 20px;">
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
            <div style="width:40px;height:40px;min-width:40px;border-radius:50%;background:{icon_bg};
                        display:flex;align-items:center;justify-content:center;font-size:18px;">{icon}</div>
            <div style="font-size:14px;color:#4B5563;font-weight:600;">{label}</div>
          </div>
          <div style="font-size:30px;font-weight:700;color:#111827;margin-bottom:8px;">{value}</div>
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
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background-color: #EFF6FF;
    }
    .st-key-header_card, .st-key-chart_card_1, .st-key-chart_card_2, .st-key-chart_card_3, .st-key-ask_doma_card {
        background-color: #FFFFFF !important;
        box-shadow: 0 2px 8px rgba(15, 23, 42, 0.10);
        border-radius: 14px !important;
    }
    .st-key-header_card [data-testid="stSelectbox"] [role="group"],
    .st-key-header_card [data-testid="stDateInputField"] {
        background-color: #FFFFFF !important;
    }
    .st-key-ask_doma_card [data-testid="stCaptionContainer"] p {
        font-size: 15px !important;
    }
    .st-key-ask_doma_card input {
        font-size: 17px !important;
    }
    /* "How this was generated" expander: match the question input's look --
       same light-gray fill and font size, so it reads as part of the same
       section instead of a visually distinct default Streamlit expander. */
    .st-key-ask_doma_card [data-testid="stExpander"] {
        background-color: #F0F2F6 !important;
        border-radius: 10px !important;
    }
    .st-key-ask_doma_card [data-testid="stExpander"] summary {
        background-color: #F0F2F6 !important;
        font-size: 17px !important;
        border-radius: 10px !important;
    }
    .st-key-ask_doma_card [data-testid="stExpander"] p {
        font-size: 17px !important;
    }
    button[data-variant="pills"] {
        background-color: #EFF6FF !important;
        border-color: #BFDBFE !important;
    }
    button[data-variant="pills"] span {
        color: #2563EB !important;
        font-weight: 600 !important;
    }
    .st-key-ask_send_btn button {
        border-radius: 50% !important;
        width: 44px !important;
        height: 44px !important;
        min-width: 44px !important;
        padding: 0 !important;
        background-color: #2563EB !important;
        border-color: #2563EB !important;
    }
    .st-key-ask_send_btn button span {
        color: #FFFFFF !important;
    }
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
        <div style="display:flex; align-items:center; gap:24px; padding:4px 0 16px 0;">
          <img src="data:image/png;base64,{LOGO_B64}" style="height:56px; width:auto;" alt="doma" />
          <div>
            <div style="font-size:34px; font-weight:700; color:#111827; line-height:1.2;">Title Operations Insights</div>
            <div style="font-size:15px; color:#6B7280;">Ask questions. Get real answers. Powered by your data.</div>
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
for col, (field, label, icon, icon_bg, icon_color, fmt, higher_is_better) in zip(kpi_cols, KPI_DISPLAY):
    current_val, prior_val = current_week_kpis[field], prior_week_kpis[field]
    delta_pct = (
        (current_val - prior_val) / prior_val * 100
        if current_val is not None and prior_val
        else None
    )
    with col:
        render_kpi_card(icon, icon_bg, icon_color, label, fmt(kpi_values[field]), delta_pct, higher_is_better)

def render_chart_title(text: str) -> None:
    """Chart-card title, sized to match the Ask Doma AI header (24px/700)."""
    st.markdown(
        f'<div style="font-size:24px; font-weight:700; color:#111827; margin-bottom:8px;">{text}</div>',
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
        <div style="border-left:3px solid #2563EB; padding-left:16px; margin:4px 0 20px 0;">
          <div style="font-size:11px; font-weight:700; color:#2563EB; letter-spacing:0.06em; margin-bottom:6px;">
            KEY INSIGHT
          </div>
          <div style="font-size:19px; font-weight:700; color:#111827; margin-bottom:6px; line-height:1.35;">
            {headline}
          </div>
          <div style="font-size:15px; color:#4B5563; line-height:1.5;">
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
        '<div style="font-size:11px; font-weight:700; color:#111827; letter-spacing:0.06em; margin:20px 0 10px 0;">KEY DRIVERS</div>',
        unsafe_allow_html=True,
    )
    for i, driver in enumerate(drivers, 1):
        st.markdown(
            f'<div style="display:flex; gap:10px; margin-bottom:8px;">'
            f'<div style="font-weight:700; color:#2563EB; min-width:18px;">{i}.</div>'
            f'<div style="color:#374151; line-height:1.5;">{_escape_dollars(driver)}</div>'
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
        '<div style="font-size:11px; font-weight:700; color:#111827; letter-spacing:0.06em; margin:20px 0 10px 0;">EXPLORE FURTHER</div>',
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
        """
        <div style="display:flex; align-items:center; gap:10px;">
          <svg width="30" height="30" viewBox="0 0 24 24" fill="#2563EB" xmlns="http://www.w3.org/2000/svg">
            <path d="M12 2C12.5 7 14.5 9.5 20 10C14.5 10.5 12.5 13 12 18C11.5 13 9.5 10.5 4 10C9.5 9.5 11.5 7 12 2Z"/>
          </svg>
          <span style="font-size:24px; font-weight:700; color:#111827;">Ask Doma AI</span>
          <span style="background:#EFF6FF; color:#2563EB; font-size:11px; font-weight:700;
                       padding:2px 10px; border-radius:999px;">BETA</span>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption("Get insights from your title operations data. Ask a question in plain English.")
    st.caption(
        "AI-generated insights may contain errors. "
        "Verify important business decisions against governed reporting."
    )

    input_col, send_col = st.columns([20, 1.3], vertical_alignment="bottom")
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
