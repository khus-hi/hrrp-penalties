"""Composite excess readmission ratio (ERR) and percent scaling, used by analysis/err_model.py."""
from collections.abc import Sequence

import numpy as np
import pandas as pd

CONDITIONS = ["ami", "hf", "pn", "copd", "cabg", "tha_tka"]


def composite_err(df: pd.DataFrame, conditions: Sequence[str] = CONDITIONS) -> pd.DataFrame:
    """Discharge-weighted average of a hospital's per-condition ERRs.

    Expects columns err_<c> and eligible_discharges_<c> for each condition c. A condition
    only counts when CMS reported an ERR for it: if err_<c> is missing, its discharges are
    left out of the denominator too, so a suppressed ERR can't drag the average toward 0.

    Returns a DataFrame (same index as df) with:
      err_composite     sum(ERR x discharges) / sum(discharges), NaN if nothing counts
      total_discharges  sum of discharges over the conditions that count
      n_conditions      how many conditions have an ERR
    """
    num = sum(df[f"err_{c}"].fillna(0) * df[f"eligible_discharges_{c}"].where(df[f"err_{c}"].notna(), 0).fillna(0)
              for c in conditions)
    den = sum(df[f"eligible_discharges_{c}"].where(df[f"err_{c}"].notna(), 0).fillna(0) for c in conditions)
    return pd.DataFrame({
        "err_composite": num / den.replace(0, np.nan),
        "total_discharges": den,
        "n_conditions": sum(df[f"err_{c}"].notna().astype(int) for c in conditions),
    }, index=df.index)


def pct(s: pd.Series) -> pd.Series:
    """Put a proportion on a 0-100 scale, whichever scale the source used.

    CMS and Census publish shares sometimes as 0.25 and sometimes as 25. If the largest
    value is at most 1.5 the whole column is treated as 0-1 and multiplied by 100;
    otherwise it is already a percent. Text such as "Not Available" becomes NaN.
    The rule looks at the whole column, so pass a full column, not single values.
    """
    s = pd.to_numeric(s, errors="coerce")
    return s * 100 if s.max(skipna=True) <= 1.5 else s
