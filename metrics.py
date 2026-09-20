"""
Governed metric definitions for the Doma title operations dataset.

These formulas are transcribed directly from the dataset's own
`kpi_guide` sheet (see scripts/inspect_dataset.py output) -- not
reinterpreted. Both the dashboard (app.py / charts.py) and the AI
agent (agent.py, from Phase 5 on) build their SQL from these same
definitions, so the two can never silently disagree on what a
metric means.
"""

METRIC_DEFINITIONS = {
    "total_orders": {
        "label": "Total Orders",
        "sql_expression": "COUNT(order_id)",
        "description": "Count of title orders.",
    },
    "sla_compliance_pct": {
        "label": "SLA Compliance %",
        "sql_expression": "100.0 * AVG(CASE WHEN turnaround_hours <= sla_hours THEN 1 ELSE 0 END)",
        "description": "Percentage of orders completed within their SLA threshold "
                        "(turnaround_hours <= sla_hours). SLA Met is derived, never stored.",
    },
    "avg_turnaround_hours": {
        "label": "Avg Turnaround Time (hrs)",
        "sql_expression": "AVG(turnaround_hours)",
        "description": "Average elapsed processing time across ALL orders "
                        "(not filtered by status -- validated in Phase 2 against the Looker dashboard).",
    },
    "automation_rate_pct": {
        "label": "Automation Rate %",
        "sql_expression": "100.0 * AVG(CASE WHEN automated_flag = 'Yes' THEN 1 ELSE 0 END)",
        "description": "Percentage of orders processed through an automated decision path "
                        "(Instant Clear or Automated Review).",
    },
    "exception_rate_pct": {
        "label": "Exception Rate %",
        "sql_expression": "100.0 * AVG(CASE WHEN exception_flag = 'Yes' THEN 1 ELSE 0 END)",
        "description": "Percentage of orders flagged with an operational exception.",
    },
    "escalation_rate_pct": {
        "label": "Escalation Rate %",
        "sql_expression": "100.0 * AVG(CASE WHEN escalated_flag = 'Yes' THEN 1 ELSE 0 END)",
        "description": "Percentage of orders escalated for manual attention.",
    },
    "estimated_borrower_savings": {
        "label": "Estimated Borrower Savings ($)",
        "sql_expression": "SUM(estimated_borrower_savings)",
        "description": "Total illustrative borrower savings across eligible automated/accepted orders.",
    },
    "ta_eligible_rate_pct": {
        "label": "Title Acceptance Eligible Rate %",
        "sql_expression": "100.0 * AVG(CASE WHEN title_acceptance_eligible = 'Yes' THEN 1 ELSE 0 END)",
        "description": "Percentage of orders meeting title acceptance eligibility criteria "
                        "(synthetic demo indicator, not a real Fannie Mae determination).",
    },
}


DEFAULT_KPI_FIELDS = [
    "total_orders",
    "sla_compliance_pct",
    "avg_turnaround_hours",
    "automation_rate_pct",
    "exception_rate_pct",
]


def kpi_summary_sql(where_sql: str, fields: list = None) -> str:
    """SQL for the KPI card row, built entirely from governed definitions."""
    fields = fields or DEFAULT_KPI_FIELDS
    select_clause = ",\n        ".join(
        f"{METRIC_DEFINITIONS[f]['sql_expression']} AS {f}" for f in fields
    )
    return f"""
        SELECT
        {select_clause}
        FROM title_orders
        WHERE {where_sql}
    """


def order_volume_sla_sql(where_sql: str) -> str:
    """SQL for the 'Order Volume & SLA Compliance' chart."""
    return f"""
        SELECT
            strftime(order_date, '%Y-%m') AS month,
            {METRIC_DEFINITIONS['total_orders']['sql_expression']} AS order_volume,
            {METRIC_DEFINITIONS['sla_compliance_pct']['sql_expression']} AS sla_pct
        FROM title_orders
        WHERE {where_sql}
        GROUP BY month
        ORDER BY month
    """


def tat_by_decision_sql(where_sql: str) -> str:
    """SQL for the 'Turnaround Time by Decision Type' chart."""
    return f"""
        SELECT decision_type, {METRIC_DEFINITIONS['avg_turnaround_hours']['sql_expression']} AS avg_tat
        FROM title_orders
        WHERE {where_sql}
        GROUP BY decision_type
        ORDER BY avg_tat
    """


def ta_eligibility_by_state_sql(where_sql: str) -> str:
    """SQL for the 'Title Acceptance Eligibility by State' table."""
    return f"""
        SELECT
            state,
            {METRIC_DEFINITIONS['total_orders']['sql_expression']} AS total_orders,
            {METRIC_DEFINITIONS['ta_eligible_rate_pct']['sql_expression']} AS ta_eligible_pct
        FROM title_orders
        WHERE {where_sql}
        GROUP BY state
        ORDER BY ta_eligible_pct DESC
    """


def metric_definitions_prompt_text() -> str:
    """Render governed metric definitions as text for the AI agent's system prompt (Phase 5+)."""
    lines = [
        f"- {meta['label']} ({key}): {meta['sql_expression']} -- {meta['description']}"
        for key, meta in METRIC_DEFINITIONS.items()
    ]
    return "\n".join(lines)
