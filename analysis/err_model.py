"""Step 5: what explains a hospital's excess readmission ratio (ERR)?

Run after models.build:   python -m analysis.err_model
Writes docs/err_model_report.md, docs/figures/*.png and analysis/output/err_model_*.csv.

Outcome: a hospital's composite ERR, the average of its per-condition ERRs weighted by
CMS's eligible discharges (FY2026 supplemental file). ERR = 1.00 means as many
readmissions as expected; 1.05 means 5% more than expected.

Models, in order of how much to trust them:
  1. OLS with HC3 robust standard errors (main model, without star rating).
  2. The same with star rating added. Star ratings include readmission measures, so this
     version is partly circular; it's shown to make that point, not as the headline.
  3. Sensitivities: errors clustered by state, discharge-weighted (WLS), and DSH % in
     place of the dual-eligible share.
  4. A gradient-boosted tree (5-fold cross-validated) to look for nonlinearity.
Every number in the report is computed here from the live data; nothing is typed in.
"""
import duckdb
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import PartialDependenceDisplay, permutation_importance
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import KFold, cross_val_score, train_test_split
from statsmodels.stats.diagnostic import het_breuschpagan, linear_reset
from statsmodels.stats.outliers_influence import variance_inflation_factor

from hrrp.err import CONDITIONS as CONDS
from hrrp.err import composite_err, pct
from hrrp.shapley import shapley_r2
from ingest import config as CFG  # not "C": patsy formulas use C() for categoricals

LABELS = {"ami": "AMI", "hf": "Heart failure", "pn": "Pneumonia", "copd": "COPD",
          "cabg": "CABG", "tha_tka": "Hip/knee"}
REPORT = CFG.ROOT / "docs" / "err_model_report.md"
FIG = CFG.ROOT / "docs" / "figures"
OUT = CFG.ROOT / "analysis" / "output"
SEED = 42

# Predictor groups for "how much does social risk explain?"
SOCIAL = ["dual_10pp", "income_10k", "age65_5pp"]
STRUCTURAL = ["log2_beds", "teaching", "C(ownership, Treatment('Nonprofit'))"]
STAR = ["star_rating"]

TERM_TEXT = {
    "dual_10pp": "a 10-percentage-point higher share of dual-eligible (Medicare + Medicaid) patients",
    "dsh_10pp": "a 10-percentage-point higher Medicare DSH patient percentage",
    "income_10k": "$10,000 higher county median household income",
    "age65_5pp": "a 5-percentage-point higher share of county residents aged 65+",
    "log2_beds": "twice as many beds",
    "teaching[T.True]": "being a teaching hospital (any residents) vs not",
    "star_rating": "one more CMS star",
}


def load_data() -> pd.DataFrame:
    con = duckdb.connect(str(CFG.DB_PATH), read_only=True)
    err_cols = ", ".join(f"s.err_{c}, s.eligible_discharges_{c}" for c in CONDS)
    df = con.execute(f"""
        SELECT h.ccn, h.state, h.parent_system, h.beds, h.is_teaching, h.hospital_ownership,
               h.dual_proportion, h.dsh_pct, h.star_rating,
               h.county_median_household_income, h.county_share_age_65_plus,
               h.payment_adjustment_factor, {err_cols}
        FROM mart.hospital h JOIN stg.hrrp_supplemental s USING (ccn)
    """).df()
    con.close()

    # Composite ERR, weighted by eligible discharges, over conditions CMS reported (hrrp/err.py)
    comp = composite_err(df, CONDS)
    for col in comp:  # err_composite, total_discharges, n_conditions
        df[col] = comp[col]

    # Put proportions on a percent scale whatever the source used (0-1 or 0-100): hrrp.err.pct
    df["dual_10pp"] = pct(df["dual_proportion"]) / 10
    df["dsh_10pp"] = pct(df["dsh_pct"]) / 10
    df["income_10k"] = df["county_median_household_income"] / 10_000
    df["age65_5pp"] = pct(df["county_share_age_65_plus"]) / 5
    df["log2_beds"] = np.log2(df["beds"].where(df["beds"] > 0))
    df["teaching"] = df["is_teaching"].astype("boolean")
    own = df["hospital_ownership"].fillna("")
    df["ownership"] = np.select(
        [own.str.startswith("Voluntary"), own.str.startswith("Government"),
         own.str.startswith("Proprietary"), own.str.startswith("Physician")],
        ["Nonprofit", "Government", "For-profit", "Physician-owned"], default="Other")
    return df


