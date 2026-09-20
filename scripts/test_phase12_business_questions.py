"""
Phase 12: run the full business-question test set end to end through agent.ask()
and print a summary -- status, SQL, sample rows, explanation, and observability
totals -- for manual review against the design spec's expectations.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import ask

# The 7 questions from the design spec (INTERVIEW_PREP.md Section 13), plus 3
# more added here to reach a representative ~10 and exercise metrics/shapes
# the original 7 don't touch: escalation rate, a monetary metric over time
# (line chart), and a non-METRIC_DEFINITIONS groupby (exception type).
QUESTIONS = [
    "What are the top 5 vendors by order volume?",
    "Why did exception rate increase this month?",
    "Show SLA compliance by state.",
    "Which orders are at risk of missing SLA?",
    "What is the average turnaround time by lender?",
    "Which vendors have the highest average turnaround time?",
    "Compare automated versus manual review turnaround time.",
    "What is the escalation rate by vendor?",
    "What is the estimated borrower savings by month?",
    "Break down exceptions by exception type.",
]

summary = []

for i, question in enumerate(QUESTIONS, 1):
    result = ask(question)
    obs = result["observability"]
    total_tokens = obs["total_input_tokens"] + obs["total_output_tokens"]

    print(f"[{i}] Q: {question}")
    print(f"    status: {result['status']}")
    print(f"    sql: {result['sql']!r}")
    if result["status"] == "ok":
        print(f"    columns: {result['columns']}")
        print(f"    rows returned: {len(result['rows'])}")
        for row in result["rows"][:5]:
            print(f"      {row}")
        exp = result["explanation"]
        print(f"    headline: {exp['headline']}")
        print(f"    detail: {exp['detail']}")
        if exp["drivers"]:
            print(f"    drivers: {exp['drivers']}")
        if exp["follow_up_questions"]:
            print(f"    follow_up_questions: {exp['follow_up_questions']}")
    else:
        print(f"    message: {result['message']}")
    print(f"    tokens: {total_tokens}, latency: {obs['total_latency_seconds']:.2f}s")
    print("-" * 100)

    summary.append(
        {
            "question": question,
            "status": result["status"],
            "rows": len(result["rows"]) if result["status"] == "ok" else None,
            "tokens": total_tokens,
            "latency": obs["total_latency_seconds"],
        }
    )

print("\n=== SUMMARY ===")
for i, s in enumerate(summary, 1):
    rows_str = s["rows"] if s["rows"] is not None else "-"
    print(
        f"[{i}] {s['status']:9} rows={rows_str!s:4} tokens={s['tokens']:5} "
        f"latency={s['latency']:.2f}s  {s['question']}"
    )

n_ok = sum(1 for s in summary if s["status"] == "ok")
n_rejected = sum(1 for s in summary if s["status"] == "rejected")
n_error = sum(1 for s in summary if s["status"] == "error")
total_tokens_all = sum(s["tokens"] for s in summary)
total_latency_all = sum(s["latency"] for s in summary)
print(f"\n{n_ok} ok, {n_rejected} rejected, {n_error} error out of {len(summary)}")
print(f"Total tokens across all questions: {total_tokens_all}")
print(f"Total latency across all questions: {total_latency_all:.2f}s")
