"""Small, real test data for CI: about 50 hospitals sampled from the full database.

Why this exists: CI runs on every push, and it should never download from CMS, SEC or
Census (slow, rate-limited, and sometimes blocked). So CI builds the models against a
tiny DuckDB made from CSVs checked into tests/fixtures/raw/. Every row in those CSVs is
a real row, copied unchanged from the raw.* tables that `python -m ingest.load` built
from the official files. Nothing is invented or edited; we only choose which rows to keep.

Two commands:

  python -m ingest.fixtures sample   # run on YOUR laptop after a full ingest + load.
                                     # Reads data/hrrp.duckdb, writes tests/fixtures/.
  python -m ingest.fixtures build    # run anywhere (CI does). Turns the CSVs back into
                                     # a DuckDB with the same raw.* tables ingest.load makes.

How hospitals are chosen (so the sample still exercises every join and edge case):
  Maryland (no HRRP factor, waiver), each of the four public chains, Massachusetts,
  Connecticut (Census planning regions), hospitals that drop out of a join (no factor,
  no cost report, no General Info row), one at the 3% cap, unpenalized ones, then a
  random fill. "Random" is a stable hash of the CCN, so re-running gives the same pick.
  Each table is then cut to the rows those hospitals need (their enrollments, owners,
  ZIPs and counties; SEC facts only for the XBRL tags and recent years the workbook uses).
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from ingest import config as C

FIXTURES = C.ROOT / "tests" / "fixtures"
RAW_DIR = FIXTURES / "raw"
SAMPLE_FILE = FIXTURES / "sample_ccns.csv"
PROVENANCE = FIXTURES / "provenance.json"
MAX_BYTES = 1_000_000  # keep the checked-in fixtures under 1 MB
DEFAULT_FIXTURE_DB = C.ROOT / "data" / "fixture.duckdb"
CHAINS = ["HCA Healthcare", "Tenet Healthcare", "Community Health Systems", "Universal Health Services"]
SEC_YEARS = 4  # the workbook uses the last 3 fiscal years; one more for safety
PANEL_HOSPITALS = 30  # hospitals kept for every year of the FY2016-FY2027 panel tables

# Same rules as models/staging/00_macros.sql, as TEMP macros so nothing is written to
# your real database (it is attached read-only).
MACROS = r"""
CREATE OR REPLACE TEMP MACRO fx_ccn(x) AS
    CASE WHEN regexp_matches(trim(x), '^[0-9A-Za-z]{1,6}$') THEN lpad(upper(trim(x)), 6, '0') END;
CREATE OR REPLACE TEMP MACRO fx_num(x) AS
    TRY_CAST(replace(replace(replace(trim(x), ',', ''), '%', ''), '$', '') AS DOUBLE);
CREATE OR REPLACE TEMP MACRO fx_county(x) AS
    regexp_replace(
        regexp_replace(
            regexp_replace(upper(trim(x)), '\bST\.?\s', 'SAINT ', 'g'),
            '\s(COUNTY|PARISH|BOROUGH|CENSUS AREA|CITY AND BOROUGH|MUNICIPALITY|MUNICIPIO|PLANNING REGION)$', ''),
        '[^A-Z0-9]', '', 'g');
