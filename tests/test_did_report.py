"""analysis/did_report.py end to end on a SIMULATED panel (a smoke test: it runs, the rule
recompute matches, and every section is written). Its numbers mean nothing."""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyfixest")

from test_did import NM_TRUE, simulate  # noqa: E402  (pytest puts tests/ on sys.path)

from analysis import did_report  # noqa: E402
from hrrp.causal import did  # noqa: E402


def report_panel():
    p = simulate(n_hosp=600, beta={2022: -0.02, 2023: -0.02, 2024: -0.02}, seed=21)
    years = sorted(p["fiscal_year"].unique())
    starts = {t: pd.Timestamp(t - 5, 7, 1) for t in years}
    ends = {t: pd.Timestamp(t - 2, 6, 30) for t in years}
    ends[2022] = pd.Timestamp(2019, 12, 1)   # CMS cut FY2022's window at December 2019
    p["perf_start"] = p["fiscal_year"].map(starts)
    p["perf_end"] = p["fiscal_year"].map(ends)
    p["penalty_indicator"] = None
    r19 = p[p["fiscal_year"] == 2019]
    paf = (1 - did.new_rule_penalty(r19, NM_TRUE)).round(4)
    p["payment_adjustment_factor"] = np.where(p["fiscal_year"] == 2019, p["ccn"].map(paf), np.nan)
    p["dual_proportion"] = p["peer_group"] / 10
    return p


def test_report_runs_and_has_every_section(tmp_path):
    panel = report_panel()
    res = did_report.run(panel, None)
    assert "error" not in res
    assert res["nm"] == pytest.approx(NM_TRUE, abs=0.005)
    rc = res["recompute"]
    assert rc["within_0_001"] == rc["hospitals"]
    assert res["post_sets"]["pre-COVID"] == [2022]
    assert res["post_sets"]["all"] == [2022, 2023, 2024]
    per = res["periods"].set_index("fy")
    assert per.loc[2018, "window_vs_cures_act"] == "before the Act"
    assert per.loc[2020, "window_vs_cures_act"] == "straddles the Act"
    figs = did_report.figures(res, tmp_path / "figures" / "did")
    did_report.write_outputs(res, tmp_path)
    rd_row = {"estimate": 0.0003, "ci_low": -0.0026, "ci_high": 0.0036, "n": 71674}
    text = did_report.render(res, figs, tmp_path / "did_report.md", rd_row)
    for heading in ("## Bottom line", "## 1. Treatment intensity", "## 2. Event study", "### Why two specifications",
                    "### Placebo", "## 3. Compared with the RD", "Rule-only", "Binary", "Drop hospitals that changed",
                    "## Figures"):
        assert heading in text, heading
    assert len(figs) == 3 and all(p.exists() for _, p in figs)
    for f in ("did_intensity.csv", "did_event_study.csv", "did_tests.csv"):
        assert (tmp_path / f).exists()
