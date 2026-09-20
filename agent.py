"""
NL -> SQL -> validate -> execute -> explain pipeline for the Doma AI agent.
"""

import json
import os
import time

import duckdb
from anthropic import Anthropic
from dotenv import load_dotenv

from charts import format_row_for_display
from database import get_connection
from metrics import metric_definitions_prompt_text
from sql_guard import is_safe_select

load_dotenv()

MODEL = "claude-sonnet-5"

# Anthropic first-party API rates, $ per 1M tokens.
PRICING_PER_MTOK = {"claude-sonnet-5": {"input": 2.00, "output": 10.00}}

SCHEMA_TEXT = """
Table: title_orders (one row per title order)
- order_id VARCHAR
- order_date TIMESTAMP
- close_date TIMESTAMP
- state VARCHAR
- lender VARCHAR
- vendor_id VARCHAR
- vendor_name VARCHAR
- loan_type VARCHAR
- property_type VARCHAR
- loan_amount BIGINT
- property_value BIGINT
- ltv DOUBLE
- title_acceptance_eligible VARCHAR ('Yes'/'No')
- decision_type VARCHAR (e.g. Instant Clear, Automated Review, Manual Review)
- automated_flag VARCHAR ('Yes'/'No')
- exception_flag VARCHAR ('Yes'/'No')
- exception_type VARCHAR (populated only when exception_flag = 'Yes')
- turnaround_hours DOUBLE
- sla_hours BIGINT
- hands_on_minutes BIGINT
- escalated_flag VARCHAR ('Yes'/'No')
- estimated_title_cost BIGINT
- estimated_borrower_savings BIGINT
- status VARCHAR (e.g. Completed, Open)

Table: vendors (one row per vendor)
- vendor_id VARCHAR
- vendor_name VARCHAR
- region VARCHAR
- performance_profile VARCHAR
"""

SYSTEM_PROMPT = f"""You are a SQL analyst for Doma's title operations data, running on DuckDB.

DATABASE SCHEMA:
{SCHEMA_TEXT}

GOVERNED METRIC DEFINITIONS -- use these exact formulas whenever a question asks
for one of these metrics. Never invent an alternative formula for a metric that
is defined here:
{metric_definitions_prompt_text()}

RULES:
- Generate exactly one read-only DuckDB SQL SELECT statement.
- Never use INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or TRUNCATE.
- Only reference the tables/columns listed above.
- If you cannot write that SQL, do not guess -- respond with a single line
  starting with "NO_SQL:" instead, using exactly ONE of these two styles
  depending on WHY you can't answer (never combine them, never pad either
  with a long explanation -- one sentence each):

  1. INSUFFICIENT DATA -- the question asks for something this schema
     genuinely cannot support: a causal "why" question, a field that isn't
     tracked here, anything needing context outside title_orders/vendors.
     Respond with a short, plain, declarative statement, e.g.:
     "NO_SQL: I don't have enough information in the available title
     operations data to answer that question."

  2. AMBIGUOUS -- the question could be answered, but is worded in a way
     that maps to more than one reasonable interpretation (a vague term
     like "performance" or "at risk" with no defined threshold). Respond
     with exactly ONE concise clarifying question that names the specific
     options, e.g.:
     "NO_SQL: When you say performance, would you like me to compare SLA
     compliance, turnaround time, or exception rate?"

- Return ONLY the SQL statement (or the NO_SQL line) -- no explanation, no
  markdown code fences.
"""


def _call_claude(system_prompt: str, user_content: str, max_tokens: int) -> tuple[str, dict]:
    """
    Shared Claude call for Phase 11 observability: every call site needs the
    same model/token/latency bookkeeping, so it lives here once instead of
    being duplicated in generate_sql and explain_results.
    """
    client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    start = time.perf_counter()
    response = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    latency_seconds = time.perf_counter() - start

    # Some responses include a ThinkingBlock ahead of the text block -- skip
    # to the first actual text block rather than assuming content[0].
    text = next(block.text for block in response.content if block.type == "text").strip()

    meta = {
        "model": response.model,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_seconds": latency_seconds,
    }
    return text, meta


def _strip_code_fence(text: str) -> str:
    """The model sometimes wraps SQL in a markdown code fence despite being told not to."""
    if not text.startswith("```"):
        return text
    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()
    if text.lower().startswith("sql\n"):
        text = text[4:].strip()
    return text