def fit(formula, data, cov="HC3", **kw):
    return smf.ols(formula, data=data).fit(cov_type=cov, **kw)


PRETTY = {"log2_beds": "beds (per doubling)", "teaching[T.True]": "teaching hospital",
          "dual_10pp": "dual-eligible share (+10 pts)", "dsh_10pp": "DSH % (+10 pts)",
          "income_10k": "county income (+$10k)", "age65_5pp": "county 65+ share (+5 pts)",
          "star_rating": "star rating (+1)"}


def pretty(term: str) -> str:
    if term.startswith("C(ownership"):
        return term.split("[T.")[1].rstrip("]") + " (vs nonprofit)"
    return PRETTY.get(term, term)


def coef_table(res, model_name):
    ci = res.conf_int()
    t = pd.DataFrame({"model": model_name, "term": res.params.index, "coef": res.params.values,
                      "ci_low": ci[0].values, "ci_high": ci[1].values, "p_value": res.pvalues.values})
    return t[t.term != "Intercept"]


def plain_english(row) -> str:
    term = row.term
    if term.startswith("C(ownership"):
        level = term.split("[T.")[1].rstrip("]")
        what = f"{level} ownership (vs nonprofit)"
    else:
        what = TERM_TEXT.get(term, term)
    eff = row.coef * 100  # ERR points -> percent of expected readmissions
    direction = "higher" if eff > 0 else "lower"
    sig = ("clearly different from zero" if row.p_value < 0.01 else
           "weak evidence" if row.p_value < 0.05 else "not distinguishable from zero")
    return (f"Holding the other factors fixed, {what} goes with readmissions about "
            f"{abs(eff):.2f}% {direction} relative to expected "
            f"(95% CI {row.ci_low*100:+.2f}% to {row.ci_high*100:+.2f}%; {sig}).")


