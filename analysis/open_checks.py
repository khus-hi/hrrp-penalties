"""Step 8: two sanity checks on the pipeline's coverage.
Run after models.build:   python -m analysis.open_checks
Writes docs/open_checks_report.md.

A. Chain hospital counts. How many hospitals the CMS ownership match assigns to each chain,
   next to the count each company reports in its FY2025 10-K. The two will never match
   exactly (10-Ks count psychiatric, rehab and UK hospitals that HRRP doesn't cover), so the
   report breaks the gap into parts and lists owner names the match might be missing.
B. Hospitals with no FY2026 payment factor outside Maryland. Each one is classified by what
   the CMS files say about it (provider type from the CCN, whether it is still in Hospital
   General Information, CMS footnotes, case counts, cost report dates).
"""
from datetime import datetime, timezone

import duckdb

from ingest import config as CFG
from models.build import md_table

OUT = CFG.ROOT / "docs" / "open_checks_report.md"

# Hospital counts stated in each company's FY2025 10-K (Item 1, Business), read 2026-11-02.
TEN_K = [
    ("HCA Healthcare", 190, 179, "190 hospitals: 179 general acute care (includes England), 7 behavioral, 4 rehabilitation; 19 states and England",
     "https://www.sec.gov/Archives/edgar/data/860730/000119312526044769/hca-20251231.htm"),
    ("Tenet Healthcare", 50, 50, "50 acute care and specialty hospitals (Hospital Operations); USPI also holds interests in 26 surgical hospitals",
     "https://www.sec.gov/Archives/edgar/data/70318/000007031826000012/"),
    ("Community Health Systems", 69, 69, "69 affiliated hospitals, 10,458 licensed beds, 14 states",
     "https://www.sec.gov/Archives/edgar/data/1108109/000119312526059509/cyh-20251231.htm"),
    ("Universal Health Services", 29, 29, "29 U.S. inpatient acute care hospitals (plus 182 U.S. and 161 U.K. behavioral facilities), as of 2026-02-25",
     "https://www.sec.gov/Archives/edgar/data/352915/000119312526071676/uhs-20251231.htm"),
]

# Short-term acute hospitals (the ones HRRP covers) have CCN digits 3-6 in 0001-0879.
CCN_TYPE = """
CASE
    WHEN NOT regexp_matches(substr(ccn, 3, 4), '^[0-9]{4}$') THEN 'Non-numeric CCN suffix'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 1    AND 879  THEN 'Short-term acute (0001-0879)'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 1300 AND 1399 THEN 'Critical access (1300-1399)'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 2000 AND 2299 THEN 'Long-term care (2000-2299)'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 3025 AND 3099 THEN 'Rehabilitation (3025-3099)'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 3300 AND 3399 THEN 'Children''s (3300-3399)'
    WHEN substr(ccn, 3, 4)::INT BETWEEN 4000 AND 4499 THEN 'Psychiatric (4000-4499)'
    ELSE 'Other CCN range'
END
"""

SETUP = f"""
CREATE OR REPLACE TEMP TABLE ten_k(parent_system VARCHAR, tenk_total INT, tenk_acute INT, tenk_text VARCHAR, url VARCHAR);
INSERT INTO ten_k VALUES {", ".join("(" + ", ".join(repr(v) if isinstance(v, str) else str(v) for v in row) + ")" for row in TEN_K)};

CREATE OR REPLACE TEMP TABLE chain_hosp AS
SELECT h.ccn, h.facility_name, h.state, h.parent_system, h.hospital_type,
       h.payment_adjustment_factor IS NOT NULL AS has_factor,
       h.parent_max_pct_ownership,
       s.matched_owner_names,
       {CCN_TYPE} AS ccn_type
FROM mart.hospital h
JOIN int.hospital_system s USING (ccn)
WHERE h.parent_system IS NOT NULL;

CREATE OR REPLACE TEMP TABLE no_factor AS
WITH fn AS (
    SELECT ccn, string_agg(DISTINCT footnote, ', ') AS cms_footnotes,
           sum(discharges) AS hrrp_discharges, count(err) AS conditions_with_err
    FROM stg.hrrp_measures GROUP BY ccn
)
SELECT h.ccn, h.facility_name, h.state,
       {CCN_TYPE} AS ccn_type,
       gi.ccn IS NOT NULL                        AS in_general_info,
       gi.hospital_type                          AS gi_hospital_type,
       sup.ccn IS NOT NULL                       AS in_supplemental_file,
       h.payment_adjustment_factor_table15 IS NOT NULL AS in_table15,
       fn.conditions_with_err, fn.hrrp_discharges, fn.cms_footnotes,
       h.cr_fy_end                               AS latest_cost_report_end,
       CASE
           WHEN {CCN_TYPE} <> 'Short-term acute (0001-0879)' THEN 'A. Not a short-term acute (IPPS) hospital'
           WHEN gi.ccn IS NULL                   THEN 'B. No longer in Hospital General Information (likely closed or merged)'
           WHEN h.cr_fy_end < DATE '2023-07-01'  THEN 'C. No cost report since mid-2023 (likely closed or converted)'
           WHEN coalesce(fn.conditions_with_err, 0) = 0 THEN 'D. No condition with an ERR in the HRRP file'
           ELSE 'E. Open acute hospital with ERRs but no factor: unexplained'
       END                                       AS likely_reason
FROM mart.hospital h
LEFT JOIN stg.general_info gi USING (ccn)
LEFT JOIN stg.hrrp_supplemental sup USING (ccn)
LEFT JOIN fn USING (ccn)
WHERE h.payment_adjustment_factor IS NULL AND h.state <> 'MD';
"""

