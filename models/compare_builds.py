"""Compare two builds of the pipeline table by table (used to check the dbt migration).

Every table in the stg, int, mart, qa and seed schemas of BEFORE is compared with the
same table in AFTER: row count, columns, and rows that are in one but not the other
(EXCEPT ALL in both directions, so duplicate rows count too). Doubles are compared
after rounding to 6 decimal places (a millionth of a dollar or of a ratio). DuckDB adds
up numbers in parallel, so two runs of the same SQL can differ in the last binary digit
(about $0.00000000001); that noise is not a real difference, anything bigger is.

Run:
    cp data/hrrp.duckdb data/hrrp_before_dbt.duckdb      # copy of the old build
    make build                                            # dbt build into data/hrrp.duckdb
    python -m models.compare_builds data/hrrp_before_dbt.duckdb data/hrrp.duckdb

Exit code 0 = identical, 1 = something differs (each difference is printed).
"""
import sys

import duckdb

SCHEMAS = ("stg", "int", "mart", "qa", "seed")
# qa.assertions is now one row per dbt test (not the old hand-written list), so it is
# expected to differ; it is reported but not counted as a difference.
EXPECTED_TO_DIFFER = {"qa.assertions"}


def tables(con, alias):
    return {f"{s}.{t}" for s, t in con.execute(
        "SELECT schema_name, table_name FROM duckdb_tables() "
        f"WHERE database_name = '{alias}' AND schema_name IN {SCHEMAS}").fetchall()}


def columns(con, alias, table):
    s, t = table.split(".")
    return con.execute(
        "SELECT column_name, data_type FROM duckdb_columns() "
        f"WHERE database_name = '{alias}' AND schema_name = '{s}' AND table_name = '{t}' "
        "ORDER BY column_index").fetchall()


def select_list(cols):
    out = []
    for name, dtype in cols:
        q = f'"{name}"'
        out.append(f"round({q}, 6) AS {q}" if dtype in ("DOUBLE", "FLOAT", "REAL") else q)
    return ", ".join(out)


def main(before, after):
    con = duckdb.connect()
    con.execute(f"ATTACH '{before}' AS b (READ_ONLY)")
    con.execute(f"ATTACH '{after}' AS a (READ_ONLY)")
    tb, ta = tables(con, "b"), tables(con, "a")
    problems = 0
    for t in sorted(tb - ta):
        print(f"MISSING in after: {t}")
        problems += t not in EXPECTED_TO_DIFFER
    for t in sorted(ta - tb):
        print(f"new in after (not in before): {t}")
    for t in sorted(tb & ta):
        cb, ca = columns(con, "b", t), columns(con, "a", t)
        nb = con.execute(f"SELECT count(*) FROM b.{t}").fetchone()[0]
        na = con.execute(f"SELECT count(*) FROM a.{t}").fetchone()[0]
        if cb != ca:
            tag = "expected diff" if t in EXPECTED_TO_DIFFER else "DIFF"
            print(f"{tag} {t}: columns differ\n  before {cb}\n  after  {ca}")
            problems += t not in EXPECTED_TO_DIFFER
            continue
        sel = select_list(cb)
        only_b = con.execute(f"SELECT count(*) FROM (SELECT {sel} FROM b.{t} EXCEPT ALL SELECT {sel} FROM a.{t})").fetchone()[0]
        only_a = con.execute(f"SELECT count(*) FROM (SELECT {sel} FROM a.{t} EXCEPT ALL SELECT {sel} FROM b.{t})").fetchone()[0]
        same = nb == na and only_b == 0 and only_a == 0
        tag = "same" if same else ("expected diff" if t in EXPECTED_TO_DIFFER else "DIFF")
        print(f"{tag:13s} {t:45s} rows {nb:>8,} -> {na:>8,}   only before {only_b:,}  only after {only_a:,}")
        problems += (not same) and t not in EXPECTED_TO_DIFFER

    def headline(alias):
        return con.execute(f"SELECT count(*), sum(est_penalty_usd) FROM {alias}.mart.hospital_penalty").fetchone()
    if "mart.hospital_penalty" in tb & ta:
        (rb, pb), (ra, pa) = headline("b"), headline("a")
        print(f"\nmart.hospital_penalty rows {rb:,} -> {ra:,}; total est. penalty ${pb or 0:,.2f} -> ${pa or 0:,.2f}")
    if "mart.hospital" in tb & ta:
        print("mart.hospital rows " + " -> ".join(
            f"{con.execute(f'SELECT count(*) FROM {x}.mart.hospital').fetchone()[0]:,}" for x in ("b", "a")))
    print(f"\n{problems} unexpected difference(s).")
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
