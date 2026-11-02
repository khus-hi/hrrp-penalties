"""Step 7: export tidy CSVs for the Tableau Public dashboard.
Run after models.build:   python -m dashboard.export_tableau
Writes dashboard/tableau_exports/*.csv. The build guide is docs/tableau_build_guide.md.

Design rules
- One table per grain, joined in Tableau with relationships on CCN. Nothing is duplicated
  across files, so a SUM in Tableau can't double-count.
- Values are left raw (dollars, ratios). Percentages, peer medians and ranks are Tableau
  calculated fields, so every number on the dashboard can be traced to a formula.
- Hospitals with no dollar estimate stay in the file with estimate_quality saying why,
  so the map and the lookup never silently drop a hospital.
"""
import duckdb

from ingest import config as CFG
from analysis.build_workbook import load as load_workbook_inputs, pick_sec

OUT = CFG.ROOT / "dashboard" / "tableau_exports"

HOSPITALS = """
SELECT
    p.ccn,
    p.facility_name,
    p.facility_name || ' (' || p.state || ', CCN ' || p.ccn || ')'      AS hospital_label,
    gi.city,
    p.state,
    gi.zip5,
    h.county_fips,
    gi.county_name,
    p.hospital_type,
    p.hospital_ownership,
    CASE WHEN p.hospital_ownership LIKE 'Voluntary%'   THEN 'Nonprofit'
         WHEN p.hospital_ownership LIKE 'Government%'  THEN 'Government'
         WHEN p.hospital_ownership LIKE 'Proprietary%' THEN 'For-profit'
         WHEN p.hospital_ownership LIKE 'Physician%'   THEN 'Physician-owned'
         ELSE 'Other / unknown' END                                    AS ownership_group,
    coalesce(p.parent_system, 'Not one of the four chains')            AS parent_system,
    p.beds,
    -- Size bands for the peer comparison. Cut points are a presentation choice (roughly
    -- quartiles of acute hospitals), not a CMS definition.
    CASE WHEN p.beds IS NULL THEN 'Unknown size'
         WHEN p.beds < 100  THEN '1: under 100 beds'
         WHEN p.beds < 200  THEN '2: 100-199 beds'
         WHEN p.beds < 400  THEN '3: 200-399 beds'
         ELSE '4: 400+ beds' END                                       AS bed_size_band,
    CASE WHEN p.is_teaching IS NULL THEN 'Teaching status unknown'
         WHEN p.is_teaching THEN 'Teaching' ELSE 'Non-teaching' END    AS teaching_status,
    p.star_rating,
    h.peer_group                                                       AS cms_dual_peer_group,
    h.dual_proportion,
    h.n_conditions_with_err,
    p.payment_adjustment_factor,
    p.is_penalized,
    p.payment_adjustment_factor <= 0.97                                AS at_3pct_cap,
    p.est_annual_base_drg_payments,
    p.est_penalty_usd,
    p.estimate_quality,
    p.penalty_drivers,
    h.county_median_household_income,
    h.county_share_age_65_plus,
    p.penalty_usd_ami, p.penalty_usd_hf, p.penalty_usd_pn,
    p.penalty_usd_copd, p.penalty_usd_cabg, p.penalty_usd_tha_tka
FROM mart.hospital_penalty_wide p
JOIN mart.hospital h USING (ccn)
LEFT JOIN stg.general_info gi USING (ccn)
ORDER BY p.state, p.facility_name
"""

CONDITIONS = """
SELECT
    s.ccn,
    s.condition_label                       AS condition,
    s.penalty_indicator,                    -- CMS flag: Y = condition counts toward the penalty
    s.err,
    s.peer_median_err,
    s.err - s.peer_median_err               AS err_minus_peer_median,
    s.drg_payment_ratio,
    s.eligible_discharges,
    m.expected_rate,
    m.predicted_rate,
    s.share_of_penalty,
    c.condition_penalty_usd
FROM mart.hospital_condition_penalty_share s
LEFT JOIN mart.hospital_condition_penalty c USING (ccn, condition)
LEFT JOIN stg.hrrp_measures m ON m.ccn = s.ccn AND m.condition = s.condition
ORDER BY s.ccn, s.condition_label
"""


def system_financials(con):
    """Latest 5 fiscal years of 10-K figures per chain, same tag logic as the workbook."""
    _, _, facts = load_workbook_inputs(con)
    sec = pick_sec(facts)
    if sec.empty:
        raise SystemExit("No SEC 10-K facts in the database. Run ingest.download and ingest.load first.")
    # Same rule as the workbook's SEC_Financials!L: reported operating income, else EBIT.
    ebit = sec.pretax_income + sec.interest_expense
    sec["operating_income_used"] = sec.operating_income.where(sec.operating_income.notna(), ebit)
    sec["operating_income_basis"] = sec.operating_income.notna().map(
        {True: "Reported operating income", False: "EBIT (pre-tax income + interest)"})
    sec = sec.rename(columns={"company": "parent_system", "fy": "fiscal_year"})
    return sec[["parent_system", "cik", "fiscal_year", "revenue", "operating_income_used",
                "operating_income_basis", "net_income", "net_income_tag", "filed"]]


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(CFG.DB_PATH), read_only=True)
    outputs = {
        "hospitals.csv": con.execute(HOSPITALS).df(),
        "hospital_conditions.csv": con.execute(CONDITIONS).df(),
        "system_financials.csv": system_financials(con),
    }
    con.close()

    for name, df in outputs.items():
        df.to_csv(OUT / name, index=False)
        print(f"{name:26s} {len(df):>6,} rows  {df.shape[1]} columns")

    h = outputs["hospitals.csv"]
    assert h.ccn.is_unique, "hospitals.csv must have one row per CCN"
    c = outputs["hospital_conditions.csv"]
    assert not c.duplicated(["ccn", "condition"]).any(), "one row per hospital x condition"
    gap = abs(c.condition_penalty_usd.sum() - h.est_penalty_usd.sum())
    print(f"Total estimated penalty: ${h.est_penalty_usd.sum():,.0f}"
          f"  (condition split differs by ${gap:,.0f})")
    print(f"Hospitals with a $ estimate: {h.est_penalty_usd.notna().sum():,} of {len(h):,}")
    print(f"Peer groups (size x teaching): {h.groupby(['bed_size_band', 'teaching_status']).ngroups}")
    print(f"Files in {OUT}")


if __name__ == "__main__":
    main()
