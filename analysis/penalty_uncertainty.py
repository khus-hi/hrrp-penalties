"""Step 4b: how sure is the $ estimate? Impact File cross-check + Monte Carlo interval.

Run after models.build (and ingest.load, which loads the Impact File):
    python -m analysis.penalty_uncertainty

Writes
    docs/penalty_uncertainty.md                       the report
    analysis/output/impact_gap_by_hospital.csv        both bases + the gap, per hospital
    analysis/output/impact_gap_summary.csv            gap distribution, overall and by group
    analysis/output/penalty_interval.csv              90% intervals: national, condition, chain
    analysis/output/penalty_interval_components.csv   national interval with one input varied at a time
    docs/figures/uncertainty/*.png

Interview version: the penalty factor is CMS's exact number, so the uncertainty is in the
dollar base. We have two official but different measures of that base (the hospital's own
cost report and CMS's Impact File), so we measure how far apart they are, then let a
Monte Carlo resample those observed gaps (plus imputed bases for penalized hospitals with
none) and read off a 90% interval. Drift in CMS's DRG payment ratios is run separately as a
sensitivity, because its effect on the condition split flips with how the noise is centred.
The method and every choice are in hrrp/uncertainty.py and the report.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import duckdb
import numpy as np
import pandas as pd

from hrrp import uncertainty as U
from ingest import config as C

REPORT = C.ROOT / "docs" / "penalty_uncertainty.md"
OUT = C.ROOT / "analysis" / "output"
FIG = C.ROOT / "docs" / "figures" / "uncertainty"
RULE_DIR = C.RAW / "ipps_fy2026_final_rule_text"
N_DRAWS, SEED = 10_000, 2026
# Drift in DRG payment ratios is measured between FY2026 and this earlier CMS file. FY2023's
# window (Jul 2018-Jun 2021) ends where FY2026's (Jul 2021-Jun 2024) starts, and three years
# is about the lag between the middle of FY2026's window and the FY2026 payment year.
DRIFT_FROM = 2023
ALL_POP = "all penalized hospitals"
SAME_POP = "same hospitals as the point estimate"
BLUE, INK, MUTED, GRID = "#2a78d6", "#0b0b0b", "#898781", "#e1e0d9"


def table_exists(con, schema, name):
    return con.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema = ? AND table_name = ?",
                       [schema, name]).fetchone()[0] > 0


def to_num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.astype("string").str.replace(r"[$,%\s]", "", regex=True), errors="coerce")


def md(df: pd.DataFrame, money=(), pct=(), ratio=()) -> str:
    if df.empty:
        return "_(no rows)_\n"
    d = df.copy()
    for c in d.columns:
        if c in money:
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"${v / 1e6:,.1f}M")
        elif c in pct:
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{100 * v:.1f}%")
        elif c in ratio:
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else f"{v:.3f}")
    lines = ["| " + " | ".join(map(str, d.columns)) + " |", "|" + "---|" * len(d.columns)]
    lines += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in row) + " |" for row in d.itertuples(index=False)]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- data
def load_hospitals(con) -> pd.DataFrame:
    return con.execute("""
        SELECT ccn, facility_name, state, parent_system, beds, payment_adjustment_factor,
               CASE WHEN est_penalty_usd IS NOT NULL THEN est_annual_base_drg_payments END AS cr_base,
               est_penalty_usd, estimate_quality
        FROM mart.hospital_penalty_wide
        WHERE payment_adjustment_factor IS NOT NULL""").df()


def load_impact(con) -> tuple[pd.DataFrame | None, pd.DataFrame]:
    mapping = con.execute("SELECT field, matched_column FROM raw.column_mapping_log "
                          "WHERE source = 'ipps_impact' ORDER BY field").df() \
        if table_exists(con, "raw", "column_mapping_log") else pd.DataFrame()
    if not table_exists(con, "raw", "ipps_impact"):
        return None, mapping
    raw = con.execute("SELECT * FROM raw.ipps_impact").df()
    df = pd.DataFrame({"ccn": raw["ccn"].astype("string").str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(6)})
    for col in ("transfer_adjusted_cases", "bills", "case_mix_index", "wage_index", "cola",
                "readmissions_adjustment_factor"):
        df[col] = to_num(raw[col]) if col in raw else np.nan
    df = df[df.ccn.str.fullmatch(r"[0-9A-Z]{6}", na=False)].drop_duplicates("ccn")
    return df, mapping


def load_conditions(con, ccns) -> tuple[np.ndarray, np.ndarray]:
    s = con.execute("""
        SELECT ccn, condition, err, peer_median_err, drg_payment_ratio, counts_for_penalty
        FROM mart.hospital_condition_penalty_share""").df()
    s["excess"] = np.where(s.counts_for_penalty.eq(False), 0.0,
                           (s.err - s.peer_median_err).clip(lower=0).fillna(0))
    ex = s.pivot_table(index="ccn", columns="condition", values="excess", aggfunc="first")
    ra = s.pivot_table(index="ccn", columns="condition", values="drg_payment_ratio", aggfunc="first")
    ex = ex.reindex(index=ccns, columns=U.CONDITIONS).fillna(0).to_numpy(float)
    ra = ra.reindex(index=ccns, columns=U.CONDITIONS).to_numpy(float)
    return ex, ra


def load_drift(con) -> tuple[dict, pd.DataFrame, int | None]:
    """Observed ln(ratio FY2026 / ratio FY{DRIFT_FROM}) per condition, trimmed at p1/p99."""
    if not table_exists(con, "mart", "fct_hospital_condition_year"):
        return {}, pd.DataFrame(), None
    p = con.execute("""
        SELECT ccn, condition, fiscal_year::INT AS fy, drg_payment_ratio
        FROM mart.fct_hospital_condition_year
        WHERE drg_payment_ratio > 0""").df()
    years = sorted(y for y in p.fy.unique() if y < C.PROGRAM_YEAR)
    base = DRIFT_FROM if DRIFT_FROM in years else (years[-1] if years else None)
    if base is None:
        return {}, pd.DataFrame(), None
    a = p[p.fy == C.PROGRAM_YEAR].set_index(["ccn", "condition"]).drg_payment_ratio
    b = p[p.fy == base].set_index(["ccn", "condition"]).drg_payment_ratio
    j = pd.concat([a.rename("now"), b.rename("then")], axis=1, join="inner").reset_index()
    j["log_drift"] = np.log(j.now / j.then)
    pools, rows = {}, []
    for c in U.CONDITIONS:
        x, lo, hi = U.trimmed(j.loc[j.condition == c, "log_drift"])
        # Centred (average multiplier 1): the spread across hospitals is the noise we resample. The median shift is a
        # trend (e.g. hip/knee surgery moving to outpatient), and applying it would be a forecast,
        # so it is reported, not applied.
        pools[c] = x  # raw (trimmed) log drift; centred where it is used
        if len(x):
            q = np.exp(np.percentile(x, [5, 50, 95]))
            rows.append({"condition": c, "hospitals": len(x), "ratio_change_p5": q[0], "median (trend, not applied)": q[1],
                         "p95": q[2], "trimmed_below": np.exp(lo), "trimmed_above": np.exp(hi)})
    return pools, pd.DataFrame(rows), base


def rule_amounts():
    files = sorted(p for p in RULE_DIR.glob("*") if p.is_file()) if RULE_DIR.exists() else []
    if not files:
        return None, "final rule text not downloaded (python -m ingest.download)"
    try:
        return U.parse_standardized_amounts(files[0].read_text(errors="ignore")), files[0].name
    except ValueError as e:
        return None, str(e)


# ---------------------------------------------------------------- figures
def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(MUTED)
    ax.tick_params(colors=INK, labelsize=9)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def fig_gap(ratio, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    r = ratio[np.isfinite(ratio) & (ratio > 0)]
    lo, hi = np.percentile(r, [0.5, 99.5])
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    ax.hist(np.log(r[(r >= lo) & (r <= hi)]), bins=60, color=BLUE, edgecolor="white", linewidth=0.6)
    ax.axvline(0, color=INK, linewidth=1)
    ax.axvline(np.log(np.median(r)), color=INK, linewidth=1, linestyle="--")
    ticks = [0.5, 0.75, 1, 1.25, 1.5, 2]
    ax.set_xticks(np.log(ticks), [f"{t:g}x" for t in ticks])
    ax.set_xlabel("Impact File base / cost-report base (log scale; solid = equal, dashed = median)", color=INK, fontsize=9)
    ax.set_ylabel("Hospitals", color=INK, fontsize=9)
    ax.set_title("How far apart the two payment bases are, per hospital", color=INK, fontsize=11, loc="left")
    _style(ax)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


def fig_national(draws, point, lo, hi, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    ax.axvspan(lo / 1e6, hi / 1e6, color=GRID, alpha=0.7, linewidth=0)
    ax.hist(draws / 1e6, bins=80, color=BLUE, edgecolor="white", linewidth=0.4)
    ax.axvline(point / 1e6, color=INK, linewidth=1.2)
    ax.text(0.01, 0.97, f"Black line: point estimate \\${point / 1e6:,.1f}M\nShaded: 90% interval "
            f"\\${lo / 1e6:,.1f}M to \\${hi / 1e6:,.1f}M", transform=ax.transAxes, color=INK, fontsize=8, va="top",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85})
    ax.set_xlabel("Simulated FY2026 national HRRP penalty ($ millions)", color=INK, fontsize=9)
    ax.set_ylabel("Simulations", color=INK, fontsize=9)
    ax.set_title(f"{len(draws):,} Monte Carlo draws of the national total", color=INK, fontsize=11, loc="left")
    _style(ax)
    fig.tight_layout(); fig.savefig(path); plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    hosp = load_hospitals(con)
    impact, mapping = load_impact(con)
    sa, rule_note = rule_amounts()
    OUT.mkdir(parents=True, exist_ok=True); FIG.mkdir(parents=True, exist_ok=True)

    # ---- 1. Impact File base and the gap -------------------------------------------------
    hosp["if_base"] = np.nan
    join_check = pd.DataFrame()
    if impact is not None and sa is not None:
        if impact.transfer_adjusted_cases.isna().all():
            print("WARNING: no transfer-adjusted cases column matched; falling back to raw Bills, which overstates "
                  "the Impact File base. Check the column mapping in ingest/load.py.")
        cases = impact.transfer_adjusted_cases.where(impact.transfer_adjusted_cases.notna(), impact.bills)
        impact["if_base"] = U.impact_base(cases, impact.case_mix_index, impact.wage_index, impact.cola, sa)
        impact.loc[~(impact.if_base > 0), "if_base"] = np.nan
        hosp = hosp.drop(columns="if_base").merge(impact[["ccn", "if_base", "readmissions_adjustment_factor"]],
                                                  on="ccn", how="left")
        f = hosp.dropna(subset=["readmissions_adjustment_factor"])
        join_check = pd.DataFrame([{
            "hospitals_with_cms_factor": len(hosp),
            "found_in_impact_file": int(hosp.if_base.notna().sum()),
            "impact_file_hrrp_factor_present": len(f),
            "factor_matches_supplemental_file (within 0.0001)":
                int((f.readmissions_adjustment_factor - f.payment_adjustment_factor).abs().le(1e-4).sum()),
        }])
    elif impact is None:
        print("raw.ipps_impact not found: run python -m ingest.load (the Impact File zip must be in data/raw/ipps_impact_file/).")
    else:
        print(f"Standardized amounts not read from the final rule: {rule_note}")
    if hosp.if_base.notna().sum() == 0:
        print("No Impact File bases, so there is no gap to resample. Stopping before the Monte Carlo.")
        print("Column mapping found:\n" + mapping.to_string(index=False))
        sys.exit(1)

    hosp["gap_ratio"] = hosp.if_base / hosp.cr_base
    both = hosp.dropna(subset=["gap_ratio"])
    hosp.to_csv(OUT / "impact_gap_by_hospital.csv", index=False)

    def summ(label, g):
        row = U.gap_summary(g.gap_ratio)
        row["total_ratio (sum IF / sum CR)"] = g.if_base.sum() / g.cr_base.sum() if len(g) else np.nan
        return {"group": label, **row}
    gap_rows = [summ("All hospitals with both bases", both)]
    gap_rows += [summ(f"Quality: {q}", g) for q, g in both.groupby("estimate_quality")]
    gap_rows += [summ(f"System: {s}", g) for s, g in both.groupby(both.parent_system.fillna("Not one of the four chains"))]
    beds = pd.qcut(both.beds, 5, duplicates="drop")
    gap_rows += [summ(f"Beds {b}", g) for b, g in both.groupby(beds, observed=True)]
    gap = pd.DataFrame(gap_rows)
    gap.to_csv(OUT / "impact_gap_summary.csv", index=False)
    fig_gap(both.gap_ratio.to_numpy(), FIG / "impact_gap_hist.png")

    # ---- 2. Monte Carlo ------------------------------------------------------------------
    log_gap, cut_lo, cut_hi = U.trimmed(np.log(both.gap_ratio))
    drift, drift_tbl, drift_base = load_drift(con)
    excess, ratio = load_conditions(con, hosp.ccn)
    band = pd.qcut(hosp.beds, 5, labels=False, duplicates="drop").fillna(-1).astype(int).to_numpy()
    inp = U.MCInputs(
        rate=(1 - hosp.payment_adjustment_factor).clip(lower=0).to_numpy(float),
        cr_base=hosp.cr_base.to_numpy(float), if_base=hosp.if_base.to_numpy(float),
        size_band=band, group=hosp.parent_system.fillna("").to_numpy(object),
        excess=excess, drg_ratio=ratio, log_gap=log_gap, drift=drift)
    point = U.point_estimate(inp)
    published = float(hosp.est_penalty_usd.sum())
    assert abs(point["national"][0] - published) < 1, (point["national"][0], published)

    # Two populations. The point estimate covers only hospitals with a usable cost-report base, so the
    # like-for-like check is an interval over those same hospitals. The headline interval also gives a
    # base to penalized hospitals that have none, which can only add dollars.
    labels = {"ami": "AMI", "hf": "Heart failure", "pn": "Pneumonia", "copd": "COPD", "cabg": "CABG", "tha_tka": "Hip/knee"}
    # DRG ratio drift is NOT in the intervals. Perturbing ratios and renormalising shares moves
    # dollars between conditions in a direction set by how the noise is centred (median vs
    # mean 1 gave opposite shifts on the real data), not by the data. It is reported below as
    # a sensitivity instead; the split inside the intervals is CMS's own arithmetic.
    draws = U.simulate(inp, N_DRAWS, SEED, vary_ratios=False)
    draws_same = U.simulate(inp, N_DRAWS, SEED, vary_ratios=False, impute_missing=False)
    table = pd.concat([U.interval_table(draws, point).assign(population=ALL_POP),
                       U.interval_table(draws_same, point).assign(population=SAME_POP)], ignore_index=True)
    table["name"] = table.name.map(lambda n: labels.get(n, n))
    table.to_csv(OUT / "penalty_interval.csv", index=False)
    same = table[table.population == SAME_POP].reset_index(drop=True)
    table = table[table.population == ALL_POP].reset_index(drop=True)

    comps = []
    for label, kw in [("Both inputs", {}),
                      ("Payment base only", {"vary_ratios": False, "impute_missing": False}),
                      ("Penalized hospitals with no base only", {"vary_base": False, "vary_ratios": False})]:
        d = draws if not kw else U.simulate(inp, N_DRAWS, SEED, **kw)
        lo, hi = np.percentile(d["national"], [5, 95])
        comps.append({"inputs varied": label, "p5_usd": lo, "p95_usd": hi, "width_usd": hi - lo})
    comps = pd.DataFrame(comps)
    comps.to_csv(OUT / "penalty_interval_components.csv", index=False)

    # Sensitivity: condition split under observed DRG ratio drift, two ways of centring the noise.
    sens = pd.DataFrame({"condition": [labels[c] for c in U.CONDITIONS],
                         "point_estimate_usd": [point[f"condition:{c}"][0] for c in U.CONDITIONS]})
    if drift:
        for tag, centre in [("median-centred", lambda x: x - np.median(x)), ("mean-1", U.mean_one)]:
            alt = U.MCInputs(**{**inp.__dict__, "drift": {c: centre(x) for c, x in drift.items() if len(x)}})
            d = U.simulate(alt, N_DRAWS, SEED, vary_base=False, impute_missing=False)
            sens[f"{tag}: p5"] = [np.percentile(d[f"condition:{c}"], 5) for c in U.CONDITIONS]
            sens[f"{tag}: p95"] = [np.percentile(d[f"condition:{c}"], 95) for c in U.CONDITIONS]
    sens.to_csv(OUT / "penalty_ratio_drift_sensitivity.csv", index=False)

    nat = table[table.level == "national"].iloc[0]
    fig_national(draws["national"], nat.point_estimate_usd, nat.p5_usd, nat.p95_usd, FIG / "national_interval.png")

    pen_missing = hosp[(hosp.payment_adjustment_factor < 1) & hosp.cr_base.isna()]
    world_totals = pd.DataFrame([
        {"base": "Cost report (published point estimate)", "hospitals": int(hosp.cr_base.notna().sum()),
         "total_usd": published},
        {"base": "Impact File, same hospitals where available", "hospitals": int(both.shape[0]),
         "total_usd": float(((1 - both.payment_adjustment_factor) * both.if_base).sum())},
        {"base": "Cost report, same hospitals", "hospitals": int(both.shape[0]),
         "total_usd": float(((1 - both.payment_adjustment_factor) * both.cr_base).sum())},
    ])
    con.close()

    # ---- 3. Report -------------------------------------------------------------------------
    def fmt_iv(r):
        return f"${r.p5_usd / 1e6:,.1f}M to ${r.p95_usd / 1e6:,.1f}M"
    show = pd.DataFrame({
        "name": table.name, "point_estimate_usd": table.point_estimate_usd,
        "90% interval, same hospitals": same.apply(fmt_iv, axis=1),
        "contains point": same.interval_contains_point,
        "90% interval, all penalized hospitals": table.apply(fmt_iv, axis=1),
        "median, all penalized": table.p50_usd})
    cols = list(show.columns)
    contains_all = bool(same.interval_contains_point.all())
    snat = same[same.level == "national"].iloc[0]
    miss = comps[comps["inputs varied"] == "Penalized hospitals with no base only"].iloc[0]
    sa_block = (f"Table 1A (wage index > 1): labor ${sa.high_labor:,.2f}, nonlabor ${sa.high_nonlabor:,.2f} "
                f"({100 * sa.high_labor_share:.1f}% labor share). Table 1B (wage index <= 1): labor ${sa.low_labor:,.2f}, "
                f"nonlabor ${sa.low_nonlabor:,.2f} ({100 * sa.low_labor_share:.1f}%). Read from `{rule_note}`; "
                "the text the parser matched is quoted at the end of this report.")
    parts = [
        "# How sure is the penalty estimate? Payment-base cross-check and a 90% interval",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.penalty_uncertainty` "
        f"({N_DRAWS:,} draws, seed {SEED}). Method: `hrrp/uncertainty.py`._",
        "## Headline",
        f"National FY2026 HRRP penalty: point estimate **${nat.point_estimate_usd / 1e6:,.1f}M** "
        f"({int(hosp.cr_base.notna().sum()):,} hospitals with a usable cost-report base).\n\n"
        f"- **Same hospitals as the point estimate:** 90% interval ${snat.p5_usd / 1e6:,.1f}M to "
        f"${snat.p95_usd / 1e6:,.1f}M. "
        + ("Every interval over these hospitals contains its point estimate (national, conditions, chains)."
           if contains_all else
           "**At least one interval over these hospitals does not contain its point estimate**; see the table.")
        + f"\n- **All penalized hospitals:** 90% interval **${nat.p5_usd / 1e6:,.1f}M to ${nat.p95_usd / 1e6:,.1f}M** "
        f"(median ${nat.p50_usd / 1e6:,.1f}M). This adds the {len(pen_missing)} hospitals CMS penalized that have no "
        f"usable cost-report base (alone they add ${(miss.p5_usd - nat.point_estimate_usd) / 1e6:,.1f}M to "
        f"${(miss.p95_usd - nat.point_estimate_usd) / 1e6:,.1f}M), so its low end can sit above the point estimate: "
        "the point estimate leaves those hospitals at $0.\n"
        + (f"- **Direction:** across hospitals with both bases, the Impact File total is {gap.iloc[0]['total_ratio (sum IF / sum CR)']:.3f}x "
           "the cost-report total (section 1), so the published point estimate is more likely "
           + ("low than high." if gap.iloc[0]["total_ratio (sum IF / sum CR)"] > 1 else "high than low.")),
        "![national interval](figures/uncertainty/national_interval.png)",
        "## 1. Cost report vs Impact File: the gap in each hospital's base",
        "**Cost-report base:** HCRIS Worksheet E Part A line 1, latest report, annualised (penalty_method.md). "
        "**Impact File base:** CMS's FY2026 IPPS Impact File, transfer-adjusted cases x transfer-adjusted case-mix "
        "index x (labor standardized amount x FY2026 wage index + nonlabor amount x COLA), with the FY2026 "
        "national standardized amounts from the final rule:",
        sa_block,
        "Impact File columns used (matched by pattern in `ingest/load.py`; check these are the right ones):",
        md(mapping),
        "CCN join check. The Impact File carries a *proxy* readmissions factor (CMS's estimate when it built the file), so not every hospital has to match the final factor; a high match rate shows the CCNs line up:",
        md(join_check),
        "Gap = Impact File base / cost-report base (1.0 = the two agree):",
        md(gap[["group", "hospitals", "p5", "p25", "p50", "p75", "p95", "share_within_10pct", "share_within_25pct",
                 "total_ratio (sum IF / sum CR)"]],
           pct=("share_within_10pct", "share_within_25pct"),
           ratio=("p5", "p25", "p50", "p75", "p95", "total_ratio (sum IF / sum CR)")),
        "All percentiles and shares: `analysis/output/impact_gap_summary.csv`; every hospital: "
        "`analysis/output/impact_gap_by_hospital.csv`.",
        "![gap histogram](figures/uncertainty/impact_gap_hist.png)",
        "Penalty totals under each base:",
        md(world_totals, money=("total_usd",)),
        "## 2. Monte Carlo",
        "Two inputs go into the interval (DRG ratios are a separate sensitivity, below). Every distribution is "
        "resampled from observed data:",
        "| Input | What is drawn | Where the distribution comes from |\n|---|---|---|\n"
        "| Payment base, level | Each draw uses the cost-report level or the Impact File level, 50/50 | The two "
        "sources differ systematically (different years and rates) and neither is FY2026 actuals, so the choice "
        "moves every hospital together. 50/50 is a CHOICE: no data says which source is closer. |\n"
        f"| Payment base, hospital noise | Each hospital's base x exp(e), e resampled per hospital | Observed log gaps "
        f"ln(Impact/cost report) for {len(log_gap):,} hospitals, divided by sqrt(2) and shifted so the average multiplier is 1 "
        f"(equal noise in each source). Gaps outside the 1st-99th percentile ({np.exp(cut_lo):.2f}x to "
        f"{np.exp(cut_hi):.2f}x) are left out of the pool as likely data errors. |\n"

        f"| Penalized hospitals with no usable base ({len(pen_missing)}) | A base for each | The other source's base "
        "x a resampled gap; with neither source, the base of a random hospital in the same bed-size fifth. |\n",
        "### DRG payment ratios: a sensitivity, not part of the interval",
        f"The ratios only split each hospital's dollars across conditions (CMS's factor is fixed). We measured how "
        f"much each hospital's ratio changed between CMS's FY{drift_base} and FY2026 files and re-ran the split with "
        "that drift resampled. Because shares are renormalised, the result depends on how the noise is centred: "
        "median-centred noise pushes noisy conditions up, mean-1 noise pushes them down, by similar amounts. A "
        "result that flips with a convention is not something the data pins down, so the drift is shown here and "
        "kept out of the 90% intervals, whose condition split is CMS's own arithmetic.",
        "Observed drift in DRG payment ratios (FY2026 ratio / earlier ratio):",
        md(drift_tbl, ratio=("ratio_change_p5", "median (trend, not applied)", "p95", "trimmed_below", "trimmed_above")) if len(drift_tbl) else "_Panel not built: ratios held at CMS's values._\n",
        "Condition totals with the drift resampled, base held at the cost report (5th to 95th percentile):",
        md(sens, money=tuple(c for c in sens.columns if c != "condition")),
        "### National, by condition, by chain",
        md(show[cols], money=("point_estimate_usd", "median, all penalized")),
        "### Which input drives the width (national total, one input varied at a time)",
        md(comps, money=("p5_usd", "p95_usd", "width_usd")),
        "## What this does not cover",
        "- Hospitals with no CMS factor (Maryland and others not in the payment file) are left out, as in the "
        "point estimate: CMS gave them no penalty to estimate.\n"
        "- Sole community and Medicare-dependent hospitals can be paid on a hospital-specific rate; the Impact "
        "File base uses the federal rate for everyone.\n"
        "- The Impact File uses FY2024 claim volume. If FY2026 Medicare fee-for-service volume differs (for "
        "example, more Medicare Advantage enrolment), both sources miss it in the same direction.",
        "## Rule text the standardized amounts were read from",
        *(f"> {v}\n" for v in sa.snippets.values()),
    ]
    REPORT.write_text("\n\n".join(parts) + "\n")
    print(md(show[cols], money=("point_estimate_usd", "median, all penalized")))
    print(f"Report: {REPORT}")


if __name__ == "__main__":
    main()
