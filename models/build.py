"""Step 3: build the models and run the data-quality tests with dbt, then write a report.

The SQL lives in the dbt project in dbt/ (staging -> intermediate -> marts, plus qa
report tables, with the checks as dbt tests). This script is a thin wrapper so the
pipeline keeps one command per step:

    1. dbt source freshness   how old each raw table is (reported, never fatal)
    2. dbt build              seeds, models and tests in dependency order
    3. qa.assertions          one row per dbt test (read by analysis/penalty_report.py)
    4. docs/data_quality_report.md

Run:  python -m models.build          (or: make build)
Same thing by hand:  cd dbt && dbt build
Output: data/hrrp.duckdb (schemas stg, int, mart, qa, seed, qa_failures) and the report.
Exit code is 1 when a model fails or an error-severity test fails; warnings don't stop it.
"""
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ingest import config as C

DBT_DIR = C.ROOT / "dbt"
REPORT = C.ROOT / "docs" / "data_quality_report.md"
RAW_TABLES = {"hrrp_hospital", "hospital_general_info", "hrrp_supplemental", "hrrp_table15",
              "hospital_cost_report", "hospital_enrollments", "hospital_all_owners",
              "zcta_county_rel", "sec_facts", "acs_county", "column_mapping_log"}


def dbt(*args):
    """Run a dbt command in-process (same as typing it in dbt/) and return dbt's result."""
    from dbt.cli.main import dbtRunner  # imported here so `import models.build` stays light
    return dbtRunner().invoke([*args, "--project-dir", str(DBT_DIR), "--profiles-dir", str(DBT_DIR)])


