"""Phase 6: manually eyeball the SQL Claude generates for the design spec's example questions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import generate_sql

QUESTIONS = [
    "What are the top 5 vendors by order volume?",
    "Why did exception rate increase this month?",
    "Show SLA compliance by state.",
    "Which orders are at risk of missing SLA?",
    "What is the average turnaround time by lender?",
    "Which vendors have the highest average turnaround time?",
    "Compare automated versus manual review turnaround time.",
]

for question in QUESTIONS:
    print(f"Q: {question}")
    print(generate_sql(question))
    print("-" * 80)
