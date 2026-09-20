"""Phase 11: check that ask() returns sensible observability data for each status."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import ask

QUESTIONS = [
    "What are the top 5 vendors by order volume?",  # ok
    "Why did exception rate increase this month?",  # rejected
    "Show me the schema of a table that does not exist, xyz_table",  # likely error or NO_SQL
]

for question in QUESTIONS:
    result = ask(question)
    print(f"Q: {question}")
    print(f"  status: {result['status']}")
    print(f"  observability: {json.dumps(result['observability'], indent=2)}")
    print("-" * 80)
