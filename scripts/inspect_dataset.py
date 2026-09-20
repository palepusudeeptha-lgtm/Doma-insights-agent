"""
Phase 1: Inspect the synthetic Doma title operations dataset.

Reads every sheet in the Excel workbook and prints schema, grain,
nulls, and distinct-value summaries so we know exactly what we're
working with before building anything on top of it.
"""

import pandas as pd

DATA_FILE = "data/doma_title_operations.xlsx"

sheets = pd.read_excel(DATA_FILE, sheet_name=None)

print("=" * 70)
print("SHEETS FOUND:", list(sheets.keys()))
print("=" * 70)

orders = sheets["title_orders"]

print(f"\ntitle_orders: {orders.shape[0]} rows, {orders.shape[1]} columns")
print("\n--- dtypes ---")
print(orders.dtypes)

print("\n--- null counts (columns with at least 1 null) ---")
null_counts = orders.isnull().sum()
print(null_counts[null_counts > 0])

print("\n--- first 3 rows ---")
print(orders.head(3).to_string())

print("\n--- distinct values for key categorical columns ---")
categorical_cols = [
    "status", "decision_type", "automated_flag", "exception_flag",
    "exception_type", "title_acceptance_eligible", "loan_type",
    "property_type", "state", "escalated_flag",
]
for col in categorical_cols:
    print(f"\n{col}:")
    print(orders[col].value_counts(dropna=False))

print("\n--- vendors sheet ---")
print(sheets["vendors"])

print("\n--- data_dictionary sheet ---")
print(sheets["data_dictionary"].to_string())

print("\n--- kpi_guide sheet ---")
print(sheets["kpi_guide"].to_string())
