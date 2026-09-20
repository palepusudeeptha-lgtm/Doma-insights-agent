"""Phase 2: Build (or rebuild) the DuckDB database from the Excel dataset."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from database import load_database, get_connection

load_database()

con = get_connection(read_only=True)
orders_count = con.execute("SELECT COUNT(*) FROM title_orders").fetchone()[0]
vendors_count = con.execute("SELECT COUNT(*) FROM vendors").fetchone()[0]
con.close()

print(f"Loaded db/doma.duckdb")
print(f"  title_orders: {orders_count} rows")
print(f"  vendors: {vendors_count} rows")
