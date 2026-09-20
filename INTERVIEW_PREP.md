# Doma Conversational Data Insights Agent — Interview Prep Doc

**Status:** Living document, updated as we build. Last updated: Phase 12 complete (all 12 build phases done), 2026-09-19.

This file is your single source of truth for the technical interview with **Jay Ozer** (Doma Technology). It captures the *why* behind every decision, not just the *what*, so you can defend any part of this POC live.

---

## 1. Why this project exists

**Interview context:**
- Role: Senior Data Analyst, Doma Technology LLC
- Completed: Recruiter screen ✅, Hiring Manager interview with Steven Flathers (Director, Technology Operations) ✅
- Next: 45-minute technical interview with **Jay Ozer** — a data/analytics/applied-AI leader at Doma with a background spanning Staff Data Analyst → Manager, Data Engineering → Applied AI. He has hands-on experience with Snowflake, Looker/LookML, Snowflake Cortex, and LLM-based analytics.
- Recruiter's framing of the interview: *"Largely focused on your ability to take direction/ideation and put something into production... he will want to hear about examples and potentially walk through an example live together."*

**What that means for prep:** this isn't a coding test. It's a test of whether you can narrate a full product-thinking arc:

```
IDEA → BUSINESS PROBLEM → DATA → DESIGN → MVP → VALIDATION → PRODUCTION CONSIDERATIONS → MONITORING → ITERATION
```

Section 10 maps this project explicitly onto that arc so you can walk through it live if asked.

**Your role in this build:** analytics lead, not backend engineer. You're defining the business questions, validating metric correctness against the source data and the existing Looker dashboard, shaping the AI experience, and directing a technical build (via Claude Code) — the same role split you had on **Sage/Clearview** at Panasonic. Say this explicitly if asked "did you build this yourself?" — the honest answer is: yes, AI-assisted, and you understand and can defend every line because you drove the design decisions and validated the output.

---

## 2. About Doma (for framing, not to recite verbatim)

Doma modernizes real-estate title and closing. This POC is scoped to **title operations analytics**: title orders, lenders, vendors, turnaround time (TAT), SLA compliance, title acceptance eligibility, automated vs. manual processing, exceptions, borrower savings, and state-level performance.

The Senior Data Analyst role's stated responsibilities that this POC is designed to speak to:
- Owning/evolving Looker for Operations, SLA/exception/escalation reporting
- Connecting Snowflake and other sources to Looker; data quality and provenance
- Partnering across Operations, Finance, Product, Data Science, leadership
- Helping develop an **AI/agentic reporting layer** for ad-hoc business questions over governed data

Core architectural concept this project demonstrates:

```
Data warehouse → Governed data / semantic definitions → BI / Looker → Operational dashboards
                                    ↓
                     AI conversational analytics layer → Natural-language business questions
```

The load-bearing idea: **the AI layer and the BI layer must share the same governed metric definitions.** If they don't, you get "AI answer ≠ BI dashboard" — a real production risk, and one you can speak to directly from Panasonic experience.

---

## 3. The idea (one paragraph, for when Jay asks "walk me through it")

*"I built a small proof-of-concept called the Doma Conversational Data Insights Agent. It's a Streamlit app over a synthetic title-operations dataset — same dataset I used for my Looker Studio dashboard in the last round — that has two things bolted together: the operational KPI dashboard you'd expect (total orders, SLA compliance, TAT, automation rate, exception rate, two charts), and below it, a natural-language interface where you can ask things like 'which vendors have the highest average turnaround time?' and get back an answer, a data table, and — if useful — a chart. The AI doesn't invent metric definitions; it's constrained to a small governed metrics layer transcribed directly from the same KPI logic the dashboard uses, and the generated SQL is read-only and validated before it ever touches the database. There's also a 'how this was generated' panel showing the SQL, execution time, and token usage — that's the AI observability piece, inspired by work I did on a similar system, Sage/Clearview, at Panasonic."*

---

## 4. Source dataset (reused from the Looker Studio round — inspected in Phase 1)

**File:** `doma_title_operations.xlsx`, 5 sheets. This wasn't a blind dataset — it ships with its own governance:

| Sheet | Purpose |
|---|---|
| `title_orders` | Fact table. **5,000 rows × 24 columns.** Grain: one row = one title order. |
| `vendors` | 8-row lookup (vendor_id, vendor_name, region, performance_profile) |
| `data_dictionary` | Plain-English field definitions |
| `kpi_guide` | **Exact formula for every dashboard KPI** — this becomes the governed metrics layer (Section 7) |
| `README` | Dataset design notes and one important modeling instruction (see below) |

**Key fields:**
- IDs: `order_id` (e.g. `DO-10001`), `vendor_id` → joins to `vendors`
- Dates: `order_date`, `close_date` (blank for 135 still-open orders)
- Dimensions: `state` (10), `lender` (5), `vendor_name` (8), `loan_type` (2), `property_type` (4), `decision_type` (Instant Clear / Automated Review / Manual Review), `exception_type` (6 + null), `status` (Completed / In Review / Escalated)
- Flags (string "Yes"/"No", not booleans): `title_acceptance_eligible`, `automated_flag`, `exception_flag`, `escalated_flag`
- Measures: `turnaround_hours`, `sla_hours`, `hands_on_minutes`, `loan_amount`, `property_value`, `ltv`, `estimated_title_cost`, `estimated_borrower_savings`

**Data quality finding, resolved in Phase 2:** `turnaround_hours` has zero nulls across all 5,000 rows, including the 135 still-open orders. Tested both interpretations in DuckDB: `AVG(turnaround_hours)` over **all rows** reproduces the dashboard's 18.9 hrs exactly; filtering to `status = 'Completed'` only gives 18.8 hrs — a divergence. **Conclusion: Avg TAT is computed over all rows, unfiltered by status.** Good live example: *"I don't assume a formula matches the dashboard — I tested both interpretations and let the data decide."*

