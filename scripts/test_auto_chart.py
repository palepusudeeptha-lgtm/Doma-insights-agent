"""Phase 10 (+ time-series extension, + Step 2 classifier): exercise
classify_response_shape(), auto_chart(), and sort_for_display()."""

import datetime
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from charts import auto_chart, classify_response_shape, sort_for_display


def d(s):
    return datetime.date.fromisoformat(s)


CASES = [
    # (columns, rows, expect_chart, expect_line)
    (["vendor_name", "total_orders"], [("A", 792), ("B", 739), ("C", 698)], True, False),
    (["state", "sla_compliance_pct"], [("AZ", 87.2), ("CA", 86.9)], True, False),
    (["review_type", "avg_tat", "total_orders"], [("Automated", 4.8, 3155), ("Manual", 43.1, 1845)], True, False),
    (["total_orders"], [(5000,)], False, False),  # single column -- no chart
    (["vendor_name", "total_orders"], [("A", 792)], False, False),  # single row -- no chart
    (["state", "region", "count"], [("CA", "West", 1), ("TX", "South", 2)], False, False),  # 2nd col not numeric
    (["a", "b"], [(str(i), i) for i in range(30)], False, False),  # too many rows for a bar chart
    (["total_orders"], [], False, False),  # empty
    # time series -> line chart, and allowed to exceed the 25-row bar cap
    (["week_start", "avg_turnaround_hours"], [(d("2026-08-03"), 17.8), (d("2026-07-27"), 20.5)], True, True),
    (["day", "orders"], [(d(f"2026-01-{i:02d}"), i) for i in range(1, 31)], True, True),
]

# Step 2: the named classification each of the 5 response types (design
# doc Section 11 Types A-E) should map to. This is what auto_chart() is
# built on now, so a chart-type test doubles as a classification test --
# but asserting the label directly makes the mapping explicit and catches
# a regression even if a future chart-type change accidentally preserved
# the same True/False chart outcome for the wrong reason.
SHAPE_CASES = [
    ("single_value (Type A: KPI)", ["sla_compliance_pct"], [(86.5,)], "single_value"),
    ("categorical (Type B: ranking)", ["vendor_name", "total_orders"], [("A", 792), ("B", 739)], "categorical"),
    (
        "time_series (Type C: trend)",
        ["month", "sla_compliance_pct"],
        [(d("2026-03-01"), 86.5), (d("2026-04-01"), 85.0)],
        "time_series",
    ),
    (
        "categorical (Type D: diagnostic breakdown)",
        ["exception_type", "total_orders"],
        [("Lien/Judgment", 139), ("Ownership Issue", 92)],
        "categorical",
    ),
    (
        "record_table (Type E: record-level lookup, many rows)",
        ["order_id", "turnaround_hours"],
        [(f"ORD{i}", 40 + i) for i in range(50)],
        "record_table",
    ),
]

failures = 0
for columns, rows, expect_chart, expect_line in CASES:
    fig = auto_chart(columns, rows)
    got_chart = fig is not None
    got_line = got_chart and fig.data[0].type == "scatter"
    ok = got_chart == expect_chart and (not got_chart or got_line == expect_line)
    status = "OK" if ok else "MISMATCH"
    if not ok:
        failures += 1
    print(f"[{status}] columns={columns} rows={len(rows)} -> chart={got_chart} line={got_line}")

print()
print("--- classify_response_shape: Types A-E from the design spec ---")
for label, columns, rows, expected_shape in SHAPE_CASES:
    got_shape = classify_response_shape(columns, rows)
    status = "OK" if got_shape == expected_shape else "MISMATCH"
    if status == "MISMATCH":
        failures += 1
    print(f"[{status}] {label}: got={got_shape!r} expected={expected_shape!r}")

print()
print("--- sort_for_display: time series sorts chronologically, not by value ---")
ts_columns = ["week_start", "avg_turnaround_hours"]
ts_rows = [(d("2026-08-31"), 23.7), (d("2026-07-27"), 20.5), (d("2026-08-03"), 17.8)]
sorted_ts = sort_for_display(ts_columns, ts_rows)
print(sorted_ts)
assert [r[0] for r in sorted_ts] == [d("2026-07-27"), d("2026-08-03"), d("2026-08-31")], "time series not chronological!"
print("OK -- chronological order preserved")

print()
print("All cases passed." if failures == 0 else f"{failures} case(s) FAILED.")
