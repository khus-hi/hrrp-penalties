"""CMS's HRRP payment adjustment factor, re-derived from its published inputs.

The rule (42 CFR 412.152 and 412.154, and steps 4-7 of CMS's Hospital-Specific Report
methodology):

    measure contribution = DRG payment ratio x (ERR - peer-group median ERR), if positive,
                           only for conditions CMS flags with penalty indicator "Y"
                           (25+ eligible discharges and ERR above the peer median)
    payment reduction    = neutrality modifier x sum of the measure contributions,
                           capped at 3%
    adjustment factor    = 1 - payment reduction            (so never below 0.97)

The pipeline computes this in SQL (dbt/models/marts/mart_hospital_paf_recomputed.sql, checked by
dbt/tests/assert_factor_recompute_matches_cms.sql). This module is the same arithmetic in pandas so it can be
unit-tested, and analysis/check_factor.py confirms the two agree on the live data.
"""
import numpy as np
import pandas as pd

PAF_FLOOR = 0.97  # 42 CFR 412.154(c)(2): the reduction is capped at 3%

_NO = {"N", "NO", "0", "FALSE"}
_YES = {"Y", "YES", "1", "TRUE"}


def counts_for_penalty(indicator: pd.Series) -> pd.Series:
    """CMS's per-condition penalty indicator as True / False / <NA> (unrecognised or blank)."""
    s = indicator.astype("string").str.strip().str.upper()
    out = pd.Series(pd.NA, index=indicator.index, dtype="boolean")
    out[s.isin(_NO).fillna(False)] = False
    out[s.isin(_YES).fillna(False)] = True
    return out


def excess_terms(df: pd.DataFrame) -> pd.Series:
    """Each condition's contribution before the neutrality modifier.

    Needs columns err, peer_median_err, drg_payment_ratio and penalty_indicator (one row
    per hospital x condition). A condition flagged "N" contributes 0; so does an ERR at or
    below the peer median, or a missing ERR, median or ratio. As in the SQL, a blank or
    unrecognised indicator is not treated as "N".
    """
    term = (df["err"] - df["peer_median_err"]).clip(lower=0).fillna(0) * df["drg_payment_ratio"].fillna(0)
    excluded = counts_for_penalty(df["penalty_indicator"]).eq(False).fillna(False)
    return term.where(~excluded, 0.0)


def payment_adjustment_factor(df: pd.DataFrame, neutrality_modifier: float | None = None,
                              by: str = "ccn") -> pd.DataFrame:
    """Recompute each hospital's payment adjustment factor from per-condition rows.

    df has one row per hospital x condition with the columns excess_terms() needs, plus a
    neutrality_modifier column unless the value is passed in (CMS uses one national value
    per fiscal year). Returns one row per hospital: by, sum_excess_terms,
    payment_reduction (capped at 3%) and paf_recomputed. A missing neutrality modifier
    gives NaN rather than a guess.
    """
    d = df.assign(excess_term=excess_terms(df))
    if neutrality_modifier is not None:
        d["neutrality_modifier"] = neutrality_modifier
    out = d.groupby(by, sort=True).agg(neutrality_modifier=("neutrality_modifier", "first"),
                                       sum_excess_terms=("excess_term", "sum")).reset_index()
    reduction = out["neutrality_modifier"] * out["sum_excess_terms"]
    out["payment_reduction"] = np.minimum(reduction, 1 - PAF_FLOOR)
    out["paf_recomputed"] = np.maximum(PAF_FLOOR, 1 - reduction)
    return out