def generate_sql_with_meta(question: str) -> tuple[str, dict]:
    """Like generate_sql, but also returns model/token/latency metadata for observability."""
    text, meta = _call_claude(SYSTEM_PROMPT, question, max_tokens=500)
    return _strip_code_fence(text), meta


def generate_sql(question: str) -> str:
    """Ask Claude to translate a natural-language question into a single read-only SQL query."""
    text, _ = generate_sql_with_meta(question)
    return text


EXPLAIN_SYSTEM_PROMPT = """You are an AI analyst explaining title-operations query
results to an operations/leadership audience -- the goal is to read like an
analyst showing their work, not a chatbot dumping SQL output.

You will be given the original question, the SQL that was run, and the exact
rows it returned. Respond with ONLY a single JSON object (no markdown code
fences, no text before or after it) with exactly these keys:

{
  "headline": "<one sentence stating the key finding, plain English>",
  "detail": "<1-3 sentences of supporting explanation, citing specific numbers from the rows>",
  "drivers": ["<short driver 1>", "<short driver 2>", "..."],
  "follow_up_questions": ["<question 1>", "<question 2>", "..."]
}

RULES:
- Base "headline" and "detail" ONLY on the rows given to you. Never invent
  numbers, rows, or trends that aren't present in the data provided.
- If no rows were returned, say so plainly in "headline" -- don't guess at a reason.
- "drivers": 0 to 3 short strings. Only populate this when the question is
  asking to understand contributing factors behind a pattern (a breakdown,
  a comparison, a concentration of outcomes in a few categories) AND the
  returned rows actually support identifying those factors. Return an empty
  list when it doesn't apply -- never fabricate a driver just to fill the
  list. When you do include one, use associative language ("associated
  with", "contributed to", "coincided with", "appears concentrated in")
  -- the data is an aggregation, not a controlled experiment, so never
  claim causation it can't support.
- "follow_up_questions": exactly 2-3 short, natural next questions a
  business user might ask given THIS specific question and result -- not
  generic questions. Reference actual entities visible in the rows (vendor
  names, states, exception types, lenders, etc.) where relevant. Each must
  be answerable as a single SQL query against the title_orders/vendors
  schema (no follow-up that itself asks "why").
- Do not repeat the raw SQL back -- it's already shown separately.
"""


