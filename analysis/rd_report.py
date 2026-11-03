"""Step 6: does being penalized on a condition lower its later readmissions? (docs/rd_report.md)

Run after the multi-year panel is built (make build):
    python -m analysis.rd_report          (or: make rd)

Regression discontinuity at CMS's peer-group median (FY2019+), estimated with
hrrp/causal/rd.py. Writes:
    docs/rd_report.md                  the report (every number generated here)
    docs/figures/rd/*.png              binned RD plot per condition, and pooled
    analysis/output/rd_*.csv           every estimate, balance and density result

Main outcome: the same condition's ERR 3 payment years later (FY t+3), whose performance
period does not overlap FY t's. FY t+1 is shown too, labelled as contaminated: two of its
three years are the same discharges that set the running variable. FY t+4 is a timing
check (its window starts about when the hospital learns its FY t result).
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hrrp.causal import rd

MAIN_H = 3
HORIZONS = {3: "main (non-overlapping window)", 1: "contaminated by overlap", 4: "timing check"}
PLACEBO_CUTOFFS = (-0.05, 0.05)
DONUT = 0.002
BW_SCALES = (0.5, 2.0)
BALANCE = {
    "beds": "Beds (cost report)",
    "dual_proportion": "Dual-eligible share (CMS, FY t)",
    "for_profit": "For-profit (0/1)",
    "government": "Government-owned (0/1)",
    "teaching": "Teaching (0/1, residents > 0)",
    "err_lag": "Same condition's ERR in FY t-3 (pre-period)",
}
FIXTURE_MAX_HOSPITALS = 500
PANEL = "mart.fct_hospital_condition_year"

try:  # ingest.config needs only the standard library, but keep the module importable alone
    from ingest import config as C
    ROOT = C.ROOT
except Exception:  # pragma: no cover
    C = None
    ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "rd_report.md"
FIG_DIR = ROOT / "docs" / "figures" / "rd"
OUT_DIR = ROOT / "analysis" / "output"

# Colours: two categorical slots (blue = not penalized side, orange = penalized side),
# with different marker shapes so the sides don't rely on colour alone.
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#898781", "#e1e0d9"


# --- Data -------------------------------------------------------------------------------------

def load(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = con.execute(f"""
        SELECT ccn, fiscal_year, condition, err, peer_median_err, eligible_discharges,
               penalized_condition, dual_proportion, perf_start, perf_end
        FROM {PANEL}""").df()
    hosp = con.execute("""
        SELECT ccn, beds, is_teaching, hospital_ownership FROM mart.hospital""").df()
    return panel, hosp


def hospital_covariates(hosp: pd.DataFrame) -> pd.DataFrame:
    """Beds, ownership and teaching from mart.hospital (FY2026 General Info + latest cost report).
    These are one snapshot per hospital, not year by year."""
    own = hosp["hospital_ownership"].fillna("")
    return pd.DataFrame({
        "ccn": hosp["ccn"],
        "beds": pd.to_numeric(hosp["beds"], errors="coerce"),
        "for_profit": np.where(own == "", np.nan, (own == "Proprietary").astype(float)),
        "government": np.where(own == "", np.nan, own.str.startswith("Government").astype(float)),
        "teaching": hosp["is_teaching"].astype("float"),
    })


def period_overlap(panel: pd.DataFrame, horizons) -> pd.DataFrame:
    """Months shared by the performance periods of FY t and FY t+h, from the panel's dates."""
    per = (panel.dropna(subset=["perf_start", "perf_end"])
                .groupby("fiscal_year")[["perf_start", "perf_end"]]
                .agg(lambda s: s.mode().iloc[0]))
    per = per.apply(pd.to_datetime)
    rows = []
    for h in horizons:
        for t in per.index:
            if t < rd.FIRST_PEER_MEDIAN_YEAR or t + h not in per.index:
                continue
            a0, a1 = per.loc[t]
            b0, b1 = per.loc[t + h]
            days = max((min(a1, b1) - max(a0, b0)).days + 1, 0)
            rows.append({"horizon": h, "fy_t": t, "fy_t_h": t + h,
                         "period_t": f"{a0:%Y-%m}..{a1:%Y-%m}", "period_t_h": f"{b0:%Y-%m}..{b1:%Y-%m}",
                         "overlap_months": round(days / 30.44, 1)})
    return pd.DataFrame(rows)


# --- Estimation -------------------------------------------------------------------------------