**Existing dashboard KPIs (target values to reconcile against):**

| KPI | Value |
|---|---|
| Total Orders | 5,000 |
| SLA Compliance | 86.5% |
| Avg Turnaround Time | 18.9 hrs |
| Automation Rate | 63.1% |
| Exception Rate | 8.5% |
| Estimated Borrower Savings | ~$3.5M |

**Validated in Phase 2 (DuckDB reconciliation against these targets):** all 6 KPIs matched — Total Orders 5,000 exact, SLA Compliance 86.5% exact, Avg TAT 18.9 hrs exact (unfiltered by status — see data quality note above), Automation Rate 63.1% exact, Exception Rate 8.5% exact, Borrower Savings $3,486,650 (within rounding of "~$3.5M"). Full detail: `scripts/validate_kpis.py`.

---

## 5. Architecture

```
Streamlit (app.py)
    │
    ├── Dashboard path:  database.py → metrics.py → charts.py → st.plotly_chart
    │
    └── AI path:  user question
                    │
                    ▼
              Claude API (agent.py)
                    │  (prompt includes: schema + metrics.py definitions)
                    ▼
              Generated SQL
                    │
                    ▼
              sql_guard.py  → reject if not a safe read-only SELECT
                    │
                    ▼
              DuckDB (database.py) → query results
                    │
                    ▼
              Claude API → plain-English explanation of results
                    │
                    ▼
              Streamlit → insight + table + optional chart + "How this was generated" panel
```

**Why this shape:** both paths (dashboard and AI) read from the same `database.py` connection and the same `metrics.py` definitions. That shared dependency is the entire point — it's the concrete mechanism that prevents "AI answer ≠ BI dashboard" drift.

**Conceptual flow for a single AI question:**

```
USER QUESTION → LLM → UNDERSTAND QUESTION → USE SCHEMA + METRIC DEFINITIONS
→ GENERATE SQL → VALIDATE SQL → QUERY DATABASE → RETURN RESULTS
→ LLM EXPLAINS RESULTS → DISPLAY (ANSWER + DATA + OPTIONAL VISUALIZATION)
```

## 6. Project structure

```
doma-insights-agent/
    data/
        doma_title_operations.xlsx
    db/
        doma.duckdb
    app.py            — Streamlit UI (dashboard + AI section)
    database.py        — load Excel → DuckDB, connection helper
    metrics.py          — governed metric definitions, transcribed from kpi_guide
    charts.py            — Plotly chart builders
    agent.py               — NL → SQL → validate → execute → explain
    sql_guard.py              — read-only SQL safety check
    requirements.txt
    .env                          — Claude API key (gitignored)
    README.md
    INTERVIEW_PREP.md               — this file
```

Flat structure, one file per concern — deliberately avoids `src/` nesting or a config framework, so every file maps to one thing you can point at and explain live.

---

## 7. Governed metrics / mini semantic layer

The core production-risk story of this POC: **the LLM must not invent business definitions.** Instead, `metrics.py` transcribes — not reinterprets — the formulas already defined in the dataset's own `kpi_guide` sheet:

| Metric | Definition (from `kpi_guide`) |
|---|---|
| Total Orders | `COUNT(order_id)` |
| SLA Compliance % | `AVG(CASE WHEN turnaround_hours <= sla_hours THEN 1 ELSE 0 END)` |
| Avg TAT | `AVG(turnaround_hours)` |
| Automation Rate | `AVG(CASE WHEN automated_flag = 'Yes' THEN 1 ELSE 0 END)` |
| Exception Rate | `AVG(CASE WHEN exception_flag = 'Yes' THEN 1 ELSE 0 END)` |
| Escalation Rate | `AVG(CASE WHEN escalated_flag = 'Yes' THEN 1 ELSE 0 END)` |
| Estimated Borrower Savings | `SUM(estimated_borrower_savings)` |
| TA Eligible Rate | Eligible orders / Total orders |
| Vendor Performance | Group by vendor_name: Orders, SLA %, Avg TAT, Exception %, Escalation % |
| Exception Distribution | Group exception orders by exception_type: count, % of exceptions |

Important note from the dataset's own README: *"Derive SLA Met in the BI layer from `turnaround_hours <= sla_hours` rather than storing the KPI result in each row."* — i.e., SLA compliance is a **derived** metric, not a stored column. Good example of a governance principle: compute derived metrics centrally, don't let each consumer (dashboard, AI agent) reimplement the logic.

**The architectural claim to make to Jay:** both the Streamlit dashboard and the Claude-generated SQL are built against this same `metrics.py` — the AI agent's system prompt is given these definitions so it never has to guess what "SLA compliance" means.

---

## 8. AI / LLM design

- **Model:** Claude API — model selection TBD in Phase 5 (leaning toward a Sonnet-class model for both NL→SQL generation and result explanation, for reliability; Haiku-class as a cheaper alternative if latency/cost becomes a concern for the demo). *(Will finalize and record the exact model ID here once Phase 5 is built.)*
- **No LangChain, no agent framework** — the orchestration (prompt → generate SQL → validate → execute → explain) is written directly in `agent.py` so it can be fully explained line-by-line, not delegated to a framework's abstractions.
- **No vector DB / RAG** — not needed. The schema and metric definitions are small enough to pass directly in the prompt context every time.

