"""
Phase 2: Validate DuckDB KPI math against the Looker Studio dashboard.

Each query below is the kpi_guide formula written as real SQL. Target
values are what the Looker Studio dashboard displayed. We check both
the number and how close it is -- "close enough to be the same metric"
is not good enough; we want to understand any gap, not paper over it.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_connection

con = get_connection(read_only=True)

TARGETS = {
    "Total Orders": 5000,
    "SLA Compliance %": 86.5,
    "Avg TAT (hrs)": 18.9,
    "Automation Rate %": 63.1,
    "Exception Rate %": 8.5,
    "Estimated Borrower Savings ($)": 3_500_000,
}

results = {}

results["Total Orders"] = con.execute(
    "SELECT COUNT(order_id) FROM title_orders"
).fetchone()[0]

results["SLA Compliance %"] = con.execute(
    "SELECT 100.0 * AVG(CASE WHEN turnaround_hours <= sla_hours THEN 1 ELSE 0 END) "
    "FROM title_orders"
).fetchone()[0]

# Avg TAT -- two variants, since turnaround_hours has no nulls even for
# the 135 still-open orders. Check both against the target.
results["Avg TAT (hrs) -- all rows"] = con.execute(
    "SELECT AVG(turnaround_hours) FROM title_orders"
).fetchone()[0]

results["Avg TAT (hrs) -- Completed only"] = con.execute(
    "SELECT AVG(turnaround_hours) FROM title_orders WHERE status = 'Completed'"
).fetchone()[0]

results["Automation Rate %"] = con.execute(
    "SELECT 100.0 * AVG(CASE WHEN automated_flag = 'Yes' THEN 1 ELSE 0 END) "
    "FROM title_orders"
).fetchone()[0]

results["Exception Rate %"] = con.execute(
    "SELECT 100.0 * AVG(CASE WHEN exception_flag = 'Yes' THEN 1 ELSE 0 END) "
    "FROM title_orders"
).fetchone()[0]

results["Estimated Borrower Savings ($)"] = con.execute(
    "SELECT SUM(estimated_borrower_savings) FROM title_orders"
).fetchone()[0]

con.close()

print(f"{'Metric':<38}{'Computed':>15}{'Target':>15}")
print("-" * 68)
for label, value in results.items():
    target_key = label.replace(" -- all rows", "").replace(" -- Completed only", "")
    target = TARGETS.get(target_key, "")
    computed_str = f"{value:,.1f}" if isinstance(value, float) else f"{value:,}"
    target_str = f"{target:,.1f}" if isinstance(target, float) else f"{target}"
    print(f"{label:<38}{computed_str:>15}{target_str:>15}")