def _est(df, **kw) -> dict:
    """rd.estimate, but a failure becomes a row with the error instead of stopping the run."""
    label = kw.get("label", "")
    try:
        if df["y" if "y" not in kw else kw["y"]].notna().sum() < 50:
            raise ValueError(f"only {df[kw.get('y', 'y')].notna().sum()} rows")
        return rd.estimate(df, **kw).as_dict() | {"error": ""}
    except Exception as e:  # noqa: BLE001 - reported in the table
        return {"label": label, "outcome": kw.get("y", "y"), "error": f"{type(e).__name__}: {e}"}


def run(panel: pd.DataFrame, hosp: pd.DataFrame) -> dict:
    last_year = int(panel["fiscal_year"].max())
    cov = hospital_covariates(hosp)
    res: dict = {"last_year": last_year, "estimates": [], "horizon_samples": {}}

    for h, tag in HORIZONS.items():
        s = rd.build_rd_sample(panel, horizon=h)
        s = s[s["outcome_year"] <= last_year]
        s = s.merge(panel[["ccn", "fiscal_year", "condition", "dual_proportion"]],
                    on=["ccn", "fiscal_year", "condition"], how="left").merge(cov, on="ccn", how="left")
        main = rd.main_sample(s, last_year)
        res["horizon_samples"][h] = {"sample": s, "main": main}
        if main.empty:
            continue
        rows = [_est(main, label="All conditions")]
        for c in rd.CONDITION_LABELS:
            part = main[main["condition"] == c]
            if not part.empty:
                rows.append(_est(part, label=rd.CONDITION_LABELS[c]))
        for r in rows:
            r.update(section="estimate", horizon=h, horizon_note=tag)
        res["estimates"] += rows

    hs = res["horizon_samples"].get(MAIN_H)
    if hs is None or hs["main"].empty:
        return res
    s, main = hs["sample"], hs["main"]
    pooled = next(r for r in res["estimates"] if r["horizon"] == MAIN_H and r["label"] == "All conditions")
    res["pooled"] = pooled

    # Sharp or fuzzy.
    res["compliance"] = rd.compliance_table(s)
    res["design_main"] = rd.design_type(main)
    res["n_ties"] = int(s["on_cutoff"].sum())
    full = rd.drop_ties(s)
    full = full[full["y"].notna()]
    res["design_full"] = rd.design_type(full)

    rob = []
    rob.append(_est(full, label="All rows incl. <25 cases (fuzzy RD)", fuzzy=True))
    rob.append(_est(rd.donut(main, DONUT), label=f"Donut: drop abs(x) < {DONUT}"))
    if not pooled.get("error"):
        for k in BW_SCALES:
            rob.append(_est(main, label=f"Bandwidth x {k:g}", h=pooled["h"] * k, b=pooled["b"] * k))
    for c in PLACEBO_CUTOFFS:
        rob.append(_est(rd.placebo_sample(main, c), label=f"Placebo cutoff at {c:+.2f}", cutoff=c))
    for r in rob:
        r.update(section="robustness", horizon=MAIN_H, horizon_note=HORIZONS[MAIN_H])
    res["robustness"] = rob

    # Balance: predetermined covariates should not jump at the cutoff. Attrition: the
    # outcome should be just as likely to exist on both sides.
    bal = [_est(main, label=BALANCE[c], y=c) | {"covariate": c} for c in BALANCE]
    att = rd.drop_ties(s)
    att = att[att["meets_min"]]
    att_label = f"Outcome observed in FY t+{MAIN_H} (attrition, 0/1)"
    if att["y_observed"].nunique() < 2:
        bal.append({"label": att_label, "covariate": "y_observed",
                    "error": f"no attrition: the outcome is observed for {att['y_observed'].mean():.0%} of rows"})
    else:
        bal.append(_est(att, label=att_label, y="y_observed") | {"covariate": "y_observed"})
    for c in BALANCE | {"y_observed": ""}:
        src = att if c == "y_observed" else main
        below = src.loc[(src["x"] < 0) & (src["x"] > -pooled.get("h", np.inf)), c].mean()
        for r in bal:
            if r["covariate"] == c:
                r["mean_just_below"] = float(below) if pd.notna(below) else np.nan
    for r in bal:
        r.update(section="balance", horizon=MAIN_H, horizon_note=HORIZONS[MAIN_H])
    res["balance"] = bal

    dens = []
    for label, part in [("All conditions", main)] + [
            (rd.CONDITION_LABELS[c], main[main["condition"] == c]) for c in rd.CONDITION_LABELS]:
        if len(part) < 100:
            continue
        try:
            dens.append({"label": label} | rd.density_test(part["x"]) | {"error": ""})
        except Exception as e:  # noqa: BLE001
            dens.append({"label": label, "error": f"{type(e).__name__}: {e}"})
    res["density"] = pd.DataFrame(dens)
    res["overlap"] = period_overlap(panel, HORIZONS)
    return res