"""


# ----------------------------------------------------------------------------- sample
def _tables(con) -> set[str]:
    return {r[0] for r in con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_catalog = 'src' AND table_schema = 'raw'").fetchall()}


def pick_hospitals(con, n: int) -> list[tuple[str, str]]:
    """Return [(ccn, reason)] in a stable order."""
    con.execute(f"""
        CREATE TEMP TABLE universe AS
        SELECT DISTINCT fx_ccn(facility_id) AS ccn, state FROM src.raw.hrrp_hospital
        WHERE fx_ccn(facility_id) IS NOT NULL;
        CREATE TEMP TABLE supp AS
        SELECT fx_ccn(ccn) AS ccn, fx_num(payment_adjustment_factor) AS factor
        FROM src.raw.hrrp_supplemental WHERE fx_ccn(ccn) IS NOT NULL;
        CREATE TEMP TABLE patterns AS
        SELECT * FROM read_csv('{C.ROOT / "seeds" / "system_owner_patterns.csv"}', all_varchar = true);
        CREATE TEMP TABLE chain_ccn AS
        SELECT DISTINCT fx_ccn(t.c) AS ccn, p.system
        FROM src.raw.hospital_enrollments e, unnest(string_split(e.ccn, '|')) AS t(c),
             src.raw.hospital_all_owners o, patterns p
        WHERE o.enrollment_id = e.enrollment_id
          AND upper(trim(o.organization_name_owner)) ILIKE p.owner_name_pattern;
    """)
    groups = [("maryland_exempt", 3, "SELECT ccn FROM universe WHERE state = 'MD'")]
    groups += [(f"chain: {s}", 3, f"SELECT ccn FROM chain_ccn WHERE system = '{s}'") for s in CHAINS]
    groups += [
        ("massachusetts", 3, "SELECT ccn FROM universe WHERE state = 'MA'"),
        ("connecticut_planning_region", 2, "SELECT ccn FROM universe WHERE state = 'CT'"),
        ("no_payment_factor", 2,
         "SELECT ccn FROM universe WHERE state <> 'MD' AND ccn NOT IN (SELECT ccn FROM supp)"),
        ("no_cost_report", 2, "SELECT ccn FROM universe WHERE ccn NOT IN "
         "(SELECT fx_ccn(provider_ccn) FROM src.raw.hospital_cost_report WHERE fx_ccn(provider_ccn) IS NOT NULL)"),
        ("no_general_info", 1, "SELECT ccn FROM universe WHERE ccn NOT IN "
         "(SELECT fx_ccn(facility_id) FROM src.raw.hospital_general_info WHERE fx_ccn(facility_id) IS NOT NULL)"),
        ("at_3pct_cap", 1, "SELECT ccn FROM supp WHERE factor <= 0.9700001"),
        ("not_penalized", 3, "SELECT ccn FROM supp WHERE factor = 1"),
    ]
    picked: dict[str, str] = {}
    for reason, k, sql in groups:
        rows = con.execute(f"SELECT DISTINCT ccn FROM ({sql}) WHERE ccn IN (SELECT ccn FROM universe) "
                           "ORDER BY md5(ccn)").fetchall()
        new = [r[0] for r in rows if r[0] not in picked][:k]
        if len(new) < k:
            print(f"  note: only {len(new)} hospital(s) for '{reason}' (wanted {k})")
        picked.update({c: reason for c in new})
    for (c,) in con.execute("SELECT ccn FROM universe ORDER BY md5(ccn)").fetchall():
        if len(picked) >= n:
            break
        picked.setdefault(c, "random")
    return list(picked.items())


def table_filters(con, have: set[str]) -> dict[str, str]:
    """SQL that selects the rows each raw table needs for the sampled hospitals."""
    from analysis.build_workbook import TAGS  # the XBRL tags the workbook reads
    tags = ", ".join(f"'{t}'" for ts in TAGS.values() for t in ts)
    f = {
        "hrrp_hospital": "SELECT * FROM src.raw.hrrp_hospital WHERE fx_ccn(facility_id) IN (SELECT ccn FROM s)",
        "hospital_general_info":
            "SELECT * FROM src.raw.hospital_general_info WHERE fx_ccn(facility_id) IN (SELECT ccn FROM s)",
        "hrrp_supplemental": "SELECT * FROM src.raw.hrrp_supplemental WHERE fx_ccn(ccn) IN (SELECT ccn FROM s)",
        "hrrp_table15": "SELECT * FROM src.raw.hrrp_table15 WHERE fx_ccn(ccn) IN (SELECT ccn FROM s)",
        "hospital_cost_report":
            "SELECT * FROM src.raw.hospital_cost_report WHERE fx_ccn(provider_ccn) IN (SELECT ccn FROM s)",
        "hospital_enrollments": "SELECT * FROM src.raw.hospital_enrollments WHERE enrollment_id IN (SELECT id FROM enr)",
        "hospital_all_owners": "SELECT * FROM src.raw.hospital_all_owners WHERE enrollment_id IN (SELECT id FROM enr)",
        "zcta_county_rel": "SELECT * FROM src.raw.zcta_county_rel WHERE geoid_zcta5_20 IN (SELECT zip5 FROM geo)",
        "acs_county": """
            SELECT a.* FROM src.raw.acs_county a
            WHERE (a.state, fx_county(split_part(a."name", ',', 1))) IN (SELECT state_fips, county_key FROM geo)
               OR a.state || a.county IN (
                    SELECT geoid_county_20 FROM src.raw.zcta_county_rel
                    WHERE geoid_zcta5_20 IN (SELECT zip5 FROM geo))""",
        "sec_facts": f"""
            SELECT * FROM src.raw.sec_facts
            WHERE taxonomy = 'us-gaap' AND unit = 'USD' AND form IN ('10-K', '10-K/A') AND tag IN ({tags})
              AND TRY_CAST(fy AS INT) > (SELECT max(TRY_CAST(fy AS INT)) FROM src.raw.sec_facts) - {SEC_YEARS}""",
        "column_mapping_log": "SELECT * FROM src.raw.column_mapping_log",
    }
    # Multi-year panel: every year of a smaller subset of the sampled hospitals (12 years
    # of 50 hospitals would push the fixtures past 1 MB). Program years and file status
    # are tiny and kept whole.
    f["hrrp_supplemental_history"] = ("SELECT * FROM src.raw.hrrp_supplemental_history "
                                      "WHERE fx_ccn(source_ccn) IN (SELECT ccn FROM panel_s)")
    if "hrrp_hospital_history" in have:
        cols = {r[0] for r in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_catalog = 'src' "
            "AND table_schema = 'raw' AND table_name = 'hrrp_hospital_history'").fetchall()}
        ccn_cols = [c for c in ("facility_id", "provider_number", "provider_id", "ccn", "hospital_ccn") if c in cols]
        f["hrrp_hospital_history"] = (f"SELECT * FROM src.raw.hrrp_hospital_history WHERE fx_ccn(coalesce("
                                      f"{', '.join(ccn_cols)})) IN (SELECT ccn FROM panel_s)")
    f["hrrp_history_files"] = "SELECT * FROM src.raw.hrrp_history_files"
    f["hrrp_program_years"] = "SELECT * FROM src.raw.hrrp_program_years"
    # The untouched IPPS sheets: find their CCN column from the mapping log.
    from ingest.load import norm
    for source in ("hrrp_supplemental", "hrrp_table15"):
        orig = f"{source}_original"
        hit = con.execute("SELECT matched_column FROM src.raw.column_mapping_log "
                          "WHERE source = ? AND field = 'ccn'", [source]).fetchone()
        if orig in have and hit and hit[0]:
            f[orig] = f'SELECT * FROM src.raw.{orig} WHERE fx_ccn("{norm(hit[0])}") IN (SELECT ccn FROM s)'
    return f


def sample(db: Path, n: int, max_bytes: int) -> None:
    if not db.exists():
        sys.exit(f"{db} not found. Run the full pipeline first: python -m ingest.download && python -m ingest.load")
    con = duckdb.connect()
    con.execute(f"ATTACH '{db}' AS src (READ_ONLY)")
    con.execute(MACROS)
    have = _tables(con)

    picks = pick_hospitals(con, n)
    con.execute("CREATE TEMP TABLE s (ccn VARCHAR, reason VARCHAR)")
    con.executemany("INSERT INTO s VALUES (?, ?)", picks)
    con.execute(f"""
        CREATE TEMP TABLE enr AS
        SELECT DISTINCT e.enrollment_id AS id
        FROM src.raw.hospital_enrollments e, unnest(string_split(e.ccn, '|')) AS t(c)
        WHERE fx_ccn(t.c) IN (SELECT ccn FROM s);
        CREATE TEMP TABLE states AS
        SELECT * FROM read_csv('{C.ROOT / "seeds" / "state_fips.csv"}', all_varchar = true);
        CREATE TEMP TABLE geo AS
        SELECT lpad(left(trim(g.zip_code), 5), 5, '0') AS zip5, st.state_fips, fx_county(g.countyparish) AS county_key
        FROM src.raw.hospital_general_info g LEFT JOIN states st ON st.state_abbr = g.state
        WHERE fx_ccn(g.facility_id) IN (SELECT ccn FROM s);
    """)

    # The panel tables keep PANEL_HOSPITALS of the sample (stable md5 order).
    con.execute(f"CREATE TEMP TABLE panel_s AS SELECT ccn FROM s ORDER BY md5(ccn) LIMIT {PANEL_HOSPITALS}")
    filters = table_filters(con, have)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for old in RAW_DIR.glob("*.csv"):
        old.unlink()
    counts, total = {}, 0
    for table in sorted(have):
        if table not in filters:
            print(f"  skip raw.{table}: no sampling rule (add one in ingest/fixtures.py if a model reads it)")
            continue
        out = RAW_DIR / f"{table}.csv"
        # DuckDB writes NULL as an empty field and '' as "", so both survive the round trip.
        con.execute(f"COPY ({filters[table]}) TO '{out}' (HEADER, DELIMITER ',')")
        counts[table] = con.execute(f"SELECT count(*) FROM ({filters[table]})").fetchone()[0]
        total += out.stat().st_size
        print(f"  {str(out.relative_to(C.ROOT)):55s} {counts[table]:>6,} rows  {out.stat().st_size / 1024:7.1f} KB")
    con.execute(f"COPY (SELECT * FROM s ORDER BY reason, ccn) TO '{SAMPLE_FILE}' (HEADER)")

    manifest_path = C.RAW / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    PROVENANCE.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generated_by": "python -m ingest.fixtures sample",
        "hospitals": len(picks),
        "rows": counts,
        "total_bytes": total,
        "source_files": {k: {f: v.get(f) for f in ("url", "sha256", "downloaded_at")}
                         for k, v in sorted(manifest.items())},
    }, indent=2) + "\n")
    print(f"\n{len(picks)} hospitals, {total / 1024:.0f} KB of CSV in {RAW_DIR.relative_to(C.ROOT)}/")
    if total > max_bytes:
        sys.exit(f"Fixtures are {total:,} bytes, over the {max_bytes:,} limit. Re-run with a smaller --n.")


# ------------------------------------------------------------------------------ build
def build(db: Path) -> None:
    csvs = sorted(RAW_DIR.glob("*.csv"))
    if not csvs:
        sys.exit(f"No fixture CSVs in {RAW_DIR.relative_to(C.ROOT)}/. Create them on a machine with the full "
                 "data: python -m ingest.fixtures sample  (see tests/fixtures/README.md)")
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = duckdb.connect(str(db))
    con.execute("CREATE SCHEMA raw; CREATE SCHEMA seed;")
    for p in csvs:
        # all_varchar: raw tables are text, exactly like ingest.load makes them.
        # allow_quoted_nulls=false keeps "" as an empty string and an empty field as NULL.
        con.execute(f"CREATE TABLE raw.{p.stem} AS SELECT * FROM read_csv('{p}', header = true, "
                    "all_varchar = true, delim = ',', quote = '\"', escape = '\"', allow_quoted_nulls = false)")
        rows = con.execute(f"SELECT count(*) FROM raw.{p.stem}").fetchone()[0]
        print(f"  raw.{p.stem:40s} {rows:>6,} rows")
    if not (C.ROOT / "dbt" / "dbt_project.yml").exists():
        # Before dbt, ingest.load put the seeds/ CSVs in the seed schema; once dbt exists,
        # `dbt seed` (part of `dbt build`) does that instead.
        for seed in sorted((C.ROOT / "seeds").glob("*.csv")):
            con.execute(f"CREATE TABLE seed.{seed.stem} AS SELECT * FROM read_csv('{seed}', all_varchar = true)")
    con.close()
    print(f"Fixture database: {db}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample", help="cut tests/fixtures/ from the full data/hrrp.duckdb")
    s.add_argument("--db", type=Path, default=C.ROOT / "data" / "hrrp.duckdb")
    s.add_argument("--n", type=int, default=50, help="number of hospitals (default 50)")
    s.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    b = sub.add_parser("build", help="turn tests/fixtures/raw/*.csv into a DuckDB file")
    b.add_argument("--db", type=Path, default=Path(os.getenv("HRRP_DB_PATH", DEFAULT_FIXTURE_DB)))
    args = ap.parse_args()
    if args.cmd == "sample":
        sample(args.db, args.n, args.max_bytes)
    else:
        build(args.db)


if __name__ == "__main__":
    main()