def md_table(con, sql: str) -> str:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    if not rows:
        return "_(no rows)_\n"
    def fmt(v):
        # Thousands separators for counts and dollars, but not for years like 2024.
        if v is None:
            return ""
        if isinstance(v, int):
            return f"{v:,}" if abs(v) >= 10000 else str(v)
        if isinstance(v, float):
            return f"{v:,.0f}" if abs(v) >= 1000 else f"{v:.4g}"
        return str(v)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(fmt(v) for v in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def test_label(node):
    """Readable name for a test: its description, or e.g. 'unique: mart_hospital.ccn'."""
    if node.description:
        return node.description
    meta = getattr(node, "test_metadata", None)
    if meta is None:
        return node.name
    model = node.file_key_name.split(".")[-1] if node.file_key_name else ""
    target = f"{model}.{node.column_name}" if node.column_name else model
    kw = meta.kwargs
    if meta.name == "relationships":
        to = str(kw.get("to", "")).replace("ref('", "").replace("')", "")
        return f"relationships: {target} -> {to}.{kw.get('field')}"
    if meta.name == "accepted_values":
        return f"accepted_values: {target} in {len(kw.get('values', []))} listed values"
    if meta.name == "expression_is_true":
        return f"{target} {kw.get('expression')}"
    return f"{meta.name}: {target}"


def test_rows(build_result):
    """One tuple per dbt test: (label, test name, model(s), failing rows, status)."""
    rows = []
    for r in build_result.result or []:
        node = r.node
        if node.resource_type != "test":
            continue
        models = ", ".join(sorted(n.split(".")[-1] for n in node.depends_on.nodes))
        failures = r.failures if str(r.status) in ("pass", "warn", "fail") else None
        rows.append((test_label(node), node.name, models, failures, str(r.status)))
    order = {"error": 0, "fail": 1, "warn": 2, "skipped": 3, "pass": 4}
    return sorted(rows, key=lambda t: (order.get(t[4], 9), t[0]))


def freshness_rows(fresh_result):
    rows = []
    for r in getattr(fresh_result, "result", None) or []:
        loaded = getattr(r, "max_loaded_at", None)
        age = getattr(r, "age", None)
        if loaded is not None and loaded.year < 1900:  # empty table: dbt reports year 1
            loaded, age = None, None
        rows.append((r.node.name, f"{loaded:%Y-%m-%d %H:%M}" if loaded else "",
                     round(age / 86400, 1) if age is not None else None, str(r.status)))
    return sorted(rows)


def write_assertions(con, tests):
    # Same table (and test/failing_rows columns) the hand-written checks used to create,
    # so analysis/penalty_report.py keeps working unchanged.
    con.execute("CREATE SCHEMA IF NOT EXISTS qa")
    con.execute("CREATE OR REPLACE TABLE qa.assertions (test VARCHAR, failing_rows BIGINT, "
                "dbt_test VARCHAR, models VARCHAR, result VARCHAR)")
    con.executemany("INSERT INTO qa.assertions VALUES (?, ?, ?, ?, ?)",
                    [(d, f, n, m, s) for d, n, m, f, s in tests])


def write_report(con, tests, freshness):
    failing = sum(1 for t in tests if t[4] in ("fail", "error"))
    warned = sum(1 for t in tests if t[4] == "warn")
    if freshness:
        con.execute("CREATE OR REPLACE TEMP TABLE _fresh (source VARCHAR, last_loaded_utc VARCHAR, "
                    "age_days DOUBLE, result VARCHAR)")
        con.executemany("INSERT INTO _fresh VALUES (?, ?, ?, ?)", freshness)
        fresh_md = md_table(con, "SELECT * FROM _fresh")
    else:
        fresh_md = "_Not run. Re-run `python -m ingest.load` so each raw table has a `_loaded_at` column._\n"
    parts = [
        "# Data-quality report",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m models.build` (dbt build) "
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
        "## Raw data freshness (`dbt source freshness`)", fresh_md,
        f"## Assertions: dbt tests ({failing} failing, {warned} warnings, {len(tests)} tests)",
        "Generic tests are defined next to each column in `dbt/models/*/_*.yml`; singular tests are "
        "`dbt/tests/*.sql`. Each test's dbt name is in `qa.assertions.dbt_test`; its failing rows are "
        "kept in the `qa_failures` schema (`cd dbt && dbt test --select <dbt_test>` re-runs one).",
        md_table(con, "SELECT test, models, failing_rows, "
                      "CASE result WHEN 'pass' THEN 'pass' WHEN 'warn' THEN 'WARN' ELSE upper(result) END AS result "
                      "FROM qa.assertions"),
    ]
    REPORT.write_text("\n\n".join(parts))
    return failing


def main(db_path=C.DB_PATH):
    db_path = Path(db_path).resolve()
    if not db_path.exists():
        sys.exit(f"{db_path} not found. Run python -m ingest.load first.")
    with duckdb.connect(str(db_path), read_only=True) as con:
        have = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw'").fetchall()}
        has_loaded_at = con.execute(
            "SELECT count(*) FROM information_schema.columns WHERE table_schema = 'raw' "
            "AND column_name = '_loaded_at'").fetchone()[0] > 0
    if RAW_TABLES - have:
        sys.exit(f"Missing raw tables: {sorted(RAW_TABLES - have)}. Fix the download/load errors first.")

    os.environ["HRRP_DB_PATH"] = str(db_path)  # read by dbt/profiles.yml
    freshness = []
    if has_loaded_at:
        print("Checking raw data freshness (dbt source freshness):")
        freshness = freshness_rows(dbt("source", "freshness"))
    print("\nBuilding models and running tests (dbt build):")
    build = dbt("build")
    if build.exception is not None:
        sys.exit(f"dbt could not run: {build.exception}")
    tests = test_rows(build)

    with duckdb.connect(str(db_path)) as con:
        write_assertions(con, tests)
        built = con.execute("SELECT count(*) FROM information_schema.tables "
                            "WHERE table_schema = 'qa' AND table_name = 'join_funnel'").fetchone()[0]
        if not built:
            sys.exit("dbt build did not create qa.join_funnel; see the dbt output above.")
        failed = write_report(con, tests, freshness)
        print("\nJoin funnel:")
        for r in con.execute("SELECT * FROM qa.join_funnel").fetchall():
            print(f"  {r[0]}. {r[1]:58s} {r[2]:>6,}  (dropped {r[3] if r[3] is not None else '-'})")
    print(f"\nTests failing: {failed}. Full report: {REPORT}")
    if not build.success:
        sys.exit(1)


if __name__ == "__main__":
    main()
