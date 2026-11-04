"""Event study: the 21st Century Cures Act peer-group reform as a natural experiment.

The reform
----------
Up to FY2018 a condition added to a hospital's HRRP penalty when its excess readmission
ratio (ERR) was above 1. The 21st Century Cures Act (December 2016) made CMS compare each
hospital with the hospitals in its dual-eligible peer group instead (five quintiles of the
share of Medicare patients also on Medicaid), from FY2019:

    old rule (FY2013-FY2018)   penalty = min(3%,      sum_c ratio_c x max(ERR_c - 1, 0))
    new rule (FY2019 on)       penalty = min(3%, NM x sum_c ratio_c x max(ERR_c - median_gc, 0))

ratio_c is the condition's share of the hospital's base operating DRG payments (CMS's "DRG
payment ratio"), median_gc the median ERR for condition c in peer group g, NM CMS's
neutrality modifier (one national number per year that keeps total penalties the same as
under the old rule), and only conditions with 25+ eligible discharges count.

Safety-net hospitals (high dual share) have higher peer medians, so the reform cut their
penalties; hospitals in low-dual groups face a lower bar and could pay more.

Treatment intensity
-------------------
For each hospital, both rules are applied to the SAME FY2019 inputs (its FY2019 ERRs,
ratios and case counts; FY2019 peer medians and NM):

    dpen_i = penalty_new_i - penalty_old_i     (percentage points of base DRG payments)

Because the inputs are fixed, dpen comes from the rule change, not from anything the
hospital did after it ("simulated instrument", as in Currie & Gruber 1996).

The event study
---------------
    ERR_ict = sum_{k != 2018} b_k 1{t = k} dpen_i + a_i + g_ct + e_ict

a_i hospital fixed effects, g_ct condition x year fixed effects, errors clustered by
hospital, FY2018 (the last payment year under the old rule) the reference year. b_k for
k < 2019 are leads (should be 0 if hospitals with bigger and smaller simulated changes
were on parallel paths); b_k for k >= 2019 trace the response. A negative b_k means a
bigger penalty went with lower ERR, i.e. fewer readmissions.

One trap, handled in the report: dpen is a function of FY2019 ERRs, and ERR performance
windows are three years long, so FY2017-FY2021 ERRs share discharges with FY2019's. Any
mean reversion in ERR then shows up as a mechanical pattern around FY2019. The
`controls="rule_only"` specification adds year-specific slopes in the hospital's own
FY2019 ERR for that condition and in its old-rule penalty, so the remaining variation in
dpen comes from the peer-group medians, i.e. from the rule.

Everything takes and returns pandas objects so it can be tested on small simulated panels
(tests/test_did.py). Estimation uses pyfixest (MIT licence, free on PyPI).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

REFORM_YEAR = 2019       # first payment year under peer-group comparison
REF_YEAR = 2018          # last payment year under the old rule: event-study reference
CAP = 0.03               # 42 CFR 412.154(c)(2): the reduction is at most 3%
MIN_CASES = 25           # a condition counts only with 25+ eligible discharges

INTENSITY_INPUTS = ["ccn", "condition", "err", "peer_median_err", "eligible_discharges",
                    "drg_payment_ratio"]


# --- 1. Treatment intensity --------------------------------------------------------------

def _counts(df: pd.DataFrame, min_cases: int) -> pd.Series:
    return (df["eligible_discharges"].fillna(0) >= min_cases) & df["err"].notna()


def old_rule_penalty(rows: pd.DataFrame, *, min_cases: int = MIN_CASES, cap: float = CAP) -> pd.Series:
    """Pre-FY2019 rule on one hospital x condition row each: min(cap, sum ratio x max(ERR - 1, 0)).

    Returns one value per ccn, as a share of base DRG payments (0.01 = 1%)."""
    term = (rows["err"] - 1).clip(lower=0) * rows["drg_payment_ratio"].fillna(0)
    term = term.where(_counts(rows, min_cases), 0.0).fillna(0.0)
    return term.groupby(rows["ccn"]).sum().clip(upper=cap).rename("penalty_old")


def new_rule_penalty(rows: pd.DataFrame, neutrality_modifier: float, *, min_cases: int = MIN_CASES,
                     cap: float = CAP) -> pd.Series:
    """FY2019+ rule: min(cap, NM x sum ratio x max(ERR - peer median, 0)), one value per ccn."""
    term = (rows["err"] - rows["peer_median_err"]).clip(lower=0) * rows["drg_payment_ratio"].fillna(0)
    term = term.where(_counts(rows, min_cases) & rows["peer_median_err"].notna(), 0.0).fillna(0.0)
    return (neutrality_modifier * term.groupby(rows["ccn"]).sum()).clip(upper=cap).rename("penalty_new")


def neutrality_modifier_from_paf(rows: pd.DataFrame, paf: pd.Series, *, min_cases: int = MIN_CASES) -> dict:
    """Back CMS's neutrality modifier out of its published adjustment factors.

    rows: one row per hospital x condition (the INTENSITY_INPUTS columns); paf: CMS's
    payment adjustment factor, indexed by ccn. For hospitals with a reduction strictly
    between 0 and the cap, NM = (1 - PAF) / sum of excess terms. PAF is published rounded
    to 4 decimals, so only hospitals with a reduction of at least 0.1% are used, and the
    median is returned with the spread so the report can show it is one number."""
    term = (rows["err"] - rows["peer_median_err"]).clip(lower=0) * rows["drg_payment_ratio"].fillna(0)
    term = term.where(_counts(rows, min_cases) & rows["peer_median_err"].notna(), 0.0).fillna(0.0)
    s = term.groupby(rows["ccn"]).sum()
    red = 1 - paf.reindex(s.index)
    ok = (red >= 0.001) & (red < CAP - 1e-6) & (s > 0)
    nm = (red[ok] / s[ok]).astype(float)
    if nm.empty:
        return {"nm": np.nan, "n": 0, "p05": np.nan, "p95": np.nan}
    return {"nm": float(nm.median()), "n": int(len(nm)), "p05": float(nm.quantile(0.05)),
            "p95": float(nm.quantile(0.95))}


def treatment_intensity(panel: pd.DataFrame, neutrality_modifier: float, *, year: int = REFORM_YEAR,
                        min_cases: int = MIN_CASES) -> pd.DataFrame:
    """One row per hospital in the FY `year` file: both rules on its FY `year` inputs.

    Columns: ccn, peer_group (FY `year`), penalty_old, penalty_new (shares),
    dpen (percentage points, new - old), direction ('down', 'up', 'unchanged'),
    n_counted (conditions with 25+ cases)."""
    missing = [c for c in INTENSITY_INPUTS + ["fiscal_year"] if c not in panel.columns]
    if missing:
        raise KeyError(f"panel is missing columns: {missing}")
    rows = panel[panel["fiscal_year"] == year]
    if rows.empty:
        raise ValueError(f"no FY{year} rows in the panel")
    rows = rows[rows["drg_payment_ratio"].notna() | rows["err"].notna()]
    out = pd.concat([old_rule_penalty(rows, min_cases=min_cases),
                     new_rule_penalty(rows, neutrality_modifier, min_cases=min_cases),
                     _counts(rows, min_cases).groupby(rows["ccn"]).sum().rename("n_counted")], axis=1)
    if "peer_group" in rows.columns:
        out = out.join(rows.groupby("ccn")["peer_group"].first())
    out["dpen"] = 100 * (out["penalty_new"] - out["penalty_old"])
    # Below a hundredth of a basis point the difference is rounding, not the rule.
    out["direction"] = np.select([out["dpen"] < -1e-6, out["dpen"] > 1e-6], ["down", "up"], "unchanged")
    return out.reset_index().rename(columns={"index": "ccn"})


def peer_group_switchers(panel: pd.DataFrame, *, year: int = REFORM_YEAR) -> pd.Index:
    """Hospitals whose peer group in any later year differs from their FY `year` group.

    Their actual exposure after FY2019 differs from the simulated one (which uses FY2019
    groups), so dropping them is a robustness check."""
    pg = panel.loc[(panel["fiscal_year"] >= year) & panel["peer_group"].notna(),
                   ["ccn", "fiscal_year", "peer_group"]].drop_duplicates(["ccn", "fiscal_year"])
    base = pg[pg["fiscal_year"] == year].set_index("ccn")["peer_group"]
    later = pg[pg["fiscal_year"] > year]
    changed = later["peer_group"].to_numpy() != base.reindex(later["ccn"]).to_numpy()
    changed &= base.reindex(later["ccn"]).notna().to_numpy()
    return pd.Index(sorted(later.loc[changed, "ccn"].unique()), name="ccn")


# --- 2. The estimation panel ----------------------------------------------------------------

def build_event_panel(panel: pd.DataFrame, intensity: pd.DataFrame, *, year: int = REFORM_YEAR) -> pd.DataFrame:
    """Hospital x condition x year rows with an ERR, for hospitals that have an intensity.

    Adds dpen, down (1 if the reform cut the hospital's penalty, 0 if it raised it, NaN if
    unchanged), penalty_old (pp), err_base (the same condition's FY `year` ERR), and the
    fixed-effect labels cell (condition x year) and ccn_cond (hospital x condition)."""
    p = panel.loc[panel["err"].notna(), ["ccn", "fiscal_year", "condition", "err"]].copy()
    p["fiscal_year"] = p["fiscal_year"].astype(int)
    if p.duplicated(["ccn", "condition", "fiscal_year"]).any():
        raise ValueError("panel has more than one ERR for a ccn x condition x fiscal_year")
    it = intensity[["ccn", "dpen", "direction", "penalty_old"]].copy()
    it["penalty_old"] = 100 * it["penalty_old"]
    it["down"] = it["direction"].map({"down": 1.0, "up": 0.0})
    d = p.merge(it, on="ccn", how="inner")
    base = p[p["fiscal_year"] == year][["ccn", "condition", "err"]].rename(columns={"err": "err_base"})
    d = d.merge(base, on=["ccn", "condition"], how="left")
    d["cell"] = d["condition"] + "_" + d["fiscal_year"].astype(str)
    d["ccn_cond"] = d["ccn"].astype(str) + "_" + d["condition"]
    return d.reset_index(drop=True)


# --- 3. Estimation --------------------------------------------------------------------------

@dataclass
class EventStudy:
    label: str
    treat: str
    ref_year: int
    coefs: pd.DataFrame            # fiscal_year, estimate, se, ci_low, ci_high, p (ref year: 0, NaN)
    vcov: pd.DataFrame             # of the treat x year coefficients only
    n: int
    n_clusters: int
    fe: str
    controls: str
    extra: dict = field(default_factory=dict)

    def coef(self, year: int) -> float:
        return float(self.coefs.set_index("fiscal_year").loc[year, "estimate"])


_CONTROL_SETS = {
    "none": [],
    # Year-specific slopes in the inputs that make dpen a function of FY2019 ERRs, so only
    # the rule (peer medians, NM) is left to move dpen.
    "rule_only": ["err_base", "penalty_old"],
}


def _term(year_var: str, var: str, ref: int) -> str:
    return f"i({year_var}, {var}, ref={ref})"


def event_study(df: pd.DataFrame, *, treat: str = "dpen", y: str = "err", ref_year: int = REF_YEAR,
                fe: str = "ccn + cell", controls: str = "none", cluster: str = "ccn",
                label: str = "") -> EventStudy:
    """Event study of y on year x treat interactions (FY ref_year omitted), via pyfixest.

    fe: pyfixest fixed-effects part (default hospital + condition x year).
    controls: 'none' or 'rule_only' (see _CONTROL_SETS)."""
    import pyfixest as pf

    cols = _CONTROL_SETS[controls]
    need = [y, treat, "fiscal_year", cluster] + cols + [c.strip() for c in fe.split("+")]
    d = df.dropna(subset=need).copy()
    d["fiscal_year"] = d["fiscal_year"].astype(int)
    rhs = " + ".join([_term("fiscal_year", treat, ref_year)] + [_term("fiscal_year", c, ref_year) for c in cols])
    fit = pf.feols(f"{y} ~ {rhs} | {fe}", data=d, vcov={"CRV1": cluster})
    tidy = fit.tidy()
    pat = re.compile(rf"^fiscal_year::(\d+):{re.escape(treat)}$")
    keep = [(int(m.group(1)), name) for name in tidy.index if (m := pat.match(str(name)))]
    if not keep:
        raise ValueError("no treatment x year coefficients were estimated")
    names = [n for _, n in keep]
    t = tidy.loc[names]
    coefs = pd.DataFrame({"fiscal_year": [yr for yr, _ in keep], "estimate": t["Estimate"].to_numpy(),
                          "se": t["Std. Error"].to_numpy(), "ci_low": t["2.5%"].to_numpy(),
                          "ci_high": t["97.5%"].to_numpy(), "p": t["Pr(>|t|)"].to_numpy()})
    coefs = pd.concat([coefs, pd.DataFrame([{"fiscal_year": ref_year, "estimate": 0.0, "se": np.nan,
                                             "ci_low": np.nan, "ci_high": np.nan, "p": np.nan}])])
    coefs = coefs.sort_values("fiscal_year").reset_index(drop=True)
    all_names = [str(n) for n in tidy.index]
    V = pd.DataFrame(np.asarray(fit._vcov), index=all_names, columns=all_names)
    vy = V.loc[names, names]
    vy.index = vy.columns = [yr for yr, _ in keep]
    return EventStudy(label=label, treat=treat, ref_year=ref_year, coefs=coefs, vcov=vy, n=int(fit._N),
                      n_clusters=int(d[cluster].nunique()), fe=fe, controls=controls)


def wald_test(es: EventStudy, years) -> dict:
    """Joint test that the coefficients for `years` are all 0 (cluster-robust).

    F = b' V^-1 b / q against F(q, G - 1), G = number of clusters."""
    yrs = [yr for yr in years if yr in es.vcov.index]
    if not yrs:
        return {"years": [], "F": np.nan, "df1": 0, "df2": es.n_clusters - 1, "p": np.nan}
    b = es.coefs.set_index("fiscal_year").loc[yrs, "estimate"].to_numpy()
    V = es.vcov.loc[yrs, yrs].to_numpy()
    q = len(yrs)
    F = float(b @ np.linalg.solve(V, b) / q)
    return {"years": yrs, "F": F, "df1": q, "df2": es.n_clusters - 1,
            "p": float(stats.f.sf(F, q, es.n_clusters - 1))}


def average_effect(es: EventStudy, years) -> dict:
    """Mean of the coefficients for `years`, with its cluster-robust SE and 95% CI."""
    yrs = [yr for yr in years if yr in es.vcov.index]
    if not yrs:
        return {"years": [], "estimate": np.nan, "se": np.nan, "ci_low": np.nan, "ci_high": np.nan, "p": np.nan}
    w = np.full(len(yrs), 1 / len(yrs))
    b = es.coefs.set_index("fiscal_year").loc[yrs, "estimate"].to_numpy()
    est = float(w @ b)
    se = float(np.sqrt(w @ es.vcov.loc[yrs, yrs].to_numpy() @ w))
    tcrit = stats.t.ppf(0.975, es.n_clusters - 1)
    p = float(2 * stats.t.sf(abs(est / se), es.n_clusters - 1)) if se > 0 else np.nan
    return {"years": yrs, "estimate": est, "se": se, "ci_low": est - tcrit * se, "ci_high": est + tcrit * se,
            "p": p}


def placebo_did(df: pd.DataFrame, fake_year: int, *, treat: str = "dpen", y: str = "err",
                before: int = REFORM_YEAR, fe: str = "ccn + cell", cluster: str = "ccn") -> dict:
    """Pretend the reform happened in fake_year: on years < `before` only, regress y on
    treat x 1{t >= fake_year} with the same fixed effects. Should be 0."""
    import pyfixest as pf

    d = df[df["fiscal_year"] < before].dropna(subset=[y, treat]).copy()
    if not (d["fiscal_year"].min() < fake_year <= d["fiscal_year"].max()):
        raise ValueError(f"fake year {fake_year} needs years on both sides in {sorted(d['fiscal_year'].unique())}")
    d["fake_post"] = (d["fiscal_year"] >= fake_year).astype(float) * d[treat]
    fit = pf.feols(f"{y} ~ fake_post | {fe}", data=d, vcov={"CRV1": cluster})
    t = fit.tidy().loc["fake_post"]
    return {"label": f"Fake reform in FY{fake_year} (FY{int(d['fiscal_year'].min())}-FY{before - 1} only)",
            "estimate": float(t["Estimate"]), "se": float(t["Std. Error"]), "ci_low": float(t["2.5%"]),
            "ci_high": float(t["97.5%"]), "p": float(t["Pr(>|t|)"]), "n": int(fit._N),
            "n_clusters": int(d[cluster].nunique())}


# --- 4. Plain English ----------------------------------------------------------------------

def pct_of_expected(err_change: float) -> float:
    """A change in ERR as percent of expected readmissions (ERR = predicted / expected)."""
    return 100.0 * err_change


def effect_sentence(avg: dict, scale_pp: float, scale_label: str) -> str:
    """One sentence for the report from the average post-reform coefficient (per pp of dpen)."""
    pt, lo, hi = (pct_of_expected(avg[k] * scale_pp) for k in ("estimate", "ci_low", "ci_high"))
    yrs = avg["years"]
    direction = "lower" if pt < 0 else "higher"
    verdict = ("The 95% interval excludes zero." if (lo > 0 or hi < 0)
               else "The 95% interval includes zero, so the data can't tell this apart from no effect.")
    when = f"In FY{yrs[0]}" if len(yrs) == 1 else f"Averaged over FY{yrs[0]}-FY{yrs[-1]}"
    return (f"{when}, a reform-driven penalty increase of {scale_label} "
            f"is followed by readmissions {abs(pt):.2f}% of expected {direction} "
            f"(95% CI {lo:+.2f}% to {hi:+.2f}%), relative to FY{REF_YEAR}. {verdict}")
