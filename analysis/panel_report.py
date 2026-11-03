"""Step 5: describe the FY2016-FY2027 HRRP panel (docs/panel_report.md).

Run after models.build:   python -m analysis.panel_report     (or: make panel)

What it answers, from mart.fct_hospital_condition_year and the qa.panel_* tables:
  * which payment years we have, which are missing and why;
  * hospitals per year, and how many appear in every loaded year;
  * attrition: hospitals that leave or join the program from one year to the next,
    and how many of the first year's hospitals are still there each later year;
  * the known breaks (COVID-19 2020 exclusion, FY2023 pneumonia suppression, ...).

Every number comes from the database; nothing is typed in. A "hospital in year Y"
means a CCN in that year's IPPS supplemental file (the hospitals CMS scored for the
payment adjustment). CCNs change when hospitals merge or re-certify, so "attrition" is
CCN attrition: a hospital that got a new CCN shows up as one exit plus one entry.
"""
import argparse
import sys
from datetime import datetime, timezone

import duckdb

from ingest import config as C
from models.build import md_table

REPORT = C.ROOT / "docs" / "panel_report.md"
PANEL = "mart.fct_hospital_condition_year"
FIXTURE_MAX_HOSPITALS = 500  # the CI fixture has ~50; the real program has ~3,000 a year