def df_md(df: pd.DataFrame, floatfmt="{:.4f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        cells = []
        for v in r.values:
            if isinstance(v, float):
                cells.append("" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    df = load_data()
    needed = ["err_composite", "log2_beds", "teaching", "ownership", "dual_10pp",
              "income_10k", "age65_5pp", "star_rating"]
    base_n = int(df["err_composite"].notna().sum())
    d = df.dropna(subset=needed).copy()
    d["teaching"] = d["teaching"].astype(bool)
    missing = {c: int(df.loc[df["err_composite"].notna(), c].isna().sum()) for c in needed[1:]}

    for col in ["teaching", "ownership", "dual_10pp", "log2_beds"]:
        if d[col].nunique() < 2:
            raise SystemExit(f"{col} has only one value among modelled hospitals; check the mart.")
    main_rhs = " + ".join(STRUCTURAL + SOCIAL)
    m_main = fit(f"err_composite ~ {main_rhs}", d)
    m_star = fit(f"err_composite ~ {main_rhs} + star_rating", d)
    m_state = fit(f"err_composite ~ {main_rhs}", d, cov="cluster",
                  cov_kwds={"groups": pd.factorize(d["state"])[0]})
    m_wls = smf.wls(f"err_composite ~ {main_rhs}", data=d, weights=d["total_discharges"]).fit(cov_type="HC3")
    d_dsh = d.dropna(subset=["dsh_10pp"])
    m_dsh = fit(f"err_composite ~ {main_rhs.replace('dual_10pp', 'dsh_10pp')}", d_dsh)

    coefs = pd.concat([coef_table(m_main, "main (HC3)"), coef_table(m_star, "with star rating"),
                       coef_table(m_state, "clustered by state"), coef_table(m_wls, "discharge-weighted"),
                       coef_table(m_dsh, "DSH instead of dual share")])
    coefs.to_csv(OUT / "err_model_coefficients.csv", index=False)

    # --- How much does social risk explain? -------------------------------------------
    sh_no_star, r2_no_star = shapley_r2(d, {"social risk": SOCIAL, "hospital structure": STRUCTURAL})
    sh_star, r2_star = shapley_r2(d, {"social risk": SOCIAL, "hospital structure": STRUCTURAL,
                                      "star rating": STAR})
    r2_social_only = smf.ols("err_composite ~ " + " + ".join(SOCIAL), data=d).fit().rsquared
    r2_dual_only = smf.ols("err_composite ~ dual_10pp", data=d).fit().rsquared

    # --- Assumption checks ----------------------------------------------------------------
    X = m_main.model.exog
    names = m_main.model.exog_names
    vif = pd.DataFrame({"term": [pretty(t) for t in names[1:]],
                        "VIF": [variance_inflation_factor(X, i) for i in range(1, X.shape[1])]})
    bp_stat, bp_p, _, _ = het_breuschpagan(m_main.resid, X)
    reset = linear_reset(smf.ols(f"err_composite ~ {main_rhs}", data=d).fit(), power=2, use_f=True)
    cooks = smf.ols(f"err_composite ~ {main_rhs}", data=d).fit().get_influence().cooks_distance[0]
    n_influential = int((cooks > 4 / len(d)).sum())
    resid = m_main.resid
    skew, kurt = float(resid.skew()), float(resid.kurt())

    fig, ax = plt.subplots(1, 2, figsize=(10, 4))
    ax[0].scatter(m_main.fittedvalues, resid, s=6, alpha=0.4)
    ax[0].axhline(0, color="grey", lw=1)
    ax[0].set(xlabel="fitted composite ERR", ylabel="residual", title="Residuals vs fitted")
    sm.qqplot(resid, line="s", ax=ax[1], markersize=2)
    ax[1].set_title("Normal Q-Q of residuals")
    fig.tight_layout()
    fig.savefig(FIG / "err_ols_diagnostics.png", dpi=130)
    plt.close(fig)

    # --- Tree model for nonlinearity -------------------------------------------------------
    feats = ["log2_beds", "teaching", "dual_10pp", "income_10k", "age65_5pp"]
    Xt = pd.get_dummies(d[feats + ["ownership"]], columns=["ownership"], drop_first=False).astype(float)
    y = d["err_composite"].values
    kf = KFold(5, shuffle=True, random_state=SEED)
    gbm = HistGradientBoostingRegressor(max_depth=3, learning_rate=0.05, max_iter=300,
                                        min_samples_leaf=30, random_state=SEED)
    cv_gbm = cross_val_score(gbm, Xt, y, cv=kf, scoring="r2")
    cv_ols = cross_val_score(LinearRegression(), Xt, y, cv=kf, scoring="r2")
    # Importance is measured on held-out hospitals; on training data a tree's
    # importances are inflated by what it memorised.
    X_tr, X_te, y_tr, y_te = train_test_split(Xt, y, test_size=0.25, random_state=SEED)
    gbm.fit(X_tr, y_tr)
    perm = permutation_importance(gbm, X_te, y_te, n_repeats=20, random_state=SEED, scoring="r2")
    gbm.fit(Xt, y)  # refit on all rows for the partial-dependence plots
    imp = (pd.DataFrame({"feature": Xt.columns, "importance_r2_drop": perm.importances_mean})
           .sort_values("importance_r2_drop", ascending=False))
    fig, ax = plt.subplots(1, 3, figsize=(12, 3.6))
    PartialDependenceDisplay.from_estimator(gbm, Xt, ["dual_10pp", "income_10k", "log2_beds"], ax=ax)
    fig.suptitle("Tree model: how predicted ERR changes with each factor (others averaged)")
    fig.tight_layout()
    fig.savefig(FIG / "err_tree_partial_dependence.png", dpi=130)
    plt.close(fig)

    # --- Per-condition models (same right-hand side) --------------------------------------
    rows = []
    for c in CONDS:
        dc = d.dropna(subset=[f"err_{c}"])
        if len(dc) < 100:
            continue
        r = fit(f"err_{c} ~ {main_rhs}", dc)
        for term in ["dual_10pp", "income_10k", "age65_5pp", "log2_beds", "teaching[T.True]"]:
            rows.append({"condition": LABELS[c], "n": int(r.nobs), "term": term,
                         "effect_pct": r.params[term] * 100, "p_value": r.pvalues[term],
                         "r2": r.rsquared})
    per_cond = pd.DataFrame(rows)
    per_cond.to_csv(OUT / "err_model_by_condition.csv", index=False)
    per_cond_wide = (per_cond.assign(term=per_cond.term.map(pretty))
                     .pivot_table(index=["condition", "n"], columns="term", values="effect_pct")
                     .reset_index())

    # --- Report ---------------------------------------------------------------------------
    main_c = coef_table(m_main, "main")
    sentences = "\n".join(f"- {plain_english(r)}" for r in main_c.itertuples())
    def cmp_row(term):
        out = {"term": term}
        for name, mdl in [("main", m_main), ("by-state clusters", m_state),
                          ("discharge-weighted", m_wls), ("with star", m_star)]:
            if term in mdl.params:
                out[name] = f"{mdl.params[term]*100:+.2f}% (p={mdl.pvalues[term]:.3f})"
        return out
    sens = pd.DataFrame([cmp_row(t) for t in m_main.params.index if t != "Intercept"])
    sens["term"] = sens["term"].map(pretty)
    dsh_line = (f"{m_dsh.params['dsh_10pp']*100:+.2f}% per 10 points (p={m_dsh.pvalues['dsh_10pp']:.3f}, "
                f"n={int(m_dsh.nobs):,})")
    star_line = (f"{m_star.params['star_rating']*100:+.2f}% per star (p={m_star.pvalues['star_rating']:.3f})")

    parts = [
        "# What explains a hospital's excess readmission ratio?",
        "_Generated by `python -m analysis.err_model` from the live data in data/hrrp.duckdb._",
        "## Data",
        f"- Outcome: composite ERR (discharge-weighted average of the six FY2026 ERRs). "
        f"Mean {d.err_composite.mean():.4f}, SD {d.err_composite.std():.4f}.",
        f"- Hospitals with a composite ERR: {base_n:,}. Used in the models (no missing predictors): **{len(d):,}**.",
        "- Missing values that removed hospitals: " + ", ".join(f"{k} {v:,}" for k, v in missing.items()) + ".",
        "- Effects are shown as **% of expected readmissions** (an ERR change of 0.01 = 1%).",
        "## Main model (OLS, HC3 robust standard errors, without star rating)",
        f"R² = {m_main.rsquared:.3f}, adjusted R² = {m_main.rsquared_adj:.3f}, n = {int(m_main.nobs):,}.",
        df_md(main_c.drop(columns="model").assign(term=lambda x: x.term.map(pretty))),
        "### In plain English", sentences,
        "### Does it hold up? (sensitivity checks)",
        df_md(sens),
        f"- Using Medicare **DSH %** instead of the dual-eligible share: {dsh_line}.",
        f"- Adding **star rating**: {star_line}. Read with care, because star ratings include "
        "readmission measures, so part of this is the outcome explaining itself.",
        "## How much of the variation does social risk explain?",
        f"- Social risk alone (dual share, county income, county 65+ share): R² = **{r2_social_only:.3f}**. "
        f"Dual-eligible share by itself: R² = {r2_dual_only:.3f}.",
        f"- Shapley split of the main model's R² ({r2_no_star:.3f}): "
        + ", ".join(f"{k} {v:.3f} ({100*v/r2_no_star:.0f}%)" for k, v in sh_no_star.items()) + ".",
        f"- With star rating added (R² {r2_star:.3f}): "
        + ", ".join(f"{k} {v:.3f}" for k, v in sh_star.items()) + ".",
        f"- So roughly {100*(1-r2_no_star):.0f}% of the variation in composite ERR is **not** explained by "
        "any of these factors.",
        "## Is the linear model missing nonlinearity?",
        f"- 5-fold cross-validated R²: linear {cv_ols.mean():.3f} (±{cv_ols.std():.3f}), "
        f"gradient-boosted tree {cv_gbm.mean():.3f} (±{cv_gbm.std():.3f}). "
        "If the tree isn't clearly better, the linear model is a fair summary.",
        "Permutation importance on a 25% held-out set (drop in R² when a feature is shuffled):",
        df_md(imp.head(8)),
        "![Partial dependence](figures/err_tree_partial_dependence.png)",
        "## Assumption checks (main model)",
        f"- **Heteroskedasticity:** Breusch-Pagan p = {bp_p:.3g}. That's why the standard errors are robust (HC3).",
        f"- **Functional form:** Ramsey RESET p = {float(reset.pvalue):.3g} (a small p means some curvature is missed; "
        "compare with the tree above).",
        f"- **Residual shape:** skew {skew:.2f}, excess kurtosis {kurt:.2f}. With n = {len(d):,}, "
        "inference doesn't depend on normality, but heavy tails mean a few hospitals pull hard.",
        f"- **Influential hospitals:** {n_influential:,} with Cook's distance > 4/n.",
        "- **Collinearity (VIF; above about 5 is a concern):**",
        df_md(vif, "{:.2f}"),
        "![OLS diagnostics](figures/err_ols_diagnostics.png)",
        "## Same model, condition by condition (effect in % of expected readmissions)",
        df_md(per_cond_wide, "{:+.2f}"),
        "## Where correlation should not be read as cause",
        "- **ERR is adjusted for clinical risk, not social risk.** So a link with the dual-eligible share mixes "
        "patients' social needs, the community's resources (housing, primary care, pharmacies) and the hospital's "
        "quality. This model can't separate those.",
        "- **County figures describe the county, not the hospital's patients** (the ecological fallacy). A "
        "downtown hospital may draw patients who are poorer than its county.",
        "- **CMS shrinks small hospitals' ERRs toward 1.0** (reliability adjustment). Hospitals with few cases "
        "look more average by construction, so part of any bed-size effect is statistical, not clinical.",
        "- **Star ratings include readmissions**, so the star coefficient is partly the outcome on both sides.",
        "- **Ownership and teaching status aren't randomly assigned.** For-profit chains choose markets, and "
        "teaching hospitals take sicker referrals. Coefficients are associations across hospitals, not the effect "
        "of converting one hospital.",
        "- **Reverse causation is possible:** penalties and finances can shape staffing and discharge planning, "
        "which then shape readmissions.",
        "- **Omitted factors** (nurse staffing, post-acute and primary-care supply, observation-stay use) "
        "are likely correlated with both the predictors and ERR.",
    ]
    REPORT.write_text("\n\n".join(parts))
    print(f"n = {len(d):,}; main R2 = {m_main.rsquared:.3f}; social-only R2 = {r2_social_only:.3f}; "
          f"CV R2 linear {cv_ols.mean():.3f} vs tree {cv_gbm.mean():.3f}")
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