# Owner names that look like one of the chains but aren't matched by seeds/system_owner_patterns.csv.
NEAR_MISS = """
WITH kw(chain, pat) AS (VALUES
    ('HCA', '%HCA%'), ('HCA', '%HEALTHTRUST%'),
    ('Tenet', '%TENET%'), ('Tenet', '%USPI%'), ('Tenet', '%UNITED SURGICAL PARTNERS%'), ('Tenet', '%CONIFER%'),
    ('CHS', '%COMMUNITY HEALTH SYSTEM%'), ('CHS', '%CHSPSC%'), ('CHS', 'CHS %'), ('CHS', '%TRIAD HOSPITALS%'),
    ('UHS', '%UNIVERSAL HEALTH%'), ('UHS', 'UHS %'), ('UHS', '%UHS OF %')
)
SELECT kw.chain AS looks_like, o.owner_org_name,
       count(DISTINCT e.ccn) AS hrrp_hospitals,
       count(DISTINCT e.ccn) FILTER (WHERE h.parent_system IS NULL) AS of_which_unmapped
FROM stg.owners o
JOIN kw ON o.owner_org_name ILIKE kw.pat
JOIN stg.enrollment_ccn e USING (enrollment_id)
JOIN mart.hospital h ON h.ccn = e.ccn
WHERE NOT EXISTS (SELECT 1 FROM seed.system_owner_patterns p WHERE o.owner_org_name ILIKE p.owner_name_pattern)
GROUP BY ALL
ORDER BY looks_like, of_which_unmapped DESC, hrrp_hospitals DESC
"""


def main():
    con = duckdb.connect(str(CFG.DB_PATH), read_only=True)
    con.execute(SETUP)

    summary = """
        SELECT t.parent_system,
               count(c.ccn)                                              AS mapped_in_hrrp_file,
               count(c.ccn) FILTER (WHERE c.has_factor)                  AS with_fy2026_factor,
               count(c.ccn) FILTER (WHERE c.parent_max_pct_ownership < 100) AS partial_ownership_lt_100pct,
               t.tenk_acute                                              AS tenk_acute_or_comparable,
               count(c.ccn) - t.tenk_acute                               AS gap_vs_10k,
               t.tenk_text
        FROM ten_k t LEFT JOIN chain_hosp c USING (parent_system)
        GROUP BY t.parent_system, t.tenk_acute, t.tenk_text ORDER BY 1"""
    parts = [
        f"# Open checks\n\n_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC} by `python -m analysis.open_checks`._\n",
        "## A. Chain hospital counts vs FY2025 10-K\n",
        "Our count is hospitals in the CMS FY2026 HRRP file whose CMS ownership record names the chain. "
        "The 10-K count is what the company says it operates. Reasons they differ: HRRP only covers short-term "
        "acute hospitals paid under IPPS (no psychiatric, rehab, UK or critical-access hospitals); two hospitals on "
        "one campus can share a CCN; the HRRP file reflects hospitals with discharges in 07/2021-06/2024, so "
        "hospitals sold since then can still be there and new ones can be missing; and CMS ownership records lag "
        "sales.\n",
        md_table(con, summary),
        "\nSources: " + "; ".join(f"[{n} 10-K]({u})" for n, *_, u in TEN_K) + "\n",
        "### Mapped hospitals by CCN type and state\n",
        md_table(con, """SELECT parent_system, ccn_type, count(*) AS hospitals,
                                string_agg(DISTINCT state, ', ' ORDER BY state) AS states
                         FROM chain_hosp GROUP BY ALL ORDER BY 1, 3 DESC"""),
        "### Owner names that look like a chain but are not in the match patterns\n",
        "If `of_which_unmapped` is large for a real subsidiary, add its name to `seeds/system_owner_patterns.csv` "
        "and rebuild. Check each name first: a keyword like `CHS` can match unrelated companies.\n",
        md_table(con, NEAR_MISS),
        "### Every mapped hospital\n",
        md_table(con, """SELECT parent_system, ccn, facility_name, state, ccn_type, has_factor,
                                parent_max_pct_ownership AS max_pct_owned, matched_owner_names
                         FROM chain_hosp ORDER BY 1, state, facility_name"""),
        "\n## B. Hospitals outside Maryland with no FY2026 payment factor\n",
        "Classified in order: the first rule that applies wins.\n",
        md_table(con, "SELECT likely_reason, count(*) AS hospitals FROM no_factor GROUP BY 1 ORDER BY 1"),
        "### By CCN type\n",
        md_table(con, "SELECT ccn_type, count(*) AS hospitals FROM no_factor GROUP BY 1 ORDER BY 2 DESC"),
        "### CMS footnotes on these hospitals' HRRP rows\n",
        "Look up each code in the CMS Provider Data Catalog footnote crosswalk before quoting what it means.\n",
        md_table(con, "SELECT coalesce(cms_footnotes, '(none)') AS cms_footnotes, count(*) AS hospitals "
                      "FROM no_factor GROUP BY 1 ORDER BY 2 DESC"),
        "### Every hospital\n",
        md_table(con, """SELECT likely_reason, ccn, facility_name, state, ccn_type, in_general_info, gi_hospital_type,
                                in_supplemental_file, in_table15, conditions_with_err, hrrp_discharges,
                                cms_footnotes, latest_cost_report_end
                         FROM no_factor ORDER BY likely_reason, state, facility_name"""),
    ]
    n = con.execute("SELECT count(*) FROM no_factor").fetchone()[0]
    print(con.execute(summary).df().drop(columns="tenk_text").to_string(index=False))
    print()
    print(f"No factor outside MD: {n}")
    print(con.execute("SELECT likely_reason, count(*) n FROM no_factor GROUP BY 1 ORDER BY 1").df().to_string(index=False))
    con.close()
    OUT.write_text("\n".join(parts))
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
