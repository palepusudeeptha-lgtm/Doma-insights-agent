"""Phase 8: exercise agent.ask() -- generate -> validate -> execute -- end to end."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import ask

QUESTIONS = [
    "What are the top 5 vendors by order volume?",
    "Why did exception rate increase this month?",  # expect: rejected (causal)
    "Show SLA compliance by state.",
    "Which orders are at risk of missing SLA?",  # expect: rejected (ambiguous)
    "What is the average turnaround time by lender?",
    "Which vendors have the highest average turnaround time?",
    "Compare automated versus manual review turnaround time.",
    "How many orders were there for lender 'Definitely Not A Real Lender'?",  # expect: ok, 0 rows
]

for question in QUESTIONS:
    result = ask(question)
    print(f"Q: {question}")
    print(f"  status: {result['status']}")
    if result["status"] == "ok":
        print(f"  sql: {result['sql']}")
        print(f"  columns: {result['columns']}")
        print(f"  rows returned: {len(result['rows'])}")
        for row in result["rows"][:5]:
            print(f"    {row}")
        exp = result["explanation"]
        print(f"  headline: {exp['headline']}")
        print(f"  detail: {exp['detail']}")
        if exp["drivers"]:
            print(f"  drivers: {exp['drivers']}")
        if exp["follow_up_questions"]:
            print(f"  follow_up_questions: {exp['follow_up_questions']}")
    else:
        print(f"  sql: {result['sql']!r}")
        print(f"  message: {result['message']}")
    print("-" * 80)
