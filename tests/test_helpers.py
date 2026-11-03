"""Small helpers used across the pipeline."""
import duckdb
import pytest

from ingest.load import norm
from models.build import md_table


@pytest.mark.parametrize("raw, expected", [
    ("Facility ID", "facility_id"),
    ("Excess Readmission Ratio (AMI)", "excess_readmission_ratio_ami"),
    ("  Peer-Group  Median ", "peer_group_median"),
    ("% Dual", "dual"),
])
def test_norm_column_names(raw, expected):
    assert norm(raw) == expected


def test_md_table_formats_counts_years_and_dollars():
    con = duckdb.connect(":memory:")
    out = md_table(con, "SELECT 2024 AS year, 12345 AS n, 315600000.0::DOUBLE AS usd, 0.99411::DOUBLE AS factor, NULL AS blank")
    assert out.splitlines()[2] == "| 2024 | 12,345 | 315,600,000 | 0.9941 |  |"


def test_md_table_empty():
    con = duckdb.connect(":memory:")
    assert md_table(con, "SELECT 1 AS x WHERE false") == "_(no rows)_\n"