# --- Figures ----------------------------------------------------------------------------------

def figure(df: pd.DataFrame, est: dict, title: str, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    d = df.assign(y_adj=rd.residualize(df))
    h = est["h"]
    width = min(max(2 * h, 0.05), 0.3)
    bins = rd.binned_means(d, "y_adj", width=width, bins_per_side=20)
    fig, ax = plt.subplots(figsize=(6.4, 4.2), dpi=150)
    for side, colour, marker, label in (("below", BLUE, "o", "Not penalized (ERR at or below median)"),
                                        ("above", ORANGE, "s", "Penalized (ERR above median)")):
        b = bins[bins["side"] == side]
        ax.errorbar(b["x_mid"], b["mean"], yerr=1.96 * b["se"], fmt=marker, ms=4.5, color=colour,
                    ecolor=colour, elinewidth=0.8, alpha=0.9, label=label, zorder=3)
        f = rd.local_linear_fit(d, "y_adj", h=h, side=side)
        ax.plot(f["x"], f["fit"], color=colour, lw=2, zorder=4)
        ax.fill_between(f["x"], f["lo"], f["hi"], color=colour, alpha=0.15, lw=0, zorder=2)
    ax.axvline(0, color=MUTED, lw=1, ls="--", zorder=1)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.set_xlabel("ERR minus peer-group median ERR in FY t (running variable)", fontsize=9, color=INK)
    ax.set_ylabel(f"Same condition's ERR in FY t+{MAIN_H}\n(minus condition-year mean, plus overall mean)",
                  fontsize=9, color=INK)
    pct = rd.pct_of_expected
    ax.set_title(f"{title}: jump {pct(est['estimate']):+.2f}% of expected "
                 f"(robust 95% CI {pct(est['ci_low']):+.2f}% to {pct(est['ci_high']):+.2f}%)",
                 fontsize=9.5, color=INK, loc="left")
    ax.legend(fontsize=7.5, frameon=False, loc="best")
    fig.text(0.01, 0.005, f"Dots: bin means with 95% CI. Lines: local-linear fit within bandwidth h = {h:.3f} "
             f"(conventional 95% band). n = {est['n']:,}.", fontsize=6.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def figures(res: dict, fig_dir: Path) -> list[tuple[str, Path]]:
    main = res["horizon_samples"][MAIN_H]["main"]
    ests = {r["label"]: r for r in res["estimates"] if r["horizon"] == MAIN_H and not r.get("error")}
    out = []
    if "All conditions" in ests:
        p = fig_dir / f"rd_all_conditions_t{MAIN_H}.png"
        figure(main, ests["All conditions"], "All conditions", p)
        out.append(("All conditions", p))
    for c, label in rd.CONDITION_LABELS.items():
        if label in ests:
            p = fig_dir / f"rd_{c}_t{MAIN_H}.png"
            figure(main[main["condition"] == c], ests[label], label, p)
            out.append((label, p))
    return out


# --- Report -----------------------------------------------------------------------------------

def _pct(v):
    return "" if pd.isna(v) else f"{rd.pct_of_expected(v):+.2f}%"


def _num(v, fmt="{:.4f}"):
    return "" if v is None or (isinstance(v, float) and np.isnan(v)) else fmt.format(v)


def est_table(rows, pct=True) -> str:
    head = (f"| | {'Jump (ERR)' if pct else 'Jump'} | {'% of expected' if pct else ''} | Robust 95% CI | p (robust) | h | n in h (below / above) | n | Hospitals |\n"
            "|---|---|---|---|---|---|---|---|---|")
    lines = [head]
    for r in rows:
        if r.get("error"):
            lines.append(f"| {r['label']} | not estimated: {r['error']} | | | | | | | |")
            continue
        ci = (f"{_pct(r['ci_low'])} to {_pct(r['ci_high'])}" if pct
              else f"{r['ci_low']:.4f} to {r['ci_high']:.4f}")
        lines.append(
            f"| {r['label']} | {r['estimate']:+.4f} | {_pct(r['estimate']) if pct else ''} | {ci} | "
            f"{r['p_robust']:.3f} | {r['h']:.4f} | {r['n_left']:,} / {r['n_right']:,} | {r['n']:,} | "
            f"{(r['n_clusters'] or 0):,} |")
    return "\n".join(lines) + "\n"


def df_md(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(no rows)_\n"
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(
            (str(v) if col.startswith("fy") or "year" in col
             else f"{v:,}" if isinstance(v, (int, np.integer)) and not isinstance(v, bool)
             else f"{v:.4g}" if isinstance(v, (float, np.floating)) else str(v))
            for col, v in zip(df.columns, row, strict=True)) + " |")
    return "\n".join(lines) + "\n"


def render(res: dict, figs: list[tuple[str, Path]], report_path: Path) -> str:
    p = res["pooled"]
    main = res["horizon_samples"][MAIN_H]["main"]
    years = sorted(main["fiscal_year"].unique())
    out = [
        "# Does a readmission penalty lower that condition's later readmissions?",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.rd_report` from "
        f"`{PANEL}` (payment years up to FY{res['last_year']}). Do not edit by hand; every number below "
        "comes from that run._",
        "",
        "## Bottom line",
        "",
    ]
    if p.get("error"):
        out += [f"The pooled estimate could not be computed: {p['error']}.", ""]
    else:
        r = rd.RDResult(**{k: p[k] for k in rd.RDResult.__dataclass_fields__})
        n_in_h = p["n_left"] + p["n_right"]
        out += [
            rd.effect_sentence(r, MAIN_H),
            "",
            f"- **Who this applies to:** hospital-condition-years with 25+ eligible discharges whose ERR in FY t "
            f"was within {p['h']:.3f} of their peer-group median ({n_in_h:,} of {p['n']:,} rows, "
            f"{n_in_h / p['n']:.0%}), in treatment years FY{years[0]}-FY{years[-1]}. It is the effect of being "
            "*just* over the median versus *just* under it, not the effect of the penalty on all hospitals, and "
            "not the effect on hospitals far above the median (who pay the most).",
            "- **Units:** ERR is predicted / expected readmissions, so a jump of -0.01 in ERR means readmissions "
            "1% of expected lower.",
            f"- **Design:** {res['design_main']} RD (see *Sharp or fuzzy* below), local-linear, triangular kernel, "
            "MSE-optimal bandwidth, robust bias-corrected CI (rdrobust), condition x year fixed effects as "
            "covariates, standard errors clustered by hospital.",
            "",
        ]
    out += [
        "**What it can't rule out**",
        "",
        "- *It is the effect of crossing the line once, not of one year's penalty.* A hospital just above the "
        "median in FY t is also more likely to be above it in FY t+1 and t+2 (their periods overlap), so the "
        "estimate bundles in those later penalties too (an intent-to-treat effect of FY t's status).",
        "- *Timing.* The FY t+3 window starts before the hospital sees its FY t result (see *Timing* below); "
        "the FY t+4 row is the check on that. Hospitals also track their own readmissions all along, so "
        "'being near the line' may matter more than the formal notice.",
        "- *Effects away from the median.* Hospitals far above the median face larger penalties and may respond "
        "more (or less); RD says nothing about them.",
        "- *Spillovers.* A hospital penalized on one condition may improve care for all conditions, including "
        "ones where it was just below the median; that would bias the jump toward zero.",
        "- *Who stays.* If penalized hospitals were more likely to close, merge or lose 25+ cases, the outcome "
        "sample would differ at the cutoff; the attrition row in *Balance* checks this.",
        "- *Six conditions, many checks.* Some per-condition or placebo results will be 'significant' by chance.",
        "",
        "## Sharp or fuzzy?",
        "",
        "CMS counts a condition toward the penalty only if its ERR is **above** the peer-group median **and** "
        "it had at least 25 eligible discharges. So on all rows, crossing the median does not always switch "
        "the penalty on (fuzzy); among rows with 25+ discharges it should (sharp). Penalized share by side, "
        "from CMS's indicator (`penalized_condition`):",
        "",
        df_md(res["compliance"]),
        f"Rows exactly at the median (x = 0, not penalized under 'above'; rdrobust would count them as treated): "
        f"**{res['n_ties']:,}**, dropped. Estimation sample (25+ cases, outcome observed): "
        f"**{res['design_main']}**. All rows: **{res['design_full']}**; its fuzzy RD is in *Robustness*.",
        "",
        "## Timing: do the windows overlap?",
        "",
        "Performance periods from the panel (`perf_start`, `perf_end`). The running variable uses FY t's "
        "window; the outcome uses FY t+h's. CMS sends each hospital its FY t result (Hospital-Specific "
        "Report) in the summer before FY t starts on October 1 (for FY2024: the HSR webinar of 17 August 2023, "
        "https://qualityreportingcenter.com/globalassets/iqr-2023-events/vbp081723/fy-2024-hrrp-hsr-webinar508_.pdf). "
        "Compare that with when the FY t+h window starts: part of a window can come before the hospital "
        "knew its FY t result.",
        "",
        df_md(res["overlap"]),
        "## Estimates",
        "",
    ]
    for h, tag in HORIZONS.items():
        rows = [r for r in res["estimates"] if r["horizon"] == h]
        if not rows:
            out += [f"### FY t+{h} ({tag})", "", "_No rows: the panel has no FY t / FY t+h pairs._", ""]
            continue
        out += [f"### Outcome: ERR in FY t+{h} ({tag})", ""]
        if h == 1:
            out += ["**Contaminated by overlap:** FY t+1's three-year window shares most of its discharges with "
                    "FY t's, so this partly measures the same readmissions that put the hospital over the line. "
                    "Shown for comparison only; do not read it as an effect.", ""]
        out += [est_table(rows), ""]
    out += [
        f"## Validity checks (outcome FY t+{MAIN_H})",
        "",
        "### Density of the running variable at the cutoff (rddensity)",
        "",
        "If hospitals could steer their ERR to just under the median, there would be a pile-up just below 0. "
        "A large p-value means no evidence of that. (No clustering: a hospital counts once per condition-year.)",
        "",
        df_md(res["density"]),
        "### Covariate balance at the cutoff",
        "",
        "Each row is an RD with a predetermined characteristic as the 'outcome': it should not jump. Beds, "
        "ownership and teaching are one FY2026 snapshot per hospital (General Info / cost report).",
        "",
        est_table(res["balance"], pct=False),
        "Mean just below the cutoff (within h), for scale: " + "; ".join(
            f"{r['label']}: {_num(r.get('mean_just_below'), '{:.3g}')}" for r in res["balance"]) + ".",
        "",
        "### Robustness: placebo cutoffs, donut, bandwidth, fuzzy on all rows",
        "",
        "Placebo cutoffs use only one side of the real cutoff, where nothing changes, so they should show no "
        "jump. The donut drops the hospitals closest to the median. Half and double bandwidth scale both h "
        "and the bias bandwidth b.",
        "",
        est_table(res["robustness"]),
        "## Figures",
        "",
    ]
    for label, path in figs:
        rel = path.relative_to(report_path.parent) if path.is_relative_to(report_path.parent) else path
        out += [f"### {label}", "", f"![{label}]({rel.as_posix()})", ""]
    out += [
        "## Files",
        "",
        "- `analysis/output/rd_estimates.csv`: every estimate above, one row each",
        "- `analysis/output/rd_density.csv`, `rd_compliance.csv`, `rd_overlap.csv`",
        "- Method: `hrrp/causal/rd.py` (tests in `tests/test_rd.py`)",
        "",
    ]
    return "\n".join(out)


def write_outputs(res: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = res["estimates"] + res.get("robustness", []) + res.get("balance", [])
    pd.DataFrame(rows).to_csv(out_dir / "rd_estimates.csv", index=False)
    for k in ("density", "compliance", "overlap"):
        if k in res:
            res[k].to_csv(out_dir / f"rd_{k}.csv", index=False)


def main():
    import duckdb

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPORT), help="where to write the report")
    args = ap.parse_args()
    report = Path(args.out)
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    panel, hosp = load(con)
    biggest = int(panel.groupby("fiscal_year")["ccn"].nunique().max() or 0)
    real = report == REPORT
    if biggest < FIXTURE_MAX_HOSPITALS and real:
        sys.exit(f"{C.DB_PATH} has at most {biggest} hospitals in a year: that's the CI fixture, not the real "
                 "data. Not overwriting docs/rd_report.md (pass --out somewhere else to test).")
    res = run(panel, hosp)
    if "pooled" not in res:
        sys.exit(f"No FY t / FY t+{MAIN_H} pairs with FY t >= {rd.FIRST_PEER_MEDIAN_YEAR} in {PANEL} "
                 f"(years loaded: {sorted(int(y) for y in panel['fiscal_year'].unique())}). Load the multi-year panel first "
                 "(panel/mac_steps_multiyear_panel.md). Nothing written.")
    fig_dir = FIG_DIR if real else report.parent / "figures" / "rd"
    out_dir = OUT_DIR if real else report.parent
    figs = figures(res, fig_dir)
    write_outputs(res, out_dir)
    report.write_text(render(res, figs, report))
    print(f"Wrote {report}, {len(figs)} figures in {fig_dir}, CSVs in {out_dir}")
    p = res["pooled"]
    if not p.get("error"):
        print(rd.effect_sentence(rd.RDResult(**{k: p[k] for k in rd.RDResult.__dataclass_fields__}), MAIN_H))


if __name__ == "__main__":
    main()
