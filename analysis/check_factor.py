"""Cross-check: does the tested Python factor recompute agree with the SQL and with CMS?

Run after models.build:   python -m analysis.check_factor
Writes nothing. Prints three comparisons for every hospital in CMS's FY2026
supplemental file and exits with an error if any of them fails:
  1. Python recompute (hrrp.penalty) vs CMS's published factor (published to 4 decimals)
  2. SQL recompute (mart.hospital_paf_recomputed) vs CMS's published factor
  3. Python recompute vs SQL recompute (should agree to floating-point precision)
"""
import sys

import duckdb

from hrrp.penalty import payment_adjustment_factor
from ingest import config as CFG

TOL_CMS = 0.0001   # CMS rounds the factor to 4 decimals
TOL_SQL = 1e-9


def main():
    con = duckdb.connect(str(CFG.DB_PATH), read_only=True)
    cond = con.execute("""
        SELECT ccn, condition, err, peer_median_err, drg_payment_ratio, penalty_indicator, neutrality_modifier
        FROM mart.hospital_condition_penalty_share
    """).df()
    ref = con.execute("""
        SELECT s.ccn, s.payment_adjustment_factor AS paf_cms, r.paf_recomputed AS paf_sql
        FROM stg.hrrp_supplemental s JOIN mart.hospital_paf_recomputed r USING (ccn)
    """).df()
    con.close()

    py = payment_adjustment_factor(cond)[["ccn", "paf_recomputed"]].rename(columns={"paf_recomputed": "paf_py"})
    m = ref.merge(py, on="ccn", how="left")
    checks = {
        "Python vs CMS": (m.paf_py - m.paf_cms).abs() > TOL_CMS,
        "SQL vs CMS": (m.paf_sql - m.paf_cms).abs() > TOL_CMS,
        "Python vs SQL": (m.paf_py - m.paf_sql).abs() > TOL_SQL,
    }
    print(f"Hospitals compared: {len(m):,}")
    missing = int(m[["paf_cms", "paf_sql", "paf_py"]].isna().any(axis=1).sum())
    print(f"  missing a factor: {missing}")
    failed = missing > 0
    for name, bad in checks.items():
        print(f"  {name:<14} mismatches: {int(bad.sum())}")
        failed |= bool(bad.any())
    print(f"  max |Python - CMS| = {(m.paf_py - m.paf_cms).abs().max():.6f}, "
          f"max |Python - SQL| = {(m.paf_py - m.paf_sql).abs().max():.2e}")
    if failed:
        sys.exit("Factor cross-check FAILED; see mismatches above.")
    print("Factor cross-check passed.")


if __name__ == "__main__":
    main()
