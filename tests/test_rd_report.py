"""analysis/rd_report.py end to end on a hand-built panel (a smoke test: it runs and writes
every section). The panel is a deterministic formula, not data; its numbers mean nothing."""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("rdrobust")
pytest.importorskip("rddensity")

from analysis import rd_report  # noqa: E402


def hand_built_panel(n_hosp=400, years=range(2016, 2025)):
    rows = []
    for i in range(n_hosp):
        level = 0.2 * ((i * 37 % n_hosp) / n_hosp - 0.5)       # spread of ERRs around 1
        for t in years:
            err = 1 + level + 0.01 * np.sin(1.7 * i + 2.3 * t)
            median = 1.0 if t >= 2019 else None
            disch = 10 if i % 10 == 0 else 100                     # every 10th hospital is low volume
            pen = (err > 1 and disch >= 25) if t >= 2019 else err > 1
            rows.append((f"{i:06d}", t, "hf", err, median, disch, pen, 0.2 + 0.001 * (i % 50),
                         pd.Timestamp(t - 5, 7, 1), pd.Timestamp(t - 2, 6, 30)))
    cols = ["ccn", "fiscal_year", "condition", "err", "peer_median_err", "eligible_discharges",
            "penalized_condition", "dual_proportion", "perf_start", "perf_end"]
    panel = pd.DataFrame(rows, columns=cols)
    hosp = pd.DataFrame({"ccn": [f"{i:06d}" for i in range(n_hosp)],
                         "beds": [50 + (i * 13) % 400 for i in range(n_hosp)],
                         "is_teaching": [i % 3 == 0 for i in range(n_hosp)],
                         "hospital_ownership": ["Proprietary" if i % 4 == 0 else "Government - Local" if i % 4 == 1
                                                else "Voluntary non-profit - Private" for i in range(n_hosp)]})
    return panel, hosp


def test_report_runs_and_has_every_section(tmp_path):
    panel, hosp = hand_built_panel()
    res = rd_report.run(panel, hosp)
    assert res["design_main"] == "sharp" and res["design_full"] == "fuzzy"
    ov = res["overlap"].set_index(["horizon", "fy_t"])
    assert ov.loc[(3, 2019), "overlap_months"] == 0           # 3-year windows, 3 years apart
    assert ov.loc[(1, 2019), "overlap_months"] > 20           # t+1 shares two of three years
    report = tmp_path / "rd_report.md"
    figs = rd_report.figures(res, tmp_path / "figures" / "rd")
    rd_report.write_outputs(res, tmp_path)
    text = rd_report.render(res, figs, report)
    for heading in ("## Bottom line", "## Sharp or fuzzy?", "## Timing", "FY t+1 (contaminated by overlap)",
                    "### Density", "### Covariate balance", "Placebo cutoff at -0.05", "Donut",
                    "Bandwidth x 0.5", "fuzzy RD", "## Figures"):
        assert heading in text, heading
    assert all(p.exists() for _, p in figs) and len(figs) == 2  # pooled + heart failure
    assert (tmp_path / "rd_estimates.csv").exists()
