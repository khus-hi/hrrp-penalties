"""Step 3: build the SQL models and data-quality checks, then write a report.

Order: models/staging -> models/intermediate -> models/marts -> checks/.
Each layer only reads from the layer before it (raw -> stg -> int -> mart), which is
the same idea dbt uses, kept dependency-free here: just .sql files run in order.

Run:  python -m models.build
Output: data/hrrp.duckdb (tables mart.hospital, qa.*) and docs/data_quality_report.md
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ingest import config as C

LAYERS = ["models/staging", "models/intermediate", "models/marts", "checks"]
REPORT = C.ROOT / "docs" / "data_quality_report.md"


def run_sql(con, root: Path):
    for layer in LAYERS:
        for f in sorted((root / layer).glob("*.sql")):
            print(f"  running {f.relative_to(root)}")
            con.execute(f.read_text())


def md_table(con, sql: str) -> str:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return "_(no rows)_\n"
    fmt = lambda v: "" if v is None else (f"{v:,}" if isinstance(v, int) else str(v))
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def write_report(con):
    failed = con.execute("SELECT count(*) FROM qa.assertions WHERE failing_rows > 0").fetchone()[0]
    parts = [
        "# Data-quality report",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m models.build` "
        "from the files in data/raw/ (see data/raw/manifest.json for exact downloads)._",
        "## Join funnel (cumulative)", md_table(con, "SELECT * FROM qa.join_funnel"),
        "## Coverage by source (independent)",
        md_table(con, "SELECT source, matched, total, round(100.0*matched/total, 1) AS pct "
                      "FROM qa.source_coverage"),
        "## Unmatched CCNs by reason",
        md_table(con, "SELECT reason, count(*) AS ccns FROM qa.unmatched_ccns GROUP BY 1 ORDER BY 2 DESC"),
        "Full list: `SELECT * FROM qa.unmatched_ccns`.",
        "## Suppressed / missing HRRP values by condition", md_table(con, "SELECT * FROM qa.suppressed_values"),
        "## Text values turned into NULL", md_table(con, "SELECT * FROM qa.non_numeric_values"),
        "## IPPS spreadsheet columns not found (left NULL)", md_table(con, "SELECT * FROM qa.column_mapping_misses"),
        "## Parent-system crosswalk (check against each 10-K)",
        md_table(con, "SELECT * FROM qa.system_summary"),
        md_table(con, "SELECT * FROM qa.system_owner_names"),
        "## Cost report fiscal-year ends (federal FY2026 = Oct 2025 to Sep 2026)",
        md_table(con, "SELECT * FROM qa.cost_report_years"),
        f"## Assertions ({failed} failing)",
        md_table(con, "SELECT test, failing_rows, CASE WHEN failing_rows = 0 THEN 'pass' ELSE 'FAIL' END AS result "
                      "FROM qa.assertions"),
    ]
    REPORT.write_text("\n\n".join(parts))
    return failed


def main(db_path=C.DB_PATH):
    if not Path(db_path).exists():
        sys.exit(f"{db_path} not found. Run python -m ingest.load first.")
    con = duckdb.connect(str(db_path))
    print("Building models:")
    run_sql(con, C.ROOT)
    failed = write_report(con)
    print("\nJoin funnel:")
    for r in con.execute("SELECT * FROM qa.join_funnel").fetchall():
        print(f"  {r[0]}. {r[1]:58s} {r[2]:>6,}  (dropped {r[3] if r[3] is not None else '-'})")
    print(f"\nAssertions failing: {failed}. Full report: {REPORT}")
    con.close()


if __name__ == "__main__":
    main()
