"""
Loads the synthetic Doma dataset into a local DuckDB file and hands out
connections to it. This is the one place both the Streamlit dashboard
and the AI agent go to reach the data -- keeping it in one place is
what lets both sides stay consistent.
"""

from pathlib import Path

import duckdb
import pandas as pd

PROJECT_ROOT = Path(__file__).parent
DATA_FILE = PROJECT_ROOT / "data" / "doma_title_operations.xlsx"
DB_FILE = PROJECT_ROOT / "db" / "doma.duckdb"


def load_database(db_path: Path = DB_FILE, data_path: Path = DATA_FILE) -> None:
    """Read the Excel workbook and (re)build the DuckDB tables from it."""
    orders = pd.read_excel(data_path, sheet_name="title_orders")
    vendors = pd.read_excel(data_path, sheet_name="vendors")

    if db_path.exists():
        db_path.unlink()

    con = duckdb.connect(str(db_path))
    # DuckDB can query the local pandas DataFrames (`orders`, `vendors`)
    # directly by name -- no separate "insert" step needed.
    con.execute("CREATE TABLE title_orders AS SELECT * FROM orders")
    con.execute("CREATE TABLE vendors AS SELECT * FROM vendors")
    con.close()


def get_connection(db_path: Path = DB_FILE, read_only: bool = False) -> duckdb.DuckDBPyConnection:
    """Open a connection to the DuckDB database file."""
    return duckdb.connect(str(db_path), read_only=read_only)