### SQL safety (guardrail)
- Agent is **read-only**. Only `SELECT` is permitted.
- `sql_guard.py` rejects any generated SQL containing `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `CREATE`, `TRUNCATE`, or anything that isn't a single safe `SELECT` statement.
- Invalid or unsafe SQL is rejected before execution — never silently modified or run anyway.

### Response behavior guardrails
- If a question can't be answered from available data: say so, don't fabricate.
- If ambiguous: ask a clarifying question rather than guessing.
- If a metric has an established definition (Section 7): always use it, never let the LLM invent an alternative formula.
- Persistent UI disclaimer: *"AI-generated insights may contain errors. Verify important business decisions against governed reporting."*

### Observability (secondary UI, not front-and-center)
Expandable "How this answer was generated" panel per AI response, showing:
- User question, generated SQL, query execution time, rows returned
- Model used, prompt/completion/total tokens, overall response latency

This directly mirrors LLM observability work from Panasonic (PostHog/GA4-based AI observability on Sage/Clearview) — a concrete talking point for "have you thought about monitoring AI systems in production?"

---

## 9. Tech stack — what's in, what's deliberately out

| Layer | Choice | Why |
|---|---|---|
| Frontend | Streamlit | Fastest path to a working UI you can fully own and explain; no separate frontend build |
| App logic | Python | Matches Claude Code-assisted workflow; readable for a non-SWE to own |
| LLM | Claude API | Direct API calls, no framework indirection |
| Analytical DB | DuckDB | Local, zero-infra, SQL-native — stands in for "the warehouse" without needing real Snowflake access |
| Data manipulation | Pandas | Standard, already familiar from BI background |
| Visualization | Plotly | Interactive, works cleanly inside Streamlit |
| Dev environment | VS Code + Claude Code | Same AI-assisted workflow used at Panasonic |

**Explicitly excluded** (and why, if asked): LangChain (adds abstraction without adding capability at this scale), vector databases / RAG (schema is small enough to pass directly — no retrieval problem to solve), multi-agent frameworks (one clear NL→SQL→explain pipeline doesn't need multiple agents), Kubernetes/AWS/cloud infra (out of scope for a local POC; would be the first production conversation), complex microservices, auth/user management.

---

## 10. Mapping this project onto the recruiter's framing

*(This is your live-narration cheat sheet — use it if Jay asks you to walk through your process.)*

| Stage | What happened in this project |
|---|---|
| **Idea** | Recreate the Sage/Clearview conversational-analytics pattern from Panasonic, adapted to Doma's title-operations domain, as a way to demonstrate both BI craft and applied-AI judgment in one artifact. |
| **Business problem** | Operations/leadership need governed, ad-hoc answers to questions like "which vendors are slow?" without waiting on a new Looker report each time — but without an AI answer silently diverging from the trusted dashboard. |
| **Data** | Reused the same synthetic title-operations dataset from the Looker Studio round rather than building something new — inspected its grain, fields, and *its own embedded KPI logic* before writing any code. |
| **Design** | Kept the architecture intentionally small: Streamlit + DuckDB + direct Claude API calls, with one shared metrics layer feeding both the dashboard and the AI agent, plus explicit SQL-safety and guardrail layers. |
| **MVP** | Built incrementally, phase by phase (Section 11), validating each layer before adding the next. |
| **Validation** | Dashboard KPIs reconciled against the original Looker Studio numbers (5,000 orders, 86.5% SLA compliance, 18.9 hr avg TAT, etc.) before ever wiring up the AI layer — so the AI has a trustworthy baseline to inherit. |
| **Production considerations** | Read-only SQL guardrails, governed metric definitions, ambiguity/no-data handling, and a persistent "verify against governed reporting" disclaimer — the concrete things you'd need before this touches real users. |
| **Monitoring** | Per-query observability panel (SQL, latency, token usage, rows returned) — a lightweight version of the AI observability instrumentation built at Panasonic. |
| **Iteration** | POC scoped to 2 charts and ~10 test questions deliberately, so the next iteration (more charts, more question types, real Snowflake/Looker integration) has a validated foundation to build from rather than guessing. |

---

## 11. Build phases (progress tracker)

Update the checkbox as each phase completes.

- [x] **Phase 0 — Environment setup.** Installed Python 3.13.15 from python.org (no Homebrew needed — the installer ships a prebuilt binary). Certificates installed via `Install Certificates.command`. Project venv created at `venv/`.
- [x] **Phase 1 — Inspect dataset.** Confirmed with pandas (`scripts/inspect_dataset.py`): 5,000 rows × 24 cols, dtypes clean, nulls exactly where expected. All flag columns (`automated_flag`, `exception_flag`, etc.) are string "Yes"/"No", not booleans.
- [x] **Phase 2 — Load into DuckDB; validate dashboard KPIs match Looker Studio numbers.** `database.py` builds `db/doma.duckdb` from the Excel file (shared by dashboard + AI agent going forward). `scripts/validate_kpis.py` reconciles all 6 KPIs — see Section 4 for results.
- [x] **Phase 3 — Streamlit dashboard: KPI cards, 2 charts, basic filters.** `app.py` + `charts.py`. Verified live in a headless browser (Playwright, used only for this one-off verification — not a project dependency): all 5 KPIs match Phase 2 validated values, both charts render correctly, filters (Date Range/Lender/State) work via parameterized DuckDB queries, zero console errors. KPI/chart SQL is still inline in `app.py`/`charts.py` at this point — Phase 4 extracts it into `metrics.py`.
  - **Post-Phase-4 addition:** added a 6th KPI card (Est. Borrower Savings, formatted as $X.XM) and a "Title Acceptance Eligibility by State" table, to bring the Streamlit dashboard closer to parity with the original Looker Studio dashboard. Values verified against the Looker screenshot (CO 75.76%, IL 75.42%, WA 73.33%, AZ 73.02%, GA 72.33%, CA 71.61%, TX 71.39% — all exact matches). This used the `kpi_summary_sql(where_sql, fields)` and new `ta_eligibility_by_state_sql(where_sql)` builders in `metrics.py` — no bypassing the governed layer even for a quick addition.
- [x] **Phase 4 — `metrics.py` governed metric layer.** Extracted the inline SQL from `app.py`/`charts.py` into `METRIC_DEFINITIONS` (8 metrics: total orders, SLA compliance, avg TAT, automation rate, exception rate, escalation rate, borrower savings, TA eligible rate) plus SQL-builder functions. `app.py` and `charts.py` now both call into `metrics.py` instead of hardcoding formulas. Verified via screenshot that dashboard output is byte-identical to Phase 3 (5,000 / 86.5% / 18.9 hrs / 63.1% / 8.5%, same chart values) — this was a refactor, not a behavior change. Also added `metric_definitions_prompt_text()`, which renders these definitions as plain text — this is what gets fed into Claude's prompt starting Phase 5, the actual mechanism (not just the diagram) that keeps the AI agent from inventing its own metric formulas.
- [x] **Phase 5 — Connect Claude API.** `scripts/test_claude_connection.py` confirms the key works end to end (`ANTHROPIC_API_KEY` in `.env`, gitignored). Model: `claude-sonnet-5` — used for both NL→SQL generation and (from Phase 9) result explanation, prioritizing reliability over the cheaper Haiku-class option for this demo.
- [x] **Phase 6 — Natural language → SQL generation.** `agent.py` (`generate_sql()`) builds a system prompt from the DB schema plus `metric_definitions_prompt_text()` from `metrics.py`, so the LLM is handed the governed formulas rather than asked to infer them. Tested against all 7 Section 13 example questions (`scripts/test_nl_to_sql.py`): 5 produced correct SQL using the exact governed formulas (including a `vendors` join for vendor-level turnaround), and 2 correctly declined with a `NO_SQL:` reason instead of guessing — one causal question ("why did exception rate increase") that can't be answered by a single query, and one genuinely ambiguous question ("at risk of missing SLA") where it asked for a threshold definition instead of inventing one. Not yet wired into `app.py` — SQL is generated but not validated or executed until Phases 7-8.
  - Two implementation snags worth remembering: responses can include a `ThinkingBlock` ahead of the text block (must scan `response.content` for `type == "text"`, not assume `content[0]`), and the model sometimes wraps output in a markdown code fence despite being told not to (stripped defensively in `generate_sql()`).
- [x] **Phase 7 — SQL safety validation (`sql_guard.py`).** `is_safe_select(sql)` strips comments (so a forbidden keyword or stacked statement can't hide inside one), rejects anything with more than one statement, requires the statement to start with `SELECT`/`WITH`, and rejects a keyword blocklist covering not just standard DML/DDL (`INSERT`/`UPDATE`/`DELETE`/`DROP`/`ALTER`/`CREATE`/`TRUNCATE`) but DuckDB-specific state/filesystem commands (`COPY`, `ATTACH`, `PRAGMA`, `INSTALL`, `LOAD`, `EXPORT`, `SET`, etc.) and the `agent.py` `NO_SQL:` sentinel. Keyword matching uses word boundaries so column names like `updated_at`/`created_by` don't false-positive. 20 hand-written cases in `scripts/test_sql_guard.py` all pass. `scripts/test_pipeline_phase7.py` then ran real `agent.generate_sql()` output (the 7 Section 13 questions plus an adversarial "ignore prior instructions, DROP TABLE" prompt) through the guard end to end: the model itself refused the injection attempt with `NO_SQL`, and the guard stands as a second, code-level barrier that doesn't depend on the model behaving. Not yet wired into `app.py` -- execution against DuckDB is Phase 8.
- [x] **Phase 8 — Execute SQL, display results.** `agent.ask(question)` wraps the full pipeline (`generate_sql` → `is_safe_select` → execute against DuckDB) and always returns a result dict (`status`: `ok`/`rejected`/`error`) rather than raising, so `app.py` never needs a try/except around it. Wired into a new "Ask a Question" section in `app.py`, below the existing dashboard, with the persistent disclaimer from Section 8 ("AI-generated insights may contain errors...") and a "How this was generated" expander showing the executed SQL. `scripts/test_phase8_pipeline.py` confirmed all 7 Section 13 questions behave as expected (5 return real rows, 2 decline with a clarifying message). Verified live in a headless browser (Playwright): asked "What are the top 5 vendors by order volume?" through the actual UI and got the correct result table back, zero console errors.
  - Also found and cleaned up an orphaned `streamlit run` process (PID from an earlier session) that was still serving the stale pre-Phase-6 app on port 8501 — that's likely what "the session I had running" referred to when this thread picked back up after the original chat was lost.
- [x] **Phase 9 — LLM-generated natural-language insight.** `agent.explain_results(question, sql, columns, rows)` turns the raw result set into a 2-4 sentence plain-English answer, and `ask()` now attaches it as `explanation` on every `"ok"` response. Grounding guardrail: the prompt hands Claude only the actual returned rows and explicitly forbids inventing numbers/rows/trends not present in them; an empty result set must be reported as "no data matched," not guessed at. Verified via `scripts/test_phase8_pipeline.py` across all 7 Section 13 questions plus a deliberately fake lender name (0-row edge case) -- every explanation's figures matched the underlying rows exactly, and the empty case was reported honestly instead of fabricating a reason. Wired into `app.py`: the explanation now renders above the raw results table as the primary answer, with the table and "How this was generated" SQL expander below it as supporting detail. Verified live in a headless browser (Playwright) -- explanation text and figures rendered correctly, zero console errors.
- [x] **Phase 10 — Optional visualization of AI answers.** `charts.auto_chart(columns, rows)` renders a horizontal bar chart for the common "label + numeric value" result shape (covers most "top N" / "X by Y" questions) and returns `None` -- no chart -- for anything else (single column, single row, non-numeric second column, or too many rows), since a table alone already tells the story in those cases. Deliberately reuses the single-hue horizontal-bar style already established by `tat_by_decision_chart` (Phase 3) rather than introducing a new visual language. Verified live in a headless browser (Playwright): "top 5 vendors by order volume" rendered a correctly-ordered, correctly-labeled bar chart beneath the results table.
  - **Post-Phase-10 fix #1:** the LLM doesn't always include an `ORDER BY` in its generated SQL (e.g. "average turnaround time by lender" came back in arbitrary row order), so `charts.sort_for_display(columns, rows)` sorts once, at display time, and `app.py` feeds those same sorted rows to both the table and `auto_chart` -- guaranteeing they always agree with each other regardless of what SQL was generated.
  - **Post-Phase-10 fix #2:** a naive "always sort descending by value" rule breaks time-series questions (e.g. "avg turnaround time in August by week" would scramble weeks into value order instead of calendar order). `sort_for_display` now detects a date/timestamp label column (index 0, via `isinstance(v, datetime.date)`) and sorts chronologically ascending instead; only a non-time numeric value column gets the descending "top N" sort. `auto_chart` mirrors this: a time-like label column renders a line chart (`go.Scatter`, `lines+markers`) instead of a horizontal bar, and is allowed up to 200 points (vs. 25 for bar charts, since dense daily lines stay readable where 25+ horizontal bars wouldn't). 10 cases in `scripts/test_auto_chart.py` cover both the bar and line paths plus a chronological-order assertion; all pass. Verified live: "average turnaround time in the month of august for every week" renders a proper Jul 26 -> Aug 30 line chart with the end-of-month spike (23.7 hrs) reading as a trend, matching the chronologically-ordered table exactly.
- [x] **Phase 11 — Observability panel.** `agent._call_claude()` centralizes model/token/latency capture so both `generate_sql_with_meta()` and `explain_results_with_meta()` (new; `generate_sql`/`explain_results` now delegate to these and keep their original plain-string signatures so earlier test scripts didn't need to change) return `(text, meta)`. `ask()` assembles an `observability` dict on every response -- `ok`, `rejected`, and `error` alike -- with `model`, per-stage token/latency breakdown (`sql_generation`, `sql_execution` incl. rows returned, `explanation`), and running `total_input_tokens`/`total_output_tokens`/`total_latency_seconds`. `app.py`'s `render_observability()` shows this inside the existing "How this was generated" expander (now added to the `rejected` case too, which previously had none) as 4 metric cards (Model, Total Tokens, Rows Returned, Total Latency) plus a per-stage bullet breakdown; `rejected` responses correctly show "-" for Rows Returned since no query ran. `scripts/test_phase11_observability.py` covers the `ok`/`rejected` paths against the real API, and a monkeypatched run confirmed the `error` path's shape (execution latency captured even on a DB error, e.g. querying a nonexistent column). Verified live in a headless browser (Playwright) for both `ok` and `rejected` cases, zero console errors.
- [x] **Phase 12 — Test against ~10 representative business questions.** Ran the full pipeline end to end (`scripts/test_phase12_business_questions.py`) against the 7 Section 13 design-spec questions plus 3 added to exercise metrics/shapes the original 7 didn't touch (escalation rate, a monetary metric over time, a non-`METRIC_DEFINITIONS` groupby by `exception_type`). Result: **8/10 answered correctly with governed SQL, 2/10 correctly declined** (the two guardrail cases were expected to decline, per Section 13's own framing) -- 0 unexpected errors. Cross-check: the "borrower savings by month" breakdown summed to exactly $3,486,650, matching the Phase 2 validated dashboard total to the dollar -- concrete proof the AI path and the governed dashboard path agree, not just superficially but numerically. Total cost for the full 10-question run: ~21K tokens, ~43s combined latency (~2-5s per question).

  | # | Question | Status | Notes |
  |---|---|---|---|
  | 1 | What are the top 5 vendors by order volume? | ok | Pacific Title Services leads (792); chart + table match |
  | 2 | Why did exception rate increase this month? | rejected | Correctly identified as a causal question, not answerable by SQL |
  | 3 | Show SLA compliance by state. | ok | Uses the exact governed SLA formula; CO highest (88.8%), VA lowest (83.9%) |
  | 4 | Which orders are at risk of missing SLA? | rejected | Correctly identified "at risk" as undefined; asked a clarifying question instead of guessing a threshold |
  | 5 | What is the average turnaround time by lender? | ok | Summit Home Lending slowest (19.9 hrs), Harbor Mortgage fastest (18.3 hrs) |
  | 6 | Which vendors have the highest average turnaround time? | ok | Correctly joined `vendors`; Metro Title Partners is a clear outlier (24.8 hrs) |
  | 7 | Compare automated vs. manual review turnaround time. | ok | ~9x speed difference (4.8 hrs automated vs. 43.1 hrs manual) |
  | 8 | What is the escalation rate by vendor? | ok | Uses the exact governed escalation formula; range 2.3%-4.9% across vendors |
  | 9 | What is the estimated borrower savings by month? | ok | Line chart, chronological Mar-Aug 2026; sum matches the $3,486,650 Phase 2 total exactly |
  | 10 | Break down exceptions by exception type. | ok | Lien/Judgment is the top driver (139 of ~425 total exceptions) |

  This is the project's acceptance test: every governed metric formula from Section 7 has now been exercised at least once through the live AI path and produced numbers consistent with the validated dashboard, and both guardrail behaviors from Section 8 (causal questions, undefined-threshold ambiguity) fire correctly rather than fabricating an answer.

- **Post-Phase-12 UI redesign**, matching a supplied mockup (`doma_ai_agent_mockup.png`):
  - Header: `doma` wordmark + "Title Operations Insights" title, styled via inline CSS (no image asset needed).
  - The 6 KPI cards were rebuilt as custom HTML components (`render_kpi_card`) with an icon badge and a "vs. prior week" trend indicator. The trend is a real calculation, not decorative: `app.py` computes each KPI over the 7 days ending on the selected date range's end date vs. the 7 days before that (still respecting the active Lender/State filters), and colors the delta green/red based on whether that specific metric's direction is favorable (e.g. a turnaround-time *decrease* is green, an exception-rate *decrease* is green, an order-volume *decrease* is red) rather than naively coloring all increases green.
  - Layout: the Title Acceptance Eligibility by State table moved into the same row as the two charts (3-column layout) instead of a separate full-width section below.
  - The AI section was renamed "Ask Doma AI" (with a BETA badge, sparkle icon, and explanatory subtitle) and given a bordered card to stand out from the dashboard above it. The 5 example questions render as `st.pills` beneath the input -- clicking one fills the question box via an `on_change` callback rather than auto-submitting.
  - Display formatting: dates in the AI answer table render as `2026-07-27` (not `2026-07-27 00:00:00`) via `charts.format_row_for_display`; float values are rounded to exactly 2 decimals once, in `agent.ask()` right after query execution, so the explanation text, the table, and the chart labels all cite the identical rounded number instead of drifting from a long raw float.
  - The observability panel was reworked per request: Model / Input Tokens / Output Tokens / Total Tokens / Cost / Latency (Rows Returned was dropped). Cost is computed from real Sonnet 5 pricing ($2.00 / $10.00 per MTok in / out) via `agent._estimate_cost_usd()`, present on every response status including `rejected`.
  - **Bug found and fixed during verification, not requested but discovered live:** dollar amounts in the AI's prose explanation (e.g. "$513K") were being parsed as LaTeX math delimiters by `st.markdown`, mangling surrounding text into garbled italic notation. Fixed by escaping literal `$` before rendering (`result["explanation"].replace("$", "\\$")`). Caught by actually reading the rendered screenshot rather than just checking for exceptions -- a reminder that "no console errors" doesn't mean "renders correctly."
  - All changes verified live in a headless browser (Playwright): KPI trend colors independently cross-checked against a raw DuckDB query (not just eyeballed) to confirm the favorable/unfavorable logic, pill-click-fills-input confirmed, and the full ask -> table -> chart -> observability flow re-verified end to end after each fix.

- **Post-Phase-12 UI polish round 2** (matching the real Doma logo + further mockup fidelity):
  - Replaced the CSS text wordmark with the actual supplied logo (`doma_logo.png`), embedded as base64 inline in the header HTML rather than served as a separate file, so there's no extra static-file route to manage.
  - Page background is now pale blue (`#EFF6FF`) with the KPI cards, the 3 chart cards, and the Ask Doma AI section kept white for contrast -- matching the mockup's card-on-tinted-background look.
  - The 3 charts (Order Volume & SLA Compliance, Turnaround Time by Decision Type, Title Acceptance Eligibility by State) are each wrapped in `st.container(border=True, key="chart_card_N")` and styled with a border-radius + drop shadow.
  - **Styling-implementation note worth remembering:** Streamlit's own auto-generated CSS classes for `st.container(border=True)` (the `st-emotion-cache-*` hashes) are not stable across sessions/versions, so they can't be targeted directly. Passing `key="some_name"` to `st.container`/`st.columns` makes Streamlit add a stable `st-key-some_name` class instead -- confirmed by inspecting the rendered DOM (Playwright) before relying on it, not by assuming from memory. Same approach used for the send button (`key="ask_send_btn"`) and the example-question pills (targeted via the stable `button[data-variant="pills"]` attribute selector instead, which needed no key).
  - Example-question pills: light blue background + bold bright-blue text. The "Ask" button was replaced with a circular blue send-icon button (`st.button(icon=":material/send:")`, Streamlit's built-in Material Symbols support) placed directly beside the input via `st.columns([20, 1.3], vertical_alignment="bottom")` -- an actual icon-in-the-input-box overlay isn't achievable without fragile absolute-positioning CSS, so this adjacent-column layout was the robust choice.
  - The header sparkle was an emoji (✨) that can't be recolored via CSS (color emoji glyphs ignore the `color` property) -- replaced with a small inline SVG sparkle path with an explicit blue `fill`, sized larger, matching the pill/button blue exactly.
  - Verified live in a headless browser after each change; the send button was specifically click-tested (not just visually inspected) to confirm it still triggers the same `ask()` pipeline as the old button did.

- **Post-Phase-12 UI polish round 3:**
  - Logo (56px) and title (34px) sized up further.
  - Added Vendor and Property Type as two more filters (5 total: Date Range, Lender, State, Vendor, Property Type) -- both flow through the same `where_sql`/`params` construction and the KPI-trend base clauses already used by Lender/State, so a filtered view's charts, KPIs, and week-over-week trend all stay consistent automatically.
  - The header (logo, title, all 5 filters) is now boxed together in one `st.container(border=True, key="header_card")` card with a drop shadow, visually separated from the KPI row below it. Filter widgets inside it were forced to a white background (`[data-testid="stSelectbox"] [role="group"]`, `[data-testid="stDateInputField"]`) since Streamlit's default fill is a light gray that read as inconsistent against the new white card.
  - The 3 chart-card titles were switched from `st.subheader()` (Streamlit's fixed heading size) to a custom `render_chart_title()` helper matching the Ask Doma AI header's exact 24px/700-weight style, for visual consistency across the dashboard.
  - The 3 chart cards are now a fixed, shared height (`charts.DASHBOARD_CARD_HEIGHT`) applied to both Plotly figures (`fig.update_layout(height=...)`) and the state-eligibility `st.dataframe(..., height=...)`. First tried 420px, which left a distracting half-empty trailing row in the 10-row state table (Streamlit's data grid quantizes to a per-row pixel height, so an arbitrary card height rarely divides evenly); switched to 385px, a clean fit for the header + 10 data rows, which removed the artifact while keeping all 3 cards visually identical in height.
  - The "How this was generated" expander is now styled to match the question input box -- same light-gray fill (`#F0F2F6`, matched from the input's own computed background rather than guessed) and the same 17px font size -- so it reads as part of the Ask Doma AI card rather than a visually distinct default Streamlit expander.

- **Ask Doma AI UX overhaul (analyst-experience redesign):** a deliberate, staged rework of the response experience -- from "chatbot returning SQL results" to "AI analyst showing its work" -- planned in small, individually-approved steps rather than one big rewrite, specifically so each change is easy to explain and defend on its own in the interview.

  - **Step 1 (layout only, done):** `app.py`'s `render_key_insight()` splits the existing single explanation string into a bold headline (first sentence) + supporting detail (the rest), styled as a "KEY INSIGHT" callout with a blue left-border accent -- pure display-layer change, no new Claude calls. The response order was also changed to Key Insight -> chart -> table -> "How this was generated" (previously table came before the chart). Loading copy changed to "Analyzing your title operations data...". **Explicitly temporary:** the headline/detail split is a regex heuristic (first sentence vs. rest), not a real distinction the model produces on purpose -- Step 6 replaces it with structured output.
  - **Step 2 (adaptive visualization, done):** Investigated first rather than assuming a rebuild was needed -- `charts.auto_chart()`'s shape-based heuristic from Phase 10 already implemented all 5 response types from the design spec's Section 11 correctly (verified live against the real API/DB in `scripts/test_step2_adaptive_viz.py`: KPI -> no chart, ranking -> bar, trend -> line, diagnostic breakdown -> bar, a 1,784-row record-level lookup -> no chart). Rather than rebuild working code, extracted the implicit shape logic into a named, independently-tested `classify_response_shape()` function (`single_value` / `time_series` / `categorical` / `record_table`) that `auto_chart()` now builds on -- zero behavior change (confirmed via the full existing `scripts/test_auto_chart.py` suite passing unchanged), but now self-documenting and reusable by Step 6, which will need to know the response type to decide whether "Key Drivers" applies. Deliberately did **not** add a pie/donut chart type here: distinguishing "distribution/share" intent from a plain ranking question isn't reliably inferable from result shape alone, and guessing wrong would violate the "don't overengineer" instruction -- flagged as a possible future addition only if a real trigger condition (e.g. an explicit hint from Step 6's structured output) makes it safe to add.
  - **Step 3 (supporting-data expander, done):** `app.py`'s `render_supporting_table()` caps the inline table at `SUPPORTING_TABLE_ROW_CAP` (10) rows, labeled "Supporting Data -- top 10 of N rows", with a "View supporting data (N rows)" expander holding the complete result only when there's more to show (a <=10-row result renders exactly as before, no extra expander). Because the table is fed the same `sort_for_display`-ordered rows the chart uses, "top 10" is already meaningful rather than arbitrary: for a ranking/breakdown answer it's the 10 highest values; for the 1,784-row "orders over 20 hours" test case it surfaced the 10 longest-running orders (168.2 hrs down to 115.6 hrs) instead of 10 arbitrary rows. Verified live: the capped table + working expander for the 1,784-row case, and confirmed no expander renders at all for a 5-row result.
  - **Step 4 ("How this answer was calculated", done):** Renamed the expander from "How this was generated" and added two new sections ahead of the existing SQL/observability content: **Metric Definitions Used** and **Filters**. The metric-matching mechanism is the key design decision here: rather than asking the LLM to describe its own metrics (which would let it invent a definition), `render_how_calculated()` matches the *result's actual column names* against the same `metrics.METRIC_DEFINITIONS` dict the SQL-generation prompt already uses as the expected aliases -- a plain dict lookup, no extra Claude call, no new governance mechanism. Verified live with "What is the escalation rate by vendor?": the result column `escalation_rate_pct` matched and displayed "Escalation Rate % -- Percentage of orders escalated for manual attention," reproducing the exact governed description from `metrics.py`. Filters (Date, Lender, State, Vendor, Property Type) show the live values of the dashboard's own filter widgets, so a reader can see exactly what scope the answer was computed against. For the `rejected` status (a declined/ambiguous question), the expander correctly shows only Filters + observability -- no Metric Definitions Used (there's no result to match against) and no Generated SQL (nothing safe was generated), confirmed live against "Why did exception rate increase this month?".
  - **Step 5 (observability, done -- small by design):** As anticipated when this plan was proposed, this was already ~90% done -- Model, Input/Output/Total Tokens, Cost, and Latency were already real captured values (from `response.usage` and `time.perf_counter()` in `agent.py`, never hardcoded), just needed re-surfacing, which Step 4 already did. The one genuine gap against the design spec's Section 9: **Rows Analyzed** had been explicitly removed from this panel in an earlier, unrelated styling round; added it back since the new spec calls for it, sourced from the same real `sql_execution.rows_returned` value that was already being captured internally but not displayed. Shows "-" (not a fabricated `0` or blank) when no query ran, verified live for a `rejected` question -- Rows Analyzed correctly shows "-" while Model/Tokens/Cost/Latency for the SQL-generation call still show real numbers, since that Claude call did happen even though no query executed.
  - **Step 6 (Key Drivers + follow-up questions, done -- the significant one):** This is the one step that genuinely changes `agent.py`'s explanation contract, flagged in advance before building it. `explain_results_with_meta()` now asks Claude for a single JSON object (`headline`, `detail`, `drivers`, `follow_up_questions`) instead of a 2-4 sentence paragraph -- `_parse_explanation()` parses it (tolerating a markdown code fence, same issue seen with SQL generation) and degrades gracefully to a fallback shape instead of crashing if the model ever returns non-JSON. `ask()`'s `"explanation"` field is now this dict, not a string; `explain_results()` (the plain-string wrapper other code might still want) reconstructs `f"{headline} {detail}"` for backward compatibility. In `app.py`, `render_key_insight()` now reads `headline`/`detail` directly from the model's own structured output -- **retiring the Step 1 regex sentence-split exactly as that step's docstring promised it would be replaced.**
    - **Guardrail interaction, flagged before building and confirmed unchanged:** genuinely causal "why" questions are still rejected at the SQL-generation stage (Phase 6 behavior, unchanged) and never reach the explanation step, so Key Drivers cannot literally trigger off "why did X happen" -- it populates instead for *answered* breakdown/comparison questions where the data supports naming contributors (e.g. "break down exceptions by type" -> 3 drivers, all using associative language like "concentrated in" / "add a significant secondary share", never causal claims), and correctly returns an empty list (rendering nothing) for a plain ranking or single-KPI question. Verified with `scripts/test_step6_structured_explanation.py` across 4 question types against the real API: 0 drivers for a ranking question, 3 well-grounded drivers for a breakdown question, 0 drivers for a single KPI, and the causal question confirmed still rejected before reaching this code at all.
    - **Follow-up questions** are capped at 3, must reference real entities from the actual result (verified: a breakdown by exception type produced follow-ups naming the specific exception types and asking to further break them out by vendor/state), and render as `st.pills` under an "EXPLORE FURTHER" label. Unlike the top example-question pills (fill-only), clicking a follow-up both fills the input and sets a `pending_followup` session-state flag that the main control flow checks on the next rerun -- so it submits automatically, per the design spec's explicit ask ("clicking a follow-up should submit it as the next question"). Verified live end-to-end via Playwright, including an instructive edge case: one AI-generated follow-up ("...by vendor or lender?") was itself ambiguous, and the guardrail correctly asked for clarification instead of guessing -- proof the guardrails apply uniformly to AI-generated follow-ups, not just user-typed questions. A second follow-up click produced a genuinely new, correct answer, and in one run the model itself caught and honestly reported a data-shape quirk (a filtered exception type not appearing in its own grouped result) rather than fabricating numbers to fill the gap.
    - **Response ordering corrected** to match the design spec's full diagram, which (on a literal re-read) places the raw "Supporting Data" table *after* the collapsed "How this answer was calculated" expander, not before it: Key Insight -> chart -> Key Drivers -> Follow-ups -> How Calculated (collapsed) -> Supporting Data. The Step 3 supporting-table code itself didn't change, just where it's called from.
  - **Step 7 (error/ambiguity copy, done):** `agent.SYSTEM_PROMPT`'s single blended "NO_SQL: short reason or clarifying question" rule was split into two explicit, mutually exclusive styles the model is told to choose between based on *why* it can't answer: (1) **insufficient data** -- a genuinely unanswerable question (a causal "why", a field this schema doesn't track) gets one plain declarative sentence; (2) **ambiguous** -- a vague term with multiple reasonable readings (e.g. "performance", "at risk") gets exactly one concise clarifying question naming the specific options. Verified against 4 real questions spanning both styles: a causal question and an out-of-schema question ("customer satisfaction score") both produced the declarative style -- the latter reproducing the spec's example phrasing verbatim ("I don't have enough information in the available title operations data to answer that question"); a vague "How is our performance?" and the previously-tested undefined-"at risk"-threshold question both produced a single naming-the-options clarifying question, matching the spec's own worked example almost exactly. `app.py`'s new `render_rejected_message()` strips the internal `"NO_SQL:"` sentinel prefix (previously shown raw to users) and gives the two styles distinct visual treatment -- a plain warning box for the declarative case, a blue "To answer that, I need a bit more detail:" info box for the clarifying-question case -- detected via a cheap, reliable heuristic (does the message end in "?") rather than adding a new model output field for it.

---

## 12. Open questions / things to double-check before the interview

- [ ] Confirm whether Avg TAT (18.9 hrs) is computed over all 5,000 orders or only `status = 'Completed'` ones — don't guess, check both in DuckDB (Section 4 data quality note).
- [ ] Finalize which Claude model is used and be ready to explain the choice (cost/latency/quality tradeoff).
- [ ] Have 2-3 example AI questions memorized end-to-end (question → generated SQL → answer) so you can walk through one live without reading from screen.
- [ ] Be ready to name what you'd change for a real production version (see Section 10, "Production considerations") — Jay's background is applied AI in production, so this is likely to come up.

---

## 13. Example questions the AI agent should handle (from the design spec)

1. "What are the top 5 vendors by order volume?"
2. "Why did exception rate increase this month?"
3. "Show SLA compliance by state."
4. "Which orders are at risk of missing SLA?"
5. "What is the average turnaround time by lender?"
6. "Which vendors have the highest average turnaround time?"
7. "Compare automated versus manual review turnaround time."

These double as the Phase 12 test set.
