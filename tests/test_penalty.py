"""CMS's HRRP payment adjustment factor (hrrp/penalty.py).

Method: 42 CFR 412.152 (definitions) and 412.154(c) (payment reduction, 3% cap), as laid
out in steps 4-7 of CMS's HRRP Hospital-Specific Report methodology (CMS, "Overview of the
FY 2024 Hospital Readmissions Reduction Program", HSR webinar slides 14-19:
https://qualityreportingcenter.com/globalassets/iqr-2023-events/vbp081723/fy-2024-hrrp-hsr-webinar508_.pdf):
  step 4  a measure contributes only if ERR > peer-group median ERR and 25+ eligible discharges
          (CMS's penalty indicator "Y")
  step 5  contribution = neutrality modifier x DRG payment ratio x (ERR - peer-group median ERR)
  step 6  payment reduction = sum of contributions, capped at 3%
  step 7  payment adjustment factor = 1 - payment reduction
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from hrrp.penalty import PAF_FLOOR, counts_for_penalty, excess_terms, payment_adjustment_factor

ROOT = Path(__file__).resolve().parents[1]

# --- Worked example: one real hospital, every input as CMS published it ------------------
# Source: CMS FY2026 HRRP supplemental data file (FY2026 IPPS/LTCH PPS final rule, CMS-1833-F),
# https://www.cms.gov/files/zip/fy2026-hospital-readmissions-reduction-program-supplemental-data-file.zip
# Hospital: CCN 010040, Gadsden Regional Medical Center (AL), dual peer group 2.
# The same values are in dashboard/tableau_exports/hospital_conditions.csv, and the FY2026
# neutrality modifier is in analysis/output/hrrp_chain_workbook.xlsx (Condition_Data, column I).
FY2026_NEUTRALITY_MODIFIER = 0.9626769795624243
GADSDEN_CMS_FACTOR = 0.9931  # CMS's published FY2026 payment adjustment factor (4 decimals)
GADSDEN = pd.DataFrame(
    [  # condition,  indicator, eligible discharges, ERR, peer-group median ERR, DRG payment ratio
        ("AMI",           "N",  89, 0.9771640117164375, 0.9964480468680641, 0.01875517547678904),
        ("CABG",          "Y",  47, 1.1728296363612727, 1.0008463023305127, 0.028159258296427576),
        ("COPD",          "Y",  89, 0.9967108436767906, 0.9965295871166622, 0.009923851081237011),
        ("Heart failure", "N", 229, 0.9563347418273982, 0.9921556922796164, 0.03304618443843528),
        ("Hip/knee",      "Y",  46, 1.1145805139456644, 0.9918230873884601, 0.00937305721354099),
        ("Pneumonia",     "Y", 248, 1.0158603246563729, 0.989223659092981, 0.04314998760941664),
    ],
    columns=["condition", "penalty_indicator", "eligible_discharges", "err", "peer_median_err",
             "drg_payment_ratio"],
).assign(ccn="010040")


def test_cms_worked_example_gadsden_fy2026():
    # By hand:
    #   CABG       0.028159 x (1.172830 - 1.000846 = 0.171983) = 0.0048429
    #   COPD       0.009924 x (0.996711 - 0.996530 = 0.000181) = 0.0000018
    #   Hip/knee   0.009373 x (1.114581 - 0.991823 = 0.122757) = 0.0011506
    #   Pneumonia  0.043150 x (1.015860 - 0.989224 = 0.026637) = 0.0011494
    #   AMI, HF    indicator N (ERR below the peer median)       = 0
    #   sum = 0.0071447; x neutrality modifier 0.962677 = 0.0068780 reduction
    #   factor = 1 - 0.0068780 = 0.993122, which CMS publishes as 0.9931
    out = payment_adjustment_factor(GADSDEN, FY2026_NEUTRALITY_MODIFIER).iloc[0]
    assert out["sum_excess_terms"] == pytest.approx(0.0071447060602874, abs=1e-12)
    assert out["payment_reduction"] == pytest.approx(0.0068780440499789, abs=1e-12)
    assert out["paf_recomputed"] == pytest.approx(0.9931219559500212, abs=1e-12)
    assert round(out["paf_recomputed"], 4) == GADSDEN_CMS_FACTOR


def test_worked_example_condition_terms():
    terms = excess_terms(GADSDEN).set_axis(GADSDEN["condition"])
    assert terms["AMI"] == 0 and terms["Heart failure"] == 0
    assert terms["CABG"] == pytest.approx(0.0048429, abs=1e-7)
    assert terms["Pneumonia"] == pytest.approx(0.0011494, abs=1e-7)


# --- The rules, one at a time, on hand-built rows -------------------------------------------
def rows(*specs, nm=1.0):
    """specs: (ccn, indicator, err, peer_median_err, drg_payment_ratio)."""
    df = pd.DataFrame(specs, columns=["ccn", "penalty_indicator", "err", "peer_median_err", "drg_payment_ratio"])
    return df.assign(neutrality_modifier=nm)


def test_indicator_n_contributes_nothing_even_above_median():
    df = rows(("A", "N", 1.20, 1.00, 0.05))
    assert excess_terms(df).tolist() == [0.0]
    assert payment_adjustment_factor(df)["paf_recomputed"].iloc[0] == 1.0


def test_err_at_or_below_median_contributes_nothing():
    df = rows(("A", "Y", 0.95, 1.00, 0.05), ("A", "Y", 1.00, 1.00, 0.05))
    assert excess_terms(df).tolist() == [0.0, 0.0]


def test_missing_inputs_contribute_nothing():
    df = rows(("A", "Y", np.nan, 1.00, 0.05), ("A", "Y", 1.10, np.nan, 0.05), ("A", "Y", 1.10, 1.00, np.nan))
    assert excess_terms(df).tolist() == [0.0, 0.0, 0.0]


def test_neutrality_modifier_scales_the_reduction():
    df = rows(("A", "Y", 1.10, 1.00, 0.05), nm=0.9)  # 0.05 x 0.10 = 0.005; x 0.9 = 0.0045
    assert payment_adjustment_factor(df)["paf_recomputed"].iloc[0] == pytest.approx(0.9955)


def test_reduction_is_capped_at_3_percent():
    df = rows(("A", "Y", 1.50, 1.00, 0.10))  # 0.10 x 0.50 = 0.05, more than the 3% cap
    out = payment_adjustment_factor(df).iloc[0]
    assert out["paf_recomputed"] == PAF_FLOOR == 0.97
    assert out["payment_reduction"] == pytest.approx(0.03)


def test_one_row_per_hospital():
    df = rows(("B", "Y", 1.10, 1.00, 0.05), ("A", "Y", 1.00, 1.00, 0.05), ("B", "Y", 1.20, 1.00, 0.01))
    out = payment_adjustment_factor(df)
    assert out["ccn"].tolist() == ["A", "B"]
    assert out["sum_excess_terms"].tolist() == pytest.approx([0.0, 0.005 + 0.002])


def test_missing_neutrality_modifier_gives_nan_not_a_guess():
    df = rows(("A", "Y", 1.10, 1.00, 0.05), nm=np.nan)
    assert np.isnan(payment_adjustment_factor(df)["paf_recomputed"].iloc[0])


def test_indicator_parsing():
    s = pd.Series(["Y", " n ", "Yes", "NO", "", None, "Too Few"])
    assert counts_for_penalty(s).tolist() == [True, False, True, False, pd.NA, pd.NA, pd.NA]


# --- Every hospital: the committed CMS exports, no download needed ---------------------------
EXPORTS = ROOT / "dashboard" / "tableau_exports"


@pytest.mark.skipif(not (EXPORTS / "hospital_conditions.csv").exists(), reason="Tableau exports not present")
def test_recompute_matches_cms_for_every_hospital_in_the_exports():
    cond = pd.read_csv(EXPORTS / "hospital_conditions.csv", dtype={"ccn": str})
    hosp = pd.read_csv(EXPORTS / "hospitals.csv", dtype={"ccn": str})
    out = payment_adjustment_factor(cond, FY2026_NEUTRALITY_MODIFIER)
    m = out.merge(hosp[["ccn", "payment_adjustment_factor"]], on="ccn").dropna(subset=["payment_adjustment_factor"])
    # 2,945 hospitals in CMS's supplemental file; 8 aren't in the HRRP hospital file, so the
    # exports carry CMS's factor for 2,937. CMS rounds the factor to 4 decimals.
    assert len(m) == 2937
    mismatches = m[(m["paf_recomputed"] - m["payment_adjustment_factor"]).abs() > 0.0001]
    assert mismatches.empty, mismatches.head()
