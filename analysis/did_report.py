"""Step 7: the Cures Act peer-group reform as a natural experiment (docs/did_report.md).

Run after the multi-year panel is built (make build), and after make rd if you want the
RD comparison filled in:
    python -m analysis.did_report          (or: make did)

1. Treatment intensity: for every hospital in the FY2019 file, the old rule (ERR > 1) and
   the new rule (ERR > peer-group median, times CMS's neutrality modifier) are applied to
   the same FY2019 inputs. dpen = new - old, in percentage points of base DRG payments.
2. Event study (pyfixest): ERR on year x dpen, hospital and condition x year fixed effects,
   errors clustered by hospital, FY2018 the reference year, FY2016 to the last loaded year.
3. Checks: joint test on the leads, placebo fake reform years, dropping hospitals that
   changed peer group, a binary version (penalty went down vs up), year-specific controls
   for the FY2019 ERRs that dpen is built from, hospital x condition fixed effects.
4. Comparison with the RD (analysis/output/rd_estimates.csv, from make rd).

Writes docs/did_report.md, docs/figures/did/*.png and analysis/output/did_*.csv. Every
number in the report comes from this run.
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from hrrp.causal import did

PANEL = "mart.fct_hospital_condition_year"
SUPP = "stg.hrrp_supplemental_history"
CURES_ACT = pd.Timestamp("2016-12-13")   # 21st Century Cures Act signed (Pub. L. 114-255, section 15002)
LEADS = (2016, 2017)
FIXTURE_MAX_HOSPITALS = 500

try:
    from ingest import config as C
    ROOT = C.ROOT
except Exception:  # pragma: no cover
    C = None
    ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "did_report.md"
FIG_DIR = ROOT / "docs" / "figures" / "did"
OUT_DIR = ROOT / "analysis" / "output"
RD_CSV = OUT_DIR / "rd_estimates.csv"

# Same two categorical slots as the RD figures, plus marker shape so series never rely on colour.
BLUE, ORANGE, INK, MUTED, GRID = "#2a78d6", "#eb6834", "#0b0b0b", "#898781", "#e1e0d9"


# --- Data -------------------------------------------------------------------------------------

def load(con) -> tuple[pd.DataFrame, float | None]:
    panel = con.execute(f"""
        SELECT ccn, fiscal_year, condition, err, peer_median_err, eligible_discharges,
               drg_payment_ratio, penalty_indicator, peer_group, dual_proportion,
               payment_adjustment_factor, perf_start, perf_end
        FROM {PANEL}""").df()
    try:
        nm = con.execute(f"""SELECT median(neutrality_modifier) FROM {SUPP}
                             WHERE fiscal_year = {did.REFORM_YEAR}""").fetchone()[0]
    except Exception:  # noqa: BLE001 - the column or table may not exist; we back NM out instead
        nm = None
    return panel, (float(nm) if nm is not None else None)


def periods(panel: pd.DataFrame) -> pd.DataFrame:
    """Each payment year's performance window, months shared with FY2019's, and whether the
    window starts after the Cures Act was signed (when hospitals could first react)."""
    per = (panel.dropna(subset=["perf_start", "perf_end"]).groupby("fiscal_year")[["perf_start", "perf_end"]]
                .agg(lambda s: s.mode().iloc[0]).apply(pd.to_datetime))
    a0, a1 = per.loc[did.REFORM_YEAR] if did.REFORM_YEAR in per.index else (pd.NaT, pd.NaT)
    rows = []
    for t, (b0, b1) in per.iterrows():
        days = max((min(a1, b1) - max(a0, b0)).days + 1, 0) if pd.notna(a0) else np.nan
        timing = ("before the Act" if b1 < CURES_ACT else "after the Act" if b0 >= CURES_ACT
                  else "straddles the Act")
        rows.append({"fy": int(t), "window": f"{b0:%Y-%m}..{b1:%Y-%m}",
                     "months_shared_with_fy2019": round(days / 30.44, 1), "window_vs_cures_act": timing,
                     "includes_2020_or_later": bool(b1 >= pd.Timestamp("2020-01-01"))})
    return pd.DataFrame(rows)


def post_years(per: pd.DataFrame) -> tuple[list[int], list[int]]:
    """(clean_pre_covid, all_clean): years whose window starts after the Act; the first set
    also ends before 2020 (CMS cut FY2022's window at December 2019)."""
    after = per[per["window_vs_cures_act"] == "after the Act"]
    return (after.loc[~after["includes_2020_or_later"], "fy"].tolist(), after["fy"].tolist())


# --- Estimation -------------------------------------------------------------------------------

def check_recompute(panel: pd.DataFrame, nm: float) -> dict:
    """Does the new rule, as coded, reproduce CMS's FY2019 adjustment factors?"""
    r = panel[panel["fiscal_year"] == did.REFORM_YEAR]
    pen = did.new_rule_penalty(r, nm)
    paf = r.groupby("ccn")["payment_adjustment_factor"].first().reindex(pen.index)
    diff = ((1 - pen) - paf).abs()
    ok = paf.notna()
    return {"hospitals": int(ok.sum()), "within_0_0001": int((diff[ok] <= 0.0001 + 1e-9).sum()),
            "within_0_001": int((diff[ok] <= 0.001 + 1e-9).sum()), "max_abs_diff": float(diff[ok].max())}


def _es(df, **kw) -> dict:
    """did.event_study, with a failure kept as a row instead of stopping the run."""
    try:
        return {"es": did.event_study(df, **kw), "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"es": None, "error": f"{type(e).__name__}: {e}", "label": kw.get("label", "")}


def run(panel: pd.DataFrame, nm_file: float | None) -> dict:
    res: dict = {"last_year": int(panel["fiscal_year"].max())}
    r19 = panel[panel["fiscal_year"] == did.REFORM_YEAR]
    res["fy2019"] = {"hospitals": int(r19["ccn"].nunique()),
                     "with_ratio": int(r19.loc[r19["drg_payment_ratio"].notna(), "ccn"].nunique()),
                     "with_peer_group": int(r19.loc[r19["peer_group"].notna(), "ccn"].nunique())}
    nm_back = did.neutrality_modifier_from_paf(r19, r19.groupby("ccn")["payment_adjustment_factor"].first())
    res["nm_backed_out"] = nm_back
    res["nm_file"] = nm_file
    nm = nm_file if nm_file is not None and not np.isnan(nm_file) else nm_back["nm"]
    res["nm"], res["nm_source"] = nm, ("CMS FY2019 supplemental file" if nm_file is not None
                                       else "backed out of CMS's FY2019 adjustment factors")
    if np.isnan(nm) or res["fy2019"]["with_ratio"] == 0:
        res["error"] = ("FY2019 has no DRG payment ratios or no neutrality modifier in the panel, so the rules "
                        "can't be applied")
        return res
    res["recompute"] = check_recompute(panel, nm)

    it = did.treatment_intensity(panel, nm)
    it = it[it["n_counted"] > 0]
    dual = r19.groupby("ccn")["dual_proportion"].first()
    it = it.merge(dual.rename("dual_proportion"), left_on="ccn", right_index=True, how="left")
    res["intensity"] = it
    res["by_group"] = (it.groupby("peer_group").agg(
        hospitals=("ccn", "size"), dual_share_mean=("dual_proportion", "mean"),
        old_rule_pct=("penalty_old", lambda s: 100 * s.mean()), new_rule_pct=("penalty_new", lambda s: 100 * s.mean()),
        dpen_mean_pp=("dpen", "mean"), share_down=("direction", lambda s: (s == "down").mean()),
        share_up=("direction", lambda s: (s == "up").mean()),
        share_unchanged=("direction", lambda s: (s == "unchanged").mean())).reset_index())
    q = it["dpen"].quantile([0.1, 0.25, 0.5, 0.75, 0.9])
    res["dpen_quantiles"] = q
    res["scale_pp"] = float(q.loc[0.75] - q.loc[0.25])

    per = periods(panel)
    res["periods"] = per
    pre_covid, all_post = post_years(per)
    res["post_sets"] = {"pre-COVID": pre_covid, "all": all_post}

    ev = did.build_event_panel(panel, it)
    switchers = did.peer_group_switchers(panel)
    res["n_switchers"] = int(it["ccn"].isin(switchers).sum())
    res["event_panel_rows"] = len(ev)
    specs = [
        ("main", "Main: dpen x year, hospital + condition x year FE", ev, {}),
        ("rule_only", "Rule-only: + year-specific slopes in FY2019 ERR and old-rule penalty", ev,
         {"controls": "rule_only"}),
        ("ccn_cond", "Hospital x condition FE instead of hospital FE", ev, {"fe": "ccn_cond + cell"}),
        ("no_switchers", "Drop hospitals that changed peer group after FY2019", ev[~ev["ccn"].isin(switchers)], {}),
        ("binary", "Binary: penalty went down (1) vs up (0)", ev.dropna(subset=["down"]), {"treat": "down"}),
        ("binary_rule_only", "Binary, rule-only controls", ev.dropna(subset=["down"]),
         {"treat": "down", "controls": "rule_only"}),
    ]
    out = {}
    for key, label, data, kw in specs:
        r = _es(data, label=label, **kw)
        r["label"] = label
        if r["es"] is not None:
            es = r["es"]
            r["pretrend"] = did.wald_test(es, LEADS)
            r["avg"] = {name: did.average_effect(es, yrs) for name, yrs in res["post_sets"].items()}
        out[key] = r
    res["specs"] = out

    pl = []
    for fake in (2017, 2018):
        try:
            pl.append(did.placebo_did(ev, fake))
        except Exception as e:  # noqa: BLE001
            pl.append({"label": f"Fake reform in FY{fake}", "error": f"{type(e).__name__}: {e}"})
    res["placebo"] = pl
    return res


def rd_comparison(path: Path = RD_CSV) -> dict | None:
    """The pooled sharp RD at FY t+3 from analysis/rd_report.py, if it has been run."""
    if not path.exists():
        return None
    d = pd.read_csv(path)
    m = d[(d["section"] == "estimate") & (d["horizon"] == 3) & (d["label"] == "All conditions")]
    return None if m.empty else m.iloc[0].to_dict()


# --- Figures ----------------------------------------------------------------------------------

def _style(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#c3c2b7")
    ax.grid(axis="y", color=GRID, lw=0.6)
    ax.tick_params(colors=MUTED, labelsize=8)


def figure(series: list[tuple[str, did.EventStudy, str, str]], ylabel: str, title: str, path: Path,
           scale: float = 1.0) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.8, 4.2), dpi=150)
    k = len(series)
    for j, (label, es, colour, marker) in enumerate(series):
        c = es.coefs
        x = c["fiscal_year"] + (j - (k - 1) / 2) * 0.18
        y = 100 * scale * c["estimate"]
        lo, hi = 100 * scale * c["ci_low"], 100 * scale * c["ci_high"]
        ax.errorbar(x, y, yerr=[y - lo, hi - y], fmt=marker, ms=5, color=colour, ecolor=colour, elinewidth=1,
                    capsize=0, label=label, zorder=3)
        ax.plot(x, y, color=colour, lw=1, alpha=0.5, zorder=2)
    ax.axhline(0, color=MUTED, lw=0.8, zorder=1)
    ax.axvline(did.REFORM_YEAR - 0.5, color=MUTED, lw=1, ls="--", zorder=1)
    ax.text(did.REFORM_YEAR - 0.45, ax.get_ylim()[1], "peer-group rule starts (FY2019)", fontsize=7, color=MUTED,
            va="top")
    years = sorted(series[0][1].coefs["fiscal_year"])
    ax.set_xticks(years)
    ax.set_xticklabels([f"FY{str(y)[2:]}" for y in years])
    ax.set_xlabel(f"Payment year (FY{did.REF_YEAR} = 0, the reference)", fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK)
    ax.set_title(title, fontsize=9.5, color=INK, loc="left")
    _style(ax)
    ax.legend(fontsize=7.5, frameon=False, loc="lower left")
    fig.text(0.01, 0.005, "Dots: coefficients with 95% CI, errors clustered by hospital. Hospital and condition x "
             "year fixed effects.", fontsize=6.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def intensity_figure(it: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(6.4, 3.8), dpi=150)
    groups = sorted(it["peer_group"].dropna().unique())
    data = [it.loc[it["peer_group"] == g, "dpen"].to_numpy() for g in groups]
    ax.boxplot(data, tick_labels=[f"{int(g)}" for g in groups], showfliers=False, widths=0.5,
               medianprops={"color": ORANGE, "lw": 2}, boxprops={"color": INK, "lw": 0.8},
               whiskerprops={"color": INK, "lw": 0.8}, capprops={"color": INK, "lw": 0.8})
    ax.axhline(0, color=MUTED, lw=0.8, ls="--")
    ax.set_xlabel("FY2019 peer group (1 = fewest dual-eligible patients, 5 = most)", fontsize=9, color=INK)
    ax.set_ylabel("Simulated change in penalty\n(new rule - old rule, pp of base DRG pay)", fontsize=9, color=INK)
    ax.set_title("Same FY2019 ERRs, two rules: who gained and who lost", fontsize=9.5, color=INK, loc="left")
    _style(ax)
    fig.text(0.01, 0.005, "Boxes: middle 50% of hospitals, line = median, whiskers 1.5 IQR (outliers not drawn).",
             fontsize=6.5, color=MUTED)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def figures(res: dict, fig_dir: Path) -> list[tuple[str, Path]]:
    out = []
    p = fig_dir / "did_intensity_by_peer_group.png"
    intensity_figure(res["intensity"], p)
    out.append(("Treatment intensity by peer group", p))
    s = res["specs"]
    scale = res["scale_pp"]
    cont = [(lab, s[k]["es"], col, mk) for k, lab, col, mk in
            (("main", "Main", BLUE, "o"), ("rule_only", "Rule-only controls", ORANGE, "s")) if s[k]["es"]]
    if cont:
        p = fig_dir / "did_event_study.png"
        figure(cont, f"ERR effect of a {scale:.2f} pp bigger penalty\n(% of expected readmissions)",
               f"Event study: ERR on simulated penalty change (scaled to its IQR, {scale:.2f} pp)", p, scale=scale)
        out.append(("Event study, continuous intensity", p))
    binr = [(lab, s[k]["es"], col, mk) for k, lab, col, mk in
            (("binary", "Main", BLUE, "o"), ("binary_rule_only", "Rule-only controls", ORANGE, "s")) if s[k]["es"]]
    if binr:
        p = fig_dir / "did_event_study_binary.png"
        figure(binr, "ERR, penalty-went-down minus went-up\n(% of expected readmissions)",
               "Event study: hospitals whose penalty the reform cut vs raised", p)
        out.append(("Event study, binary (down vs up)", p))
    return out


# --- Report -----------------------------------------------------------------------------------

def _pct(v, scale=1.0):
    return "" if v is None or pd.isna(v) else f"{100 * scale * v:+.2f}%"


def df_md(df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "_(no rows)_\n"
    lines = ["| " + " | ".join(map(str, df.columns)) + " |", "|" + "---|" * len(df.columns)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(
            (str(v) if col in ("fy", "fiscal_year", "peer_group") and not isinstance(v, float)
             else str(int(v)) if col in ("fy", "fiscal_year", "peer_group")
             else f"{v:,}" if isinstance(v, (int, np.integer)) and not isinstance(v, bool)
             else f"{v:.4g}" if isinstance(v, (float, np.floating)) else str(v))
            for col, v in zip(df.columns, row, strict=True)) + " |")
    return "\n".join(lines) + "\n"


def coef_table(res: dict) -> str:
    s = res["specs"]
    keys = [k for k in ("main", "rule_only", "ccn_cond", "no_switchers") if s[k]["es"] is not None]
    years = sorted(s[keys[0]]["es"].coefs["fiscal_year"]) if keys else []
    scale = res["scale_pp"]
    head = "| FY | " + " | ".join(s[k]["label"].split(":")[0] for k in keys) + " |"
    lines = [head, "|---|" + "---|" * len(keys)]
    for yr in years:
        cells = []
        for k in keys:
            c = s[k]["es"].coefs.set_index("fiscal_year")
            if yr not in c.index:
                cells.append("")
                continue
            r = c.loc[yr]
            cells.append("0 (reference)" if yr == did.REF_YEAR else
                         f"{_pct(r['estimate'], scale)} ({_pct(r['ci_low'], scale)} to {_pct(r['ci_high'], scale)})")
        lines.append(f"| FY{yr} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def summary_table(res: dict) -> str:
    scale = res["scale_pp"]
    lines = ["| Specification | Pre-trend test (FY2016, FY2017 = 0) | Pre-COVID post (" +
             ", ".join(f"FY{y}" for y in res["post_sets"]["pre-COVID"]) + ") | All post years (" +
             (f"FY{res['post_sets']['all'][0]}-FY{res['post_sets']['all'][-1]}" if res["post_sets"]["all"] else "") +
             ") | Rows | Hospitals |", "|---|---|---|---|---|---|"]
    for _k, r in res["specs"].items():
        if r["es"] is None:
            lines.append(f"| {r['label']} | not estimated: {r['error']} | | | | |")
            continue
        sc = 1.0 if r["es"].treat == "down" else scale
        pt = r["pretrend"]
        cells = [f"F = {pt['F']:.2f}, p = {pt['p']:.3f}"]
        for name in ("pre-COVID", "all"):
            a = r["avg"][name]
            cells.append("" if not a["years"] else
                         f"{_pct(a['estimate'], sc)} ({_pct(a['ci_low'], sc)} to {_pct(a['ci_high'], sc)}), p = {a['p']:.3f}")
        lines.append(f"| {r['label']} | " + " | ".join(cells) + f" | {r['es'].n:,} | {r['es'].n_clusters:,} |")
    return "\n".join(lines) + "\n"


def verdict(a: dict) -> str:
    return "excludes zero" if (a["ci_low"] > 0 or a["ci_high"] < 0) else "includes zero"


def render(res: dict, figs: list[tuple[str, Path]], report_path: Path, rd_row: dict | None) -> str:
    s, scale, nmb = res["specs"], res["scale_pp"], res["nm_backed_out"]
    main, ro = s["main"], s["rule_only"]
    q = res["dpen_quantiles"]
    it = res["intensity"]
    pre_covid = res["post_sets"]["pre-COVID"]
    rc = res["recompute"]
    out = [
        "# Did the 2019 peer-group reform change readmissions? (Cures Act event study)",
        "",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.did_report` from "
        f"`{PANEL}` (payment years FY{int(res['periods']['fy'].min())}-FY{res['last_year']}). Do not edit by hand; "
        "every number below comes from that run._",
        "",
        "## Bottom line",
        "",
    ]
    for key, tag in (("main", "Main specification"), ("rule_only", "Rule-only specification")):
        r = s[key]
        if r["es"] is None:
            out += [f"- **{tag}:** not estimated ({r['error']}).", ""]
            continue
        a = r["avg"]["pre-COVID"] if pre_covid else r["avg"]["all"]
        out += [f"- **{tag}:** " + did.effect_sentence(a, scale, f"{scale:.2f} percentage points (the middle 50% "
                "range of the simulated change)") +
                f" Pre-trend test on the leads: p = {r['pretrend']['p']:.3f}.", ""]
    if main["es"] is not None and ro["es"] is not None:
        pm, pr = main["pretrend"]["p"], ro["pretrend"]["p"]
        trust = ("Both specifications pass the pre-trend test." if min(pm, pr) >= 0.05 else
                 "The main specification fails the pre-trend test and the rule-only one passes, so read the rule-only "
                 "numbers: the main one is picking up the mechanical link between dpen and FY2019 ERRs (see *Why two "
                 "specifications*)." if pm < 0.05 <= pr else
                 "The rule-only specification fails the pre-trend test, so neither estimate should be read as causal."
                 if pr < 0.05 else "")
        out += [trust, ""]
    out += [
        f"- **Units:** dpen is the simulated change in a hospital's penalty, in percentage points of its base DRG "
        f"payments (new rule minus old rule on the same FY2019 data). Effects are shown for a {scale:.2f} pp change, "
        f"the distance from the 25th to the 75th percentile of dpen. ERR = predicted / expected readmissions, so an "
        "ERR change of -0.01 is 1% of expected fewer readmissions.",
        f"- **Which years count as post:** a payment year's ERR comes from a 3-year window. Only windows that start "
        f"after the Cures Act was signed ({CURES_ACT:%d %B %Y}) can show a response to it; FY2019-FY2021 windows "
        "straddle it. The headline uses the post years whose window also ends before 2020"
        + (f" ({', '.join(f'FY{y}' for y in pre_covid)})" if pre_covid else "") +
        ", because COVID-era windows may hit safety-net hospitals (the reform's winners) differently, which the "
        "condition x year fixed effects can't absorb. The all-years average is in the table.",
        "",
        "## 1. Treatment intensity: two rules, same FY2019 data",
        "",
        "For each hospital in CMS's FY2019 supplemental file, both rules are applied to its FY2019 ERRs, DRG "
        "payment ratios and eligible discharges (only conditions with 25+ count), with the 3% cap:",
        "",
        "- old rule (FY2013-FY2018): `min(3%, sum ratio_c x max(ERR_c - 1, 0))`",
        "- new rule (FY2019 on): `min(3%, NM x sum ratio_c x max(ERR_c - peer median_c, 0))`",
        "",
        f"Neutrality modifier NM = **{res['nm']:.4f}** ({res['nm_source']}). Backed out of CMS's published "
        f"FY2019 adjustment factors as (1 - factor) / sum of excess terms, it is {nmb['nm']:.4f} (median over "
        f"{nmb['n']:,} hospitals with a reduction of 0.1% to 3%; 5th-95th percentile {nmb['p05']:.4f}-"
        f"{nmb['p95']:.4f}, the spread coming from CMS rounding factors to 4 decimals).",
        "",
        f"**Check that the new rule is coded right:** recomputing FY2019 adjustment factors from these inputs "
        f"matches CMS's published factor within 0.0001 (CMS's rounding) for **{rc['within_0_0001']:,} of "
        f"{rc['hospitals']:,}** hospitals, and within 0.001 for {rc['within_0_001']:,} (largest gap "
        f"{rc['max_abs_diff']:.4f}).",
        "",
        f"FY2019 file: {res['fy2019']['hospitals']:,} hospitals, {res['fy2019']['with_ratio']:,} with DRG payment "
        f"ratios, {res['fy2019']['with_peer_group']:,} with a peer group. Hospitals with at least one condition "
        f"that counts (25+ cases): **{len(it):,}**. Penalty went down: {(it['direction'] == 'down').sum():,}; up: "
        f"{(it['direction'] == 'up').sum():,}; unchanged (no penalty under either rule, or exactly equal): "
        f"{(it['direction'] == 'unchanged').sum():,}.",
        "",
        "dpen percentiles (pp): " + ", ".join(f"p{int(k * 100)} {v:+.3f}" for k, v in q.items()) + ".",
        "",
        "By FY2019 peer group (means; penalties in % of base DRG payments):",
        "",
        df_md(res["by_group"]),
        "## 2. Event study",
        "",
        "`ERR_ict = sum_k b_k 1{year = k} x dpen_i + hospital_i + condition x year_ct + e_ict`, FY2018 omitted, "
        "pyfixest `feols`, errors clustered by hospital. Rows are hospital x condition x payment year with an ERR, "
        f"for hospitals with a dpen ({res['event_panel_rows']:,} rows). Leads (FY2016, FY2017) test for "
        "pre-trends; FY2019 on traces the response. A negative coefficient means a bigger reform-driven penalty "
        "went with lower readmissions.",
        "",
        "### Why two specifications",
        "",
        "dpen is computed from FY2019 ERRs, and the FY2017-FY2021 windows share discharges with FY2019's (table "
        "below). A hospital with an unlucky FY2019 has a higher ERR in FY2019 by construction and a lower one later "
        "(mean reversion), and its dpen depends on that luck. So the FY2019 coefficient is mechanical, not an effect, "
        "and neighbouring years can be too. The **rule-only** specification adds year-specific slopes in the "
        "hospital's own FY2019 ERR for the condition and in its old-rule penalty. What is left to move dpen is the "
        "peer-group median, i.e. the rule.",
        "",
        df_md(res["periods"]),
        "### Coefficients",
        "",
        f"Effect of a {scale:.2f} pp bigger simulated penalty on ERR, as % of expected readmissions (95% CI):",
        "",
        coef_table(res),
        "### Summary and checks",
        "",
        "Pre-trend test: joint F-test that the FY2016 and FY2017 coefficients are 0 (cluster-robust). Post "
        f"averages: mean of the yearly coefficients (continuous rows scaled to {scale:.2f} pp; binary rows are "
        "the down-minus-up gap in ERR). In the binary rows a **positive** number is the expected sign: hospitals "
        "whose penalty fell would ease off and readmit more.",
        "",
        summary_table(res),
        f"Hospitals that changed peer group after FY2019 (dropped in that row): **{res['n_switchers']:,}** of "
        f"{len(it):,}. Peer groups are quintiles of the dual share, recomputed every year, so hospitals near a "
        "boundary move; their real exposure after FY2019 differs from the simulated one.",
        "",
        "### Placebo: pretend the reform happened earlier",
        "",
        "FY2016-FY2018 only (all under the old rule), dpen x 1{year >= fake year}, same fixed effects. There was no "
        "reform then, so the coefficient should be 0 (per pp of dpen, as % of expected readmissions):",
        "",
    ]
    lines = ["| Placebo | Estimate | 95% CI | p | Rows | Hospitals |", "|---|---|---|---|---|---|"]
    for p in res["placebo"]:
        if p.get("error"):
            lines.append(f"| {p['label']} | not estimated: {p['error']} | | | | |")
        else:
            lines.append(f"| {p['label']} | {_pct(p['estimate'])} | {_pct(p['ci_low'])} to {_pct(p['ci_high'])} | "
                         f"{p['p']:.3f} | {p['n']:,} | {p['n_clusters']:,} |")
    out += ["\n".join(lines), ""]

    out += ["## 3. Compared with the RD", ""]
    if rd_row is None:
        out += ["_analysis/output/rd_estimates.csv not found: run `make rd` first, then this report again._", ""]
    else:
        out += [
            f"The regression discontinuity (`docs/rd_report.md`) found that being just above the peer-group median "
            f"rather than just below changes the same condition's ERR three years later by "
            f"**{_pct(rd_row['estimate'])}** of expected (robust 95% CI {_pct(rd_row['ci_low'])} to "
            f"{_pct(rd_row['ci_high'])}, {int(rd_row['n']):,} rows).",
            "",
        ]
        a = ro["avg"]["pre-COVID" if pre_covid else "all"] if ro["es"] is not None else None
        if a is not None:
            out += [f"The event study (rule-only) gives {_pct(a['estimate'], scale)} for a {scale:.2f} pp bigger "
                    f"penalty (95% CI {_pct(a['ci_low'], scale)} to {_pct(a['ci_high'], scale)}; it "
                    f"{verdict(a)}).", ""]
    out += [
        "They answer different questions, so they can disagree without either being wrong:",
        "",
        "- **Local vs average.** The RD is the effect for conditions right at the median, where CMS's formula "
        "charges almost nothing (the penalty grows with ERR minus the median, so just above it the money is close "
        "to 0). It measures being *flagged*. The event study averages over every hospital and is driven by how "
        "many *dollars* the rule moved: the effect of the size of the penalty, not of crossing a line.",
        "- **Different hospitals.** The RD's information comes from hospitals near the median for some condition; "
        "the event study's from hospitals the reform moved most, which are those far from the median in "
        "peer groups 1 and 5 (lowest and highest dual share). If safety-net hospitals respond differently "
        "(fewer resources to cut readmissions), the two average over different people.",
        "- **Condition vs hospital.** RD compares conditions within the same year; the penalty change here is "
        "hospital-wide, so a hospital-wide response (a discharge-planning program that helps every condition) "
        "shows up here but is differenced away in the RD.",
        "- **Timing.** RD looks three payment years after one year's status. The event study follows a permanent "
        "rule change for up to eight years.",
        "- **Assumptions.** RD needs no manipulation at the median (the density test passed); the event study needs "
        "parallel trends between hospitals the reform helped and hurt, which the lead test checks only for "
        "FY2016-FY2017, and it can be thrown off by anything else that hit safety-net hospitals after 2017 (COVID, "
        "Medicaid expansion timing).",
        "",
        "## What it can't rule out",
        "",
        "- Only two clean leads (FY2016, FY2017): a short pre-period gives the pre-trend test little power.",
        "- dpen is built from FY2019 *outcomes*. The rule-only controls handle the linear part of mean reversion; a "
        "non-linear part would remain.",
        "- The reform was public in December 2016 and CMS finalized the method in the FY2018 IPPS rule (August "
        "2017); hospitals may have reacted at either date, or only once they saw their FY2019 report in 2018.",
        "- Hospitals that closed or merged after FY2019 leave the panel; if that depends on dpen it biases the "
        "later years.",
        "- Five specifications, two placebo years, many years: some coefficients will cross p < 0.05 by chance.",
        "",
        "## Figures",
        "",
    ]
    for label, path in figs:
        rel = path.relative_to(report_path.parent) if path.is_relative_to(report_path.parent) else path
        out += [f"### {label}", "", f"![{label}]({rel.as_posix()})", ""]
    out += [
        "## Files",
        "",
        "- `analysis/output/did_intensity.csv`: one row per hospital (old and new penalty, dpen, peer group)",
        "- `analysis/output/did_event_study.csv`: every coefficient of every specification",
        "- `analysis/output/did_tests.csv`: pre-trend tests, post averages, placebos",
        "- Method: `hrrp/causal/did.py` (tests on simulated panels with a known effect in `tests/test_did.py`)",
        "",
    ]
    return "\n".join(out)


def write_outputs(res: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    res["intensity"].to_csv(out_dir / "did_intensity.csv", index=False)
    coefs, tests = [], []
    for key, r in res["specs"].items():
        if r["es"] is None:
            tests.append({"spec": key, "label": r["label"], "test": "error", "error": r["error"]})
            continue
        coefs.append(r["es"].coefs.assign(spec=key, label=r["label"], treat=r["es"].treat))
        tests.append({"spec": key, "label": r["label"], "test": "pretrend", **{k: v for k, v in r["pretrend"].items()
                                                                              if k != "years"},
                      "years": " ".join(map(str, r["pretrend"]["years"]))})
        for name, a in r["avg"].items():
            tests.append({"spec": key, "label": r["label"], "test": f"post_avg_{name}",
                          **{k: v for k, v in a.items() if k != "years"}, "years": " ".join(map(str, a["years"]))})
    for p in res["placebo"]:
        tests.append({"spec": "main", "test": "placebo", **p})
    pd.concat(coefs).to_csv(out_dir / "did_event_study.csv", index=False)
    pd.DataFrame(tests).to_csv(out_dir / "did_tests.csv", index=False)


def main():
    import duckdb

    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(REPORT), help="where to write the report")
    args = ap.parse_args()
    report = Path(args.out)
    con = duckdb.connect(str(C.DB_PATH), read_only=True)
    panel, nm_file = load(con)
    biggest = int(panel.groupby("fiscal_year")["ccn"].nunique().max() or 0)
    real = report == REPORT
    if biggest < FIXTURE_MAX_HOSPITALS and real:
        sys.exit(f"{C.DB_PATH} has at most {biggest} hospitals in a year: that's the CI fixture, not the real "
                 "data. Not overwriting docs/did_report.md (pass --out somewhere else to test).")
    years = sorted(int(y) for y in panel["fiscal_year"].unique())
    if did.REFORM_YEAR not in years or did.REF_YEAR not in years:
        sys.exit(f"Need FY{did.REF_YEAR} and FY{did.REFORM_YEAR} in {PANEL}; loaded: {years}. Load the multi-year "
                 "panel first (panel/mac_steps_multiyear_panel.md). Nothing written.")
    res = run(panel, nm_file)
    if res.get("error"):
        sys.exit(res["error"] + ". Nothing written.")
    fig_dir = FIG_DIR if real else report.parent / "figures" / "did"
    out_dir = OUT_DIR if real else report.parent
    figs = figures(res, fig_dir)
    write_outputs(res, out_dir)
    report.write_text(render(res, figs, report, rd_comparison()))
    print(f"Wrote {report}, {len(figs)} figures in {fig_dir}, CSVs in {out_dir}")
    rc = res["recompute"]
    print(f"NM {res['nm']:.4f} ({res['nm_source']}); FY2019 factor recompute matches CMS for "
          f"{rc['within_0_0001']:,}/{rc['hospitals']:,} hospitals")
    for key in ("main", "rule_only"):
        r = res["specs"][key]
        if r["es"] is not None:
            a = r["avg"]["pre-COVID"] if res["post_sets"]["pre-COVID"] else r["avg"]["all"]
            print(f"{key}: pre-trend p = {r['pretrend']['p']:.3f}; " +
                  did.effect_sentence(a, res["scale_pp"], f"{res['scale_pp']:.2f} pp"))


if __name__ == "__main__":
    main()
