"""Runs the real staging and mart SQL on three hand-built hospitals and checks the
42 CFR 412.152 arithmetic:

    factor = max(0.97, 1 - NM * sum_c[ DRG ratio_c * max(ERR_c - peer median_c, 0) ])

where a condition counts only when CMS's penalty indicator is "Y".
"""
import pytest

from tests.conftest import run_sql_file

CONDS = ["ami", "hf", "pn", "copd", "cabg", "tha_tka"]
NM = 0.95

# ccn -> {condition: (err, peer_median, drg_ratio, indicator)}; unlisted = below median
HOSPITALS = {
    # A: two conditions above the median.
    #    excess = 0.05*(1.10-1.00) + 0.04*(1.05-1.02) = 0.005 + 0.0012 = 0.0062
    #    factor = 1 - 0.95*0.0062 = 0.99411
    "10001": {"hf": (1.10, 1.00, 0.05, "Y"), "pn": (1.05, 1.02, 0.04, "Y")},
    # B: so far above the median that the 3% cap binds -> 0.97
    "10002": {"ami": (2.00, 1.00, 0.10, "Y")},
    # C: above the median but CMS says the condition doesn't count (too few cases) -> 1.0
    "10003": {"hf": (1.20, 1.00, 0.05, "N")},
}
EXPECTED_FACTOR = {"010001": 1 - NM * 0.0062, "010002": 0.97, "010003": 1.0}
BASE_DRG = 10_000_000.0  # full-year cost report


@pytest.fixture
def mart(con):
    cols = ["ccn", "payment_adjustment_factor", "payment_reduction_pct", "dual_proportion",
            "peer_group", "neutrality_modifier"]
    for c in CONDS:
        cols += [f"err_{c}", f"peer_median_err_{c}", f"eligible_discharges_{c}",
                 f"drg_payment_ratio_{c}", f"penalty_indicator_{c}"]
    con.execute(f"CREATE TABLE raw.hrrp_supplemental ({', '.join(c + ' VARCHAR' for c in cols)})")
    con.execute("CREATE TABLE raw.hrrp_table15 (ccn VARCHAR, payment_adjustment_factor VARCHAR)")
    for ccn, conds in HOSPITALS.items():
        row = {"ccn": ccn, "payment_adjustment_factor": f"{EXPECTED_FACTOR['0' + ccn]:.4f}",
               "payment_reduction_pct": None, "dual_proportion": "0.2", "peer_group": "3",
               "neutrality_modifier": str(NM)}
        for c in CONDS:
            err, med, ratio, ind = conds.get(c, (0.95, 1.00, 0.03, "Y"))
            row |= {f"err_{c}": str(err), f"peer_median_err_{c}": str(med),
                    f"eligible_discharges_{c}": "100", f"drg_payment_ratio_{c}": str(ratio),
                    f"penalty_indicator_{c}": ind}
        con.execute(f"INSERT INTO raw.hrrp_supplemental VALUES ({', '.join('?' * len(cols))})",
                    [row[c] for c in cols])
    run_sql_file(con, "models/staging/stg_hrrp_supplemental.sql")

    # mart.hospital is built from many sources; a stub with the columns the penalty mart reads.
    con.execute("""
        CREATE TABLE mart.hospital AS
        SELECT s.ccn, 'Hospital ' || s.ccn AS facility_name, 'MA' AS state,
               'Acute Care Hospitals' AS hospital_type, 'Voluntary non-profit - Private' AS hospital_ownership,
               NULL::VARCHAR AS parent_system, false AS is_teaching, 200 AS beds, 3 AS star_rating,
               s.payment_adjustment_factor, ?::DOUBLE AS medicare_base_drg_payments,
               DATE '2024-01-01' AS cr_fy_begin, DATE '2024-12-31' AS cr_fy_end,
               100000000.0 AS net_patient_revenue
        FROM stg.hrrp_supplemental s
    """, [BASE_DRG])
    run_sql_file(con, "models/marts/mart_hospital_penalty.sql")
    return con


def test_recomputed_factor_follows_the_regulation(mart):
    got = dict(mart.execute("SELECT ccn, paf_recomputed FROM mart.hospital_paf_recomputed").fetchall())
    assert got.keys() == EXPECTED_FACTOR.keys()
    for ccn, expected in EXPECTED_FACTOR.items():
        assert got[ccn] == pytest.approx(expected, abs=1e-9), ccn


def test_recomputed_factor_matches_published_within_rounding(mart):
    worst = mart.execute("""
        SELECT max(abs(s.payment_adjustment_factor - r.paf_recomputed))
        FROM stg.hrrp_supplemental s JOIN mart.hospital_paf_recomputed r USING (ccn)
    """).fetchone()[0]
    assert worst <= 0.0001


def test_penalty_dollars_and_condition_split(mart):
    rows = dict(mart.execute("SELECT ccn, est_penalty_usd FROM mart.hospital_penalty").fetchall())
    # 366 days in 2024 -> annualised to 365
    base = BASE_DRG * 365 / 366
    assert rows["010003"] == 0
    assert rows["010002"] == pytest.approx(0.03 * base)
    assert rows["010001"] == pytest.approx((1 - 0.9941) * base)  # uses CMS's published 4-dp factor

    by_cond = dict(mart.execute("""
        SELECT condition, condition_penalty_usd FROM mart.hospital_condition_penalty
        WHERE ccn = '010001' AND condition_penalty_usd > 0
    """).fetchall())
    assert set(by_cond) == {"hf", "pn"}
    assert by_cond["hf"] / by_cond["pn"] == pytest.approx(0.005 / 0.0012)
    assert sum(by_cond.values()) == pytest.approx(rows["010001"])


def test_condition_with_indicator_n_contributes_nothing(mart):
    share = mart.execute("""
        SELECT excess_term, counts_for_penalty FROM mart.hospital_condition_penalty_share
        WHERE ccn = '010003' AND condition = 'hf'
    """).fetchone()
    assert share == (0, False)


def test_never_more_than_three_percent(mart):
    n = mart.execute("""
        SELECT count(*) FROM mart.hospital_penalty
        WHERE est_penalty_usd > 0.03 * est_annual_base_drg_payments + 0.01
    """).fetchone()[0]
    assert n == 0
