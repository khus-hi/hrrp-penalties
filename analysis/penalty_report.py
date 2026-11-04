"""Step 4: summarise the FY2026 HRRP penalty estimate and compare it with CMS.

Run after models.build:   python -m analysis.penalty_report
Writes docs/penalty_report.md and CSVs in analysis/output/ (for Tableau/Power BI later).

The comparison with CMS quotes CMS's own words: it pulls every sentence in the FY2026
IPPS final rule text that mentions readmissions together with a dollar amount or a
hospital count, so the report never relies on a number typed in by hand.
"""
import html
import re
from datetime import datetime, timezone

import duckdb
import pandas as pd

from ingest import config as C
from models.build import md_table

REPORT = C.ROOT / "docs" / "penalty_report.md"
OUT = C.ROOT / "analysis" / "output"
RULE_DIR = C.RAW / "ipps_fy2026_final_rule_text"


def cms_rule_passages(window=700, limit=30):
    """Text around every mention of the HRRP in the FY2026 final rule that also contains
    a dollar amount or a hospital count. Returns (diagnostics, passages)."""
    files = sorted(p for p in RULE_DIR.glob("*") if p.is_file())
    if not files:
        return None, None
    raw = files[0].read_text(errors="ignore")
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", raw)))
    mentions = [m.start() for m in re.finditer(r"Readmissions? Reduction Program|HRRP", text)]
    figure = re.compile(r"\$\s?[\d.,]+\s*(million|billion)|\b[\d.,]+\s+(million|billion)\b|"
                        r"\b\d{1,2},\d{3}\s+hospitals\b|\b\d{3,4}\s+hospitals\b", re.I)
    passages, last_end = [], -1
    for pos in mentions:
        start, end = max(0, pos - window // 3), min(len(text), pos + window)
        if start < last_end:  # skip overlapping windows
            continue
        chunk = text[start:end]
        if figure.search(chunk):
            passages.append("..." + chunk.strip() + "...")
            last_end = end
    diag = {"file": files[0].name, "characters": len(text), "hrrp_mentions": len(mentions),
            "passages_with_figures": len(passages)}
    return diag, passages[:limit]


INTERVALS = OUT / "penalty_interval.csv"


def interval_block(level: str) -> str:
    """90% Monte Carlo interval rows from analysis.penalty_uncertainty, as a markdown table."""
    if not INTERVALS.exists():
        return "_90% interval not computed yet: run `python -m analysis.penalty_uncertainty` before this report._"
    t = pd.read_csv(INTERVALS)
    t = t[t.level == level]
    same = t[t.population == "same hospitals as the point estimate"].set_index("name")
    full = t[t.population == "all penalized hospitals"].set_index("name")
    m = lambda v: f"${v / 1e6:,.1f}M"
    rows = ["| | Point estimate | 90% interval, same hospitals | Contains point | 90% interval, all penalized hospitals |",
            "|---|---|---|---|---|"]
    for name, r in same.iterrows():
        f = full.loc[name]
        rows.append(f"| {name} | {m(r.point_estimate_usd)} | {m(r.p5_usd)} to {m(r.p95_usd)} | "
                    f"{'yes' if r.interval_contains_point else '**no**'} | {m(f.p5_usd)} to {m(f.p95_usd)} |")
    return ("\n".join(rows) + "\n\n\"Same hospitals\" covers only hospitals with a usable cost-report base, like the "
            "point estimate. \"All penalized hospitals\" also estimates a base for the penalized hospitals that have "
            "none, so it sits higher. Method: [penalty_uncertainty.md](penalty_uncertainty.md).")


def main():
    con = duckdb.connect(str(C.DB_PATH))
    con.execute((C.ROOT / "analysis" / "penalty_summaries.sql").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    tables = ["national", "by_state", "by_ownership", "by_system", "by_condition",
              "by_system_condition", "massachusetts", "cms_file_counts"]
    for t in tables:
        con.execute(f"COPY analysis.{t} TO '{OUT / (t + '.csv')}' (HEADER)")
    con.execute(f"COPY mart.hospital_penalty_wide TO '{OUT / 'hospital_penalty.csv'}' (HEADER)")

    diag, passages = cms_rule_passages()
    if diag is None:
        cms_block = "_Final rule text not downloaded; run `python -m ingest.download`._"
    else:
        cms_block = (f"_Searched {diag['file']}: {diag['characters']:,} characters, "
                     f"{diag['hrrp_mentions']} HRRP mentions, {diag['passages_with_figures']} with a $ or hospital count._\n\n"
                     + ("\n".join(f"> {p}\n" for p in passages) or "_No matching passages found._"))

    failed = con.execute("SELECT count(*) FROM qa.assertions WHERE failing_rows > 0").fetchone()[0]
    parts = [
        "# FY2026 HRRP penalty estimate",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.penalty_report`. "
        "Method and assumptions: [penalty_method.md](penalty_method.md). "
        f"Data-quality assertions failing: {failed}._",
        "## National", md_table(con, "SELECT * FROM analysis.national"),
        "### Uncertainty: 90% interval for the national total", interval_block("national"),
        "## Check against CMS",
        "### Counts in CMS's own FY2026 supplemental file", md_table(con, "SELECT * FROM analysis.cms_file_counts"),
        "### Does the formula reproduce CMS's factor?",
        md_table(con, "SELECT * FROM qa.paf_recompute_summary"),
        "CMS penalty indicator values by condition:",
        md_table(con, "SELECT * FROM qa.penalty_indicator_values"),
        "### What the FY2026 final rule says (verbatim text around HRRP mentions that include a $ amount or hospital count)",
        cms_block,
        "## By condition", md_table(con, "SELECT * FROM analysis.by_condition"),
        "90% intervals by condition:", interval_block("condition"),
        "## By parent system", md_table(con, "SELECT * FROM analysis.by_system"),
        "90% intervals by chain:", interval_block("group"),
        md_table(con, "SELECT * FROM analysis.by_system_condition WHERE parent_system <> 'Not one of the four chains'"),
        "## By ownership type", md_table(con, "SELECT * FROM analysis.by_ownership"),
        "## By state", md_table(con, "SELECT * FROM analysis.by_state"),
        "## Massachusetts: every hospital", md_table(con, "SELECT * FROM analysis.massachusetts"),
    ]
    REPORT.write_text("\n\n".join(parts))
    print(con.sql("SELECT * FROM analysis.national"))
    print(f"Report: {REPORT}\nCSVs:   {OUT}")
    con.close()


if __name__ == "__main__":
    main()
