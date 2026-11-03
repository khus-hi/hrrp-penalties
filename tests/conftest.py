"""Shared helpers. Tests use tiny hand-built tables in an in-memory DuckDB, so they never
download anything or need data/hrrp.duckdb."""
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]


def run_sql_file(con, rel_path: str) -> None:
    con.execute((ROOT / rel_path).read_text())


@pytest.fixture
def con():
    c = duckdb.connect(":memory:")
    c.execute("CREATE SCHEMA raw")
    run_sql_file(c, "models/staging/00_macros.sql")
    yield c
    c.close()
