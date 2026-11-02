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

from ingest import config as C
from models.build import md_table

REPORT = C.ROOT / "docs" / "penalty_report.md"
OUT = C.ROOT / "analysis" / "output"
RULE_DIR = C.RAW / "ipps_fy2026_final_rule_text"


def cms_rule_passages(limit=40):
    """Sentences from the FY2026 final rule that mention HRRP and a $ figure or hospital count."""
    files = sorted(RULE_DIR.glob("*.htm*"))
    if not files:
        return None
    text = html.unescape(re.sub(r"<[^>]+>", " ", files[0].read_text(errors="ignore")))
    text = re.sub(r"\s+", " ", text)
    sentences = re.split(r"(?<=[.;])\s+(?=[A-Z(])", text)
    topic = re.compile(r"readmission", re.I)
    figure = re.compile(r"\$\s?[\d.,]+\s*(million|billion)|[\d.,]+\s+(million|billion)\b|"
                        r"\b[\d,]{3,}\s+hospitals\b|percent of (eligible |applicable )?hospitals", re.I)
    hits, seen = [], set()
    for s in sentences:
        if topic.search(s) and figure.search(s) and len(s) < 1200 and s not in seen:
            seen.add(s)
            hits.append(s.strip())
    return hits[:limit]


def main():
    con = duckdb.connect(str(C.DB_PATH))
    con.execute((C.ROOT / "analysis" / "penalty_summaries.sql").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    tables = ["national", "by_state", "by_ownership", "by_system", "by_condition",
              "by_system_condition", "massachusetts", "cms_file_counts"]
    for t in tables:
        con.execute(f"COPY analysis.{t} TO '{OUT / (t + '.csv')}' (HEADER)")
    con.execute(f"COPY mart.hospital_penalty_wide TO '{OUT / 'hospital_penalty.csv'}' (HEADER)")

    passages = cms_rule_passages()
    cms_block = ("_Final rule text not downloaded; run `python -m ingest.download`._" if passages is None
                 else "\n".join(f"> {p}\n" for p in passages) or "_No matching sentences found._")

    failed = con.execute("SELECT count(*) FROM qa.assertions WHERE failing_rows > 0").fetchone()[0]
    parts = [
        "# FY2026 HRRP penalty estimate",
        f"_Generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC by `python -m analysis.penalty_report`. "
        "Method and assumptions: [penalty_method.md](penalty_method.md). "
        f"Data-quality assertions failing: {failed}._",
        "## National", md_table(con, "SELECT * FROM analysis.national"),
        "## Check against CMS",
        "### Counts in CMS's own FY2026 supplemental file", md_table(con, "SELECT * FROM analysis.cms_file_counts"),
        "### Does the formula reproduce CMS's factor?",
        md_table(con, "SELECT test, failing_rows FROM qa.assertions WHERE test LIKE 'recomputed factor%'"),
        "### What the FY2026 final rule says (verbatim sentences mentioning readmissions with a $ amount or hospital count)",
        cms_block,
        "## By condition", md_table(con, "SELECT * FROM analysis.by_condition"),
        "## By parent system", md_table(con, "SELECT * FROM analysis.by_system"),
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
