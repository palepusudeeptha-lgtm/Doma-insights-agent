"""
UX Step 6: confirm the explanation step returns real structured data
(headline/detail/drivers/follow_up_questions) end to end against the real
API/DB, and that drivers/follow-ups behave sensibly across question types.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import ask

QUESTIONS = [
    ("Plain ranking", "What are the top 5 vendors by order volume?"),
    ("Breakdown (drivers plausible)", "Break down exceptions by exception type this year"),
    ("Single KPI", "What is our SLA compliance?"),
    ("Rejected causal question", "Why did exception rate increase this month?"),
]

REQUIRED_KEYS = {"headline", "detail", "drivers", "follow_up_questions"}

failures = 0
for label, question in QUESTIONS:
    result = ask(question)
    print(f"=== {label}: {question!r} ===")
    print(f"  status: {result['status']}")

    if result["status"] != "ok":
        print(f"  message: {result['message'][:150]}")
        print()
        continue

    exp = result["explanation"]
    missing = REQUIRED_KEYS - exp.keys()
    if missing:
        print(f"  [FAIL] missing keys: {missing}")
        failures += 1
    if not isinstance(exp["drivers"], list) or not isinstance(exp["follow_up_questions"], list):
        print("  [FAIL] drivers/follow_up_questions are not lists")
        failures += 1
    if len(exp["drivers"]) > 3 or len(exp["follow_up_questions"]) > 3:
        print("  [FAIL] drivers/follow_up_questions exceeded the 3-item cap")
        failures += 1
    if not exp["headline"]:
        print("  [FAIL] empty headline")
        failures += 1

    print(f"  headline: {exp['headline']}")
    print(f"  detail: {exp['detail']}")
    print(f"  drivers ({len(exp['drivers'])}): {exp['drivers']}")
    print(f"  follow_up_questions ({len(exp['follow_up_questions'])}): {exp['follow_up_questions']}")
    print()

print("All cases passed." if failures == 0 else f"{failures} case(s) FAILED.")