def build(con) -> str:
    years = [r[0] for r in con.execute(
        f"SELECT DISTINCT fiscal_year FROM {PANEL} WHERE in_supplemental ORDER BY 1").fetchall()]
    expected = sorted(C.HRRP_YEARS)
    missing = [y for y in expected if y not in years]
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE hy AS
        SELECT DISTINCT ccn, fiscal_year FROM {PANEL} WHERE in_supplemental
    """)
    n_years = len(years)
    in_all = con.execute(f"""
        SELECT count(*) FROM (SELECT ccn FROM hy GROUP BY ccn HAVING count(*) = {n_years})
    """).fetchone()[0] if years else 0
    ever = con.execute("SELECT count(DISTINCT ccn) FROM hy").fetchone()[0]

    out = [
        "# HRRP panel, FY2016-FY2027: coverage and attrition",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.panel_report` "
        f"from `{PANEL}`. Do not edit by hand._",
        "",
        "## Years",
        "",
        f"CMS payment years expected: FY{expected[0]}-FY{expected[-1]} ({len(expected)}). "
        f"Loaded: {n_years}" + (f" ({', '.join(f'FY{y}' for y in years)})." if years else "."),
        "",
        ("**Missing:** " + ", ".join(f"FY{y}" for y in missing) +
         ". Reasons are in the table below (`supplemental_note`) and in "
         "`data/raw/hrrp_history/missing_years.json`. Missing years are left out, never filled in.")
        if missing else "No year is missing.",
        "",
        md_table(con, """
            SELECT fiscal_year AS fy, supplemental_status AS status, hospitals,
                   hospitals_with_any_err AS with_any_err, conditions, condition_list,
                   config_period_start AS period_start, config_period_end AS period_end,
                   period_checked, file_period_start, file_period_end, supplemental_note
            FROM qa.panel_year_coverage ORDER BY fiscal_year"""),
        "`period_checked`: `file` = dates printed in CMS's Provider Data Catalog file, `cms` = quoted from a "
        "CMS/QualityNet document (link in `ingest/config.py`), `rule` = the standard 3-year window, not yet "
        "confirmed (the test `assert_panel_period_matches_file` confirms it once that year's archived "
        "Provider Data Catalog file is loaded).",
        "",
        "## Hospitals in every year",
        "",
        f"- Distinct hospitals (CCNs) in any loaded year: **{ever:,}**",
        f"- In every one of the {n_years} loaded years: **{in_all:,}**",
    ]
    if missing:
        out.append(f"- In all {len(expected)} expected years: not computable, because "
                   f"{len(missing)} year(s) are missing.")
    out += ["", "## Attrition", "",
            "Year over year: `stayed` = in both years, `left` = in the earlier year only, "
            "`joined` = in the later year only. Gaps in the years are shown as they are.", ""]
    if n_years >= 2:
        out.append(md_table(con, """
            WITH y AS (SELECT fiscal_year, lag(fiscal_year) OVER (ORDER BY fiscal_year) AS prev
                       FROM (SELECT DISTINCT fiscal_year FROM hy))
            SELECT y.prev || ' -> ' || y.fiscal_year AS years,
                   (SELECT count(*) FROM hy a WHERE a.fiscal_year = y.prev)        AS hospitals_before,
                   (SELECT count(*) FROM hy a JOIN hy b USING (ccn)
                     WHERE a.fiscal_year = y.prev AND b.fiscal_year = y.fiscal_year) AS stayed,
                   (SELECT count(*) FROM hy a WHERE a.fiscal_year = y.prev
                      AND a.ccn NOT IN (SELECT ccn FROM hy WHERE fiscal_year = y.fiscal_year)) AS "left",
                   (SELECT count(*) FROM hy b WHERE b.fiscal_year = y.fiscal_year
                      AND b.ccn NOT IN (SELECT ccn FROM hy WHERE fiscal_year = y.prev)) AS joined,
                   (SELECT count(*) FROM hy a WHERE a.fiscal_year = y.fiscal_year)  AS hospitals_after
            FROM y WHERE y.prev IS NOT NULL ORDER BY y.fiscal_year"""))
        first = years[0]
        out += ["", f"Of the hospitals in FY{first}, how many are still in each later year:", "",
                md_table(con, f"""
            SELECT b.fiscal_year AS fy, count(*) AS still_in,
                   round(100.0 * count(*) / (SELECT count(*) FROM hy WHERE fiscal_year = {first}), 1) AS pct_of_fy{first}
            FROM hy a JOIN hy b USING (ccn)
            WHERE a.fiscal_year = {first} GROUP BY 1 ORDER BY 1""")]
    else:
        out.append("_Needs at least two loaded years._")
    out += ["", "## Measures by year", "",
            "`looks_suppressed` = the condition has ERRs but CMS never marked it 'Y' for a penalty.", "",
            md_table(con, """
            SELECT fiscal_year AS fy, condition, hospital_rows, with_err, cms_indicator_y, penalized,
                   median_err, suppressed_per_cms, looks_suppressed
            FROM qa.panel_measure_coverage ORDER BY 1, 2"""),
            "", "## Known breaks in the series", "",
            "From `seeds/hrrp_known_breaks.csv`; each row links the CMS page that announced it. Rows they "
            "touch carry `covid_2020_excluded`, `measure_suppressed` and `break_notes` in the panel.", "",
            md_table(con, """
            SELECT fiscal_year AS fy, coalesce(nullif(condition, ''), 'all') AS condition, break_type,
                   description, source_url
            FROM seed.hrrp_known_breaks ORDER BY 1, 2"""),
            "", "## How to read the panel", "",
            "- Before FY2019 a condition was penalized when ERR > 1; from FY2019 when ERR > the median of the "
            "hospital's dual-proportion peer group. `penalized_source` says which rule each row used.",
            "- FY2022-FY2024 leave out January-June 2020, and FY2022's period stops at December 1, 2019. "
            "Trends across FY2021-FY2025 mix periods with and without that half-year.",
            "- FY2023 pneumonia ERRs are kept but did not count toward payment (`measure_suppressed`).",
            "- FY2027 measures 2 years of discharges instead of 3, so its ERRs rest on fewer cases.",
            ""]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPORT), help="where to write the report")
    args = ap.parse_args()
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    biggest = con.execute(f"SELECT max(n) FROM (SELECT count(DISTINCT ccn) AS n FROM {PANEL} "
                          "GROUP BY fiscal_year)").fetchone()[0] or 0
    if biggest < FIXTURE_MAX_HOSPITALS and args.out == str(REPORT):
        sys.exit(f"{C.DB_PATH} has at most {biggest} hospitals in a year: that's the CI fixture, not the real "
                 "data. Not overwriting docs/panel_report.md (pass --out somewhere else to test).")
    text = build(con)
    with open(args.out, "w") as f:
        f.write(text)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
