"""Regression discontinuity: does being penalized on a condition lower its later readmissions?

The design
----------
From FY2019 CMS compares each hospital with the hospitals in its dual-eligible peer group.
A condition counts toward the hospital's penalty (CMS's penalty indicator "Y") when

    (1) its excess readmission ratio (ERR) is above the peer group's median ERR, and
    (2) the hospital had at least 25 eligible discharges for that condition.

Running variable  x = err - peer_median_err   (cutoff 0, penalized when x > 0)
Treatment         D = penalized_condition     (CMS's indicator)
Outcome           y = the same condition's ERR h payment years later (h = 3 by default)

Sharp or fuzzy?
---------------
Rule (2) means that on the full sample, crossing the median does NOT always switch the
penalty on: a low-volume condition above the median is not penalized. On FY2026 CMS data
every one of those cases has fewer than 25 discharges. So we keep conditions with 25+
eligible discharges (a rule on a different variable, fixed before the cutoff matters),
and inside that sample the design is SHARP: D = 1{x > 0}. `design_type()` checks this on
the data every run, and `estimate()` switches to a FUZZY RD (D instrumented by 1{x > 0})
if any row disagrees. The full sample, low-volume rows included, is also run as a fuzzy RD
for comparison.

Ties: CMS's rule is "above" the median, so a condition exactly at the median (x == 0,
usually the median hospital itself) is NOT penalized, but rdrobust counts x >= c as
treated. Those rows are dropped (`drop_ties`) and counted in the report.

Units: ERR = predicted / expected readmissions, so a change of -0.01 in ERR is 1% fewer
readmissions than expected. `pct_of_expected()` is that conversion.

Everything here takes and returns pandas objects, so it can be unit-tested on small,
hand-built frames. Estimation uses rdrobust and rddensity (Calonico, Cattaneo, Farrell,
Titiunik; Cattaneo, Jansson, Ma), both free on PyPI.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

FIRST_PEER_MEDIAN_YEAR = 2019  # CMS's stratified (peer-group) comparison starts in FY2019
MIN_CASES = 25                 # CMS's minimum eligible discharges for a condition to count
CONDITION_LABELS = {
    "ami": "Heart attack (AMI)",
    "hf": "Heart failure",
    "pn": "Pneumonia",
    "copd": "COPD",
    "cabg": "Bypass surgery (CABG)",
    "tha_tka": "Hip/knee replacement",
}

PANEL_COLUMNS = ["ccn", "fiscal_year", "condition", "err", "peer_median_err",
                 "eligible_discharges", "penalized_condition"]


# --- 1. The analysis sample -------------------------------------------------------------

def build_rd_sample(panel: pd.DataFrame, horizon: int = 3, *, first_year: int = FIRST_PEER_MEDIAN_YEAR,
                    min_cases: int = MIN_CASES, lag: int = 3) -> pd.DataFrame:
    """One row per hospital x condition x treatment year FY t (t >= first_year).

    Keeps rows with an ERR, a published peer median and a known penalty status (CMS's
    suppressed FY2023 pneumonia has none, so it drops out). Adds:
      x             err - peer_median_err
      treated       CMS's penalty for the condition in FY t (0/1)
      above         1{x > 0}
      meets_min     eligible discharges >= min_cases
      on_cutoff     x == 0 exactly (not penalized by CMS's "above" rule)
      y             ERR of the same hospital and condition in FY t + horizon (NaN if absent)
      y_observed    1 if y is present (used to check attrition at the cutoff)
      err_lag       ERR in FY t - lag: a pre-treatment outcome, for the balance check
      cell          condition x year label, for fixed effects
    """
    missing = [c for c in PANEL_COLUMNS if c not in panel.columns]
    if missing:
        raise KeyError(f"panel is missing columns: {missing}")
    p = panel[PANEL_COLUMNS].copy()
    p["fiscal_year"] = p["fiscal_year"].astype(int)
    errs = p.loc[p["err"].notna(), ["ccn", "condition", "fiscal_year", "err"]]
    if errs.duplicated(["ccn", "condition", "fiscal_year"]).any():
        raise ValueError("panel has more than one ERR for a ccn x condition x fiscal_year")

    base = p[(p["fiscal_year"] >= first_year) & p["err"].notna()
             & p["peer_median_err"].notna() & p["penalized_condition"].notna()].copy()
    base["x"] = base["err"].astype(float) - base["peer_median_err"].astype(float)
    base["treated"] = base["penalized_condition"].astype(bool).astype(int)
    base["above"] = (base["x"] > 0).astype(int)
    base["meets_min"] = (base["eligible_discharges"].fillna(0) >= min_cases)
    base["on_cutoff"] = base["x"] == 0

    lead = errs.assign(fiscal_year=errs["fiscal_year"] - horizon).rename(columns={"err": "y"})
    base = base.merge(lead, on=["ccn", "condition", "fiscal_year"], how="left")
    lagged = errs.assign(fiscal_year=errs["fiscal_year"] + lag).rename(columns={"err": "err_lag"})
    base = base.merge(lagged, on=["ccn", "condition", "fiscal_year"], how="left")

    base["y_observed"] = base["y"].notna().astype(int)
    base["horizon"] = horizon
    base["outcome_year"] = base["fiscal_year"] + horizon
    base["cell"] = base["condition"] + "_" + base["fiscal_year"].astype(str)
    return base.reset_index(drop=True)


def drop_ties(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows exactly at the cutoff (see module docstring)."""
    return df[~df["on_cutoff"]]


def main_sample(sample: pd.DataFrame, max_outcome_year: int | None = None) -> pd.DataFrame:
    """The sharp-RD estimation sample: 25+ cases, not at the cutoff, outcome observed.

    max_outcome_year: drop treatment years whose outcome year is past the last loaded year
    (those rows can never have an outcome, so they would only pad the attrition check)."""
    s = drop_ties(sample)
    s = s[s["meets_min"] & s["y"].notna()]
    if max_outcome_year is not None:
        s = s[s["outcome_year"] <= max_outcome_year]
    return s.reset_index(drop=True)


# --- 2. Sharp or fuzzy ---------------------------------------------------------------------

def compliance_table(sample: pd.DataFrame) -> pd.DataFrame:
    """Rows by (meets_min, side of the cutoff): how many are penalized. Ties excluded."""
    s = drop_ties(sample)
    t = (s.assign(side=np.where(s["above"] == 1, "above median", "at or below median"))
          .groupby(["meets_min", "side"], as_index=False)
          .agg(rows=("treated", "size"), penalized=("treated", "sum")))
    t["share_penalized"] = t["penalized"] / t["rows"]
    return t


def design_type(df: pd.DataFrame) -> str:
    """'sharp' if the penalty is exactly 1{x > 0} on every row of df, else 'fuzzy'."""
    return "sharp" if (df["treated"].to_numpy() == (df["x"].to_numpy() > 0)).all() else "fuzzy"


# --- 3. Estimation ---------------------------------------------------------------------

@dataclass
class RDResult:
    label: str
    outcome: str
    design: str
    estimate: float       # conventional local-linear jump at the cutoff (rdrobust "Conventional")
    se_robust: float      # robust bias-corrected standard error
    ci_low: float         # robust bias-corrected 95% CI
    ci_high: float
    p_robust: float
    h: float              # MSE-optimal bandwidth (same on both sides, bwselect="mserd")
    b: float              # bias-correction bandwidth
    n_left: int           # observations inside h, below the cutoff
    n_right: int          # observations inside h, above the cutoff
    n: int                # observations passed in
    n_clusters: int | None
    cutoff: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def fe_matrix(df: pd.DataFrame, col: str = "cell") -> np.ndarray | None:
    """Dummies for col (one level dropped), as covariates for rdrobust. None if one level."""
    if df[col].nunique() < 2:
        return None
    return pd.get_dummies(df[col], drop_first=True, dtype=float).to_numpy()


def estimate(df: pd.DataFrame, *, label: str = "", y: str = "y", x: str = "x", cutoff: float = 0.0,
             fe: str | None = "cell", cluster: str | None = "ccn", fuzzy: bool | None = None,
             h: float | None = None, b: float | None = None) -> RDResult:
    """Local-linear RD (triangular kernel, MSE-optimal bandwidth, robust bias-corrected CI).

    fe: column whose dummies enter as covariates (condition x year fixed effects).
    cluster: standard errors clustered on this column (a hospital appears in several
             conditions and years). fuzzy=None picks sharp/fuzzy from the data.
    """
    from rdrobust import rdrobust

    d = df[df[y].notna()]
    design = design_type(d) if fuzzy is None else ("fuzzy" if fuzzy else "sharp")
    # Placebo cutoffs use one side only, where treatment is constant: that is a sharp RD on a
    # cutoff where nothing happens, never a fuzzy one.
    if cutoff != 0:
        design = "sharp"
    kw = dict(c=cutoff, p=1, kernel="tri", bwselect="mserd")
    covs = fe_matrix(d, fe) if fe else None
    if covs is not None:
        kw["covs"] = covs
    if cluster:
        kw["cluster"] = d[cluster].to_numpy()
        kw["vce"] = "cr1"
    if design == "fuzzy":
        kw["fuzzy"] = d["treated"].to_numpy(dtype=float)
    if h is not None:
        kw["h"] = h
        kw["b"] = b if b is not None else h
    r = rdrobust(d[y].to_numpy(dtype=float), d[x].to_numpy(dtype=float), **kw)
    n_cl = int(d[cluster].nunique()) if cluster else None
    return RDResult(
        label=label, outcome=y, design=design,
        estimate=float(r.coef.iloc[0, 0]), se_robust=float(r.se.iloc[2, 0]),
        ci_low=float(r.ci.iloc[2, 0]), ci_high=float(r.ci.iloc[2, 1]), p_robust=float(r.pv.iloc[2, 0]),
        h=float(r.bws.iloc[0, 0]), b=float(r.bws.iloc[1, 0]),
        n_left=int(r.N_h[0]), n_right=int(r.N_h[1]), n=int(len(d)), n_clusters=n_cl, cutoff=cutoff,
    )


def placebo_sample(df: pd.DataFrame, cutoff: float, x: str = "x") -> pd.DataFrame:
    """Only the side of the real cutoff that holds the placebo cutoff, so no real jump is in it."""
    if cutoff == 0:
        raise ValueError("a placebo cutoff must not be the real cutoff (0)")
    return df[df[x] < 0] if cutoff < 0 else df[df[x] > 0]


def donut(df: pd.DataFrame, radius: float, x: str = "x") -> pd.DataFrame:
    """Drop rows with |x| < radius (hospitals closest to the median)."""
    return df[df[x].abs() >= radius]


def density_test(x: pd.Series | np.ndarray, cutoff: float = 0.0) -> dict:
    """Cattaneo-Jansson-Ma manipulation test: is the density of x continuous at the cutoff?

    A small p-value would mean hospitals bunch on one side of the median. rddensity has no
    clustering, so a hospital-condition counted in several years counts several times."""
    from rddensity import rddensity

    xv = np.asarray(x, dtype=float)
    r = rddensity(X=xv, c=cutoff)
    return {"t_jackknife": float(r.test["t_jk"]), "p_jackknife": float(r.test["p_jk"]),
            "h_left": float(r.h["left"]), "h_right": float(r.h["right"]),
            "n_left": int(r.n["left"]), "n_right": int(r.n["right"]),
            "n_eff_left": int(r.n["eff_left"]), "n_eff_right": int(r.n["eff_right"])}


# --- 4. Pieces for the figure ---------------------------------------------------------------

def residualize(df: pd.DataFrame, y: str = "y", cell: str = "cell") -> pd.Series:
    """y minus its condition x year mean, plus the overall mean: removes year shifts for plotting."""
    return df[y] - df.groupby(cell)[y].transform("mean") + df[y].mean()


def binned_means(df: pd.DataFrame, y: str, x: str = "x", width: float = 0.1, bins_per_side: int = 20) -> pd.DataFrame:
    """Equal-width bins on each side of 0 inside [-width, width]: mean y, its SE and n per bin."""
    d = df[(df[x].abs() <= width) & df[y].notna()].copy()
    edges = np.linspace(0, width, bins_per_side + 1)
    out = []
    for side, part in (("below", d[d[x] < 0]), ("above", d[d[x] > 0])):
        dist = part[x].abs()
        idx = np.clip(np.searchsorted(edges, dist, side="left") - 1, 0, bins_per_side - 1)
        for i, g in part.groupby(idx):
            sign = -1 if side == "below" else 1
            n = len(g)
            sd = g[y].std(ddof=1) if n > 1 else np.nan
            out.append({"side": side, "x_mid": sign * (edges[i] + edges[i + 1]) / 2,
                        "mean": g[y].mean(), "se": sd / np.sqrt(n) if n > 1 else np.nan, "n": n})
    return pd.DataFrame(out).sort_values("x_mid").reset_index(drop=True)


def local_linear_fit(df: pd.DataFrame, y: str, h: float, side: str, x: str = "x",
                     grid: np.ndarray | None = None) -> pd.DataFrame:
    """Triangular-kernel weighted line on one side of 0 within bandwidth h, with a pointwise
    95% CI (HC1). This is the conventional fit drawn on the figure; the reported CI for the
    jump is rdrobust's robust bias-corrected one."""
    if side not in ("below", "above"):
        raise ValueError("side must be 'below' or 'above'")
    part = df[(df[x] < 0) if side == "below" else (df[x] > 0)]
    part = part[(part[x].abs() <= h) & part[y].notna()]
    xs, ys = part[x].to_numpy(float), part[y].to_numpy(float)
    w = 1 - np.abs(xs) / h
    X = np.column_stack([np.ones_like(xs), xs])
    XtW = X.T * w
    bread = np.linalg.inv(XtW @ X)
    beta = bread @ (XtW @ ys)
    resid = ys - X @ beta
    k, n = 2, len(ys)
    meat = (X.T * (w * resid) ** 2) @ X
    V = bread @ meat @ bread * (n / (n - k) if n > k else np.nan)
    if grid is None:
        grid = np.linspace(-h, 0, 50) if side == "below" else np.linspace(0, h, 50)
    G = np.column_stack([np.ones_like(grid), grid])
    fit = G @ beta
    se = np.sqrt(np.einsum("ij,jk,ik->i", G, V, G))
    return pd.DataFrame({"x": grid, "fit": fit, "lo": fit - 1.96 * se, "hi": fit + 1.96 * se,
                         "intercept": beta[0], "slope": beta[1]})


# --- 5. Plain English ----------------------------------------------------------------------

def pct_of_expected(err_change: float) -> float:
    """A change in ERR, as percent of expected readmissions (ERR = predicted / expected)."""
    return 100.0 * err_change


def effect_sentence(r: RDResult, horizon: int) -> str:
    """One sentence for the report, built only from the estimate."""
    pt, lo, hi = (pct_of_expected(v) for v in (r.estimate, r.ci_low, r.ci_high))
    direction = "lower" if pt < 0 else "higher"
    if lo > 0 or hi < 0:
        verdict = "The 95% interval excludes zero."
    else:
        verdict = "The 95% interval includes zero, so the data can't tell this apart from no effect."
    return (f"Being just above the peer-group median (penalized) rather than just below it is followed, "
            f"{horizon} payment year{'s' if horizon != 1 else ''} later, by readmissions "
            f"{abs(pt):.2f}% of expected {direction} for the same condition "
            f"(robust 95% CI {lo:+.2f}% to {hi:+.2f}%). {verdict}")