def _parse_explanation(raw_text: str) -> dict:
    """
    Parse the explanation JSON, tolerating a markdown code fence (the model
    sometimes adds one despite being told not to -- same issue as SQL
    generation) and degrading gracefully instead of raising if the model
    ever returns something that isn't valid JSON: the raw text becomes the
    "detail" so the user still gets an answer, just without headline/
    drivers/follow-ups for that one response.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        if text.lower().startswith("json\n"):
            text = text[5:].strip()

    fallback = {"headline": "Here's what I found:", "detail": text, "drivers": [], "follow_up_questions": []}
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return fallback
    if not isinstance(parsed, dict):
        return fallback

    return {
        "headline": str(parsed.get("headline", "")).strip(),
        "detail": str(parsed.get("detail", "")).strip(),
        "drivers": [str(d).strip() for d in parsed.get("drivers", []) if str(d).strip()][:3],
        "follow_up_questions": [str(q).strip() for q in parsed.get("follow_up_questions", []) if str(q).strip()][:3],
    }


def explain_results_with_meta(question: str, sql: str, columns: list, rows: list) -> tuple[dict, dict]:
    """
    Ask Claude to explain query results as structured data -- headline,
    supporting detail, optional key drivers, optional follow-up questions
    -- rather than a single prose paragraph. Also returns model/token/
    latency metadata for observability, like the other *_with_meta calls.
    """
    if rows:
        preview = [format_row_for_display(row) for row in rows[:20]]
        data_lines = [", ".join(columns)] + [", ".join(str(v) for v in row) for row in preview]
        data_block = "\n".join(data_lines)
        if len(rows) > len(preview):
            data_block += f"\n(showing first {len(preview)} of {len(rows)} rows)"
    else:
        data_block = "(no rows returned)"

    user_content = (
        f"Question: {question}\n\n"
        f"SQL executed:\n{sql}\n\n"
        f"Result rows:\n{data_block}"
    )
    raw_text, meta = _call_claude(EXPLAIN_SYSTEM_PROMPT, user_content, max_tokens=600)
    return _parse_explanation(raw_text), meta


def explain_results(question: str, sql: str, columns: list, rows: list) -> str:
    """Ask Claude to turn raw query results into a short plain-English answer (headline + detail only)."""
    explanation, _ = explain_results_with_meta(question, sql, columns, rows)
    return f"{explanation['headline']} {explanation['detail']}".strip()


def _estimate_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """Anthropic first-party API rates -- see PRICING_PER_MTOK. Falls back to 0.0 for an unknown model."""
    rates = PRICING_PER_MTOK.get(model, {"input": 0.0, "output": 0.0})
    return (input_tokens / 1_000_000) * rates["input"] + (output_tokens / 1_000_000) * rates["output"]


def ask(question: str) -> dict:
    """
    Full generate -> validate -> execute -> explain pipeline.

    Always returns a result dict rather than raising, since unsafe SQL,
    ambiguous questions, and query execution errors are all expected
    outcomes here, not exceptional ones -- app.py renders each `status`
    differently but never needs a try/except around this call.

    Every result includes an "observability" dict (Phase 11): model, token
    usage, and latency for each Claude call that actually ran, plus
    query execution time/rows once the SQL has run, and a running total.

    Return shape:
        {"status": "rejected", "question", "sql", "message", "observability"}  -- unsafe/NO_SQL
        {"status": "error", "question", "sql", "message", "observability"}     -- ran, DB error
        {"status": "ok", "question", "sql", "columns", "rows",
         "explanation", "observability"}                                      -- success
    """
    pipeline_start = time.perf_counter()
    raw_sql, gen_meta = generate_sql_with_meta(question)

    observability = {
        "model": gen_meta["model"],
        "sql_generation": gen_meta,
        "total_input_tokens": gen_meta["input_tokens"],
        "total_output_tokens": gen_meta["output_tokens"],
    }

    safe, detail = is_safe_select(raw_sql)
    if not safe:
        observability["total_latency_seconds"] = time.perf_counter() - pipeline_start
        observability["total_cost_usd"] = _estimate_cost_usd(
            observability["model"], observability["total_input_tokens"], observability["total_output_tokens"]
        )
        return {
            "status": "rejected",
            "question": question,
            "sql": raw_sql,
            "message": detail,
            "observability": observability,
        }

    clean_sql = detail
    con = get_connection(read_only=True)
    exec_start = time.perf_counter()
    try:
        cursor = con.execute(clean_sql)
        columns = [d[0] for d in cursor.description]
        rows = cursor.fetchall()
        # Round to 2 decimal places once, here, so the explanation text, the
        # displayed table, and chart labels all cite the exact same numbers
        # instead of the explanation citing a long raw float.
        rows = [tuple(round(v, 2) if isinstance(v, float) else v for v in row) for row in rows]
    except duckdb.Error as exc:
        observability["sql_execution"] = {"latency_seconds": time.perf_counter() - exec_start}
        observability["total_latency_seconds"] = time.perf_counter() - pipeline_start
        observability["total_cost_usd"] = _estimate_cost_usd(
            observability["model"], observability["total_input_tokens"], observability["total_output_tokens"]
        )
        return {
            "status": "error",
            "question": question,
            "sql": clean_sql,
            "message": f"Query execution failed: {exc}",
            "observability": observability,
        }
    finally:
        con.close()

    observability["sql_execution"] = {
        "latency_seconds": time.perf_counter() - exec_start,
        "rows_returned": len(rows),
    }

    explanation, exp_meta = explain_results_with_meta(question, clean_sql, columns, rows)
    observability["explanation"] = exp_meta
    observability["total_input_tokens"] += exp_meta["input_tokens"]
    observability["total_output_tokens"] += exp_meta["output_tokens"]
    observability["total_latency_seconds"] = time.perf_counter() - pipeline_start
    observability["total_cost_usd"] = _estimate_cost_usd(
        observability["model"], observability["total_input_tokens"], observability["total_output_tokens"]
    )

    return {
        "status": "ok",
        "question": question,
        "sql": clean_sql,
        "columns": columns,
        "rows": rows,
        "explanation": explanation,
        "observability": observability,
    }
