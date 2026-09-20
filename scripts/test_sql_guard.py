"""Phase 7: exercise sql_guard.py against safe queries, attacks, and edge cases."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sql_guard import is_safe_select

CASES = [
    # (sql, expected_safe)
    ("SELECT * FROM title_orders", True),
    ("SELECT * FROM title_orders;", True),
    ("  select state, count(*) from title_orders group by state  ", True),
    (
        "WITH by_state AS (SELECT state, COUNT(*) AS n FROM title_orders GROUP BY state) "
        "SELECT * FROM by_state ORDER BY n DESC",
        True,
    ),
    # column names that merely *contain* a forbidden word shouldn't false-positive
    ("SELECT order_id, updated_at, created_by FROM title_orders", True),
    ("NO_SQL: this question is ambiguous", False),
    ("", False),
    ("   ", False),
    ("DROP TABLE title_orders", False),
    ("SELECT * FROM title_orders; DROP TABLE title_orders;", False),
    ("UPDATE title_orders SET status = 'Completed'", False),
    ("DELETE FROM title_orders", False),
    ("INSERT INTO title_orders VALUES (1)", False),
    ("ALTER TABLE title_orders ADD COLUMN x INT", False),
    ("CREATE TABLE evil AS SELECT * FROM title_orders", False),
    ("COPY title_orders TO '/tmp/out.csv'", False),
    ("ATTACH '/tmp/other.db' AS other", False),
    ("PRAGMA database_list", False),
    ("SELECT * FROM title_orders -- ; DROP TABLE title_orders", True),
    ("SELECT * FROM title_orders /* DROP TABLE title_orders */", True),
]

failures = 0
for sql, expected_safe in CASES:
    safe, detail = is_safe_select(sql)
    status = "OK" if safe == expected_safe else "MISMATCH"
    if status == "MISMATCH":
        failures += 1
    print(f"[{status}] safe={safe!s:5} expected={expected_safe!s:5} sql={sql!r}")
    print(f"         -> {detail!r}")

print()
print("All cases passed." if failures == 0 else f"{failures} case(s) FAILED.")
