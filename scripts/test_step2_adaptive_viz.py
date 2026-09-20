"""
UX Step 2: confirm adaptive visualization end to end against the real API/DB,
one representative question per response type (design spec Section 11).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import ask
from charts import auto_chart, classify_response_shape, sort_for_display

CASES = [
    ("A - KPI", "What is our SLA compliance?", "single_value", None),
    ("B - Ranking", "Which vendors have the highest average turnaround time?", "categorical", "bar"),
    ("C - Trend", "How has SLA compliance changed over the last 6 months?", "time_series", "scatter"),
    ("D - Diagnostic breakdown", "Break down exceptions by exception type this year", "categorical", "bar"),
    (
        "E - Record-level",
        "Show me order_id and turnaround_hours for orders with turnaround_hours greater than 20 hours",
        "record_table",
        None,
    ),
]

failures = 0
for label, question, expected_shape, expected_chart_type in CASES:
    result = ask(question)
    print(f"=== {label}: {question!r} ===")
    if result["status"] != "ok":
        print(f"  UNEXPECTED status={result['status']}: {result['message'][:150]}")
        failures += 1
        print()
        continue

    display_rows = sort_for_display(result["columns"], result["rows"])
    got_shape = classify_response_shape(result["columns"], display_rows)
    fig = auto_chart(result["columns"], display_rows)
    got_chart_type = fig.data[0].type if fig is not None else None

    ok = got_shape == expected_shape and got_chart_type == expected_chart_type
    status = "OK" if ok else "MISMATCH"
    if not ok:
        failures += 1
    print(f"  [{status}] rows={len(result['rows'])} shape={got_shape!r} chart={got_chart_type!r}")
    print(f"           (expected shape={expected_shape!r} chart={expected_chart_type!r})")
    print()

print("All cases passed." if failures == 0 else f"{failures} case(s) FAILED.")
