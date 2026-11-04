"""Tests for the multi-year ingest helpers (no downloads).

The spreadsheet test uses the real FY2026 CMS rows already in tests/fixtures/raw/,
written back out with the column headers CMS used (from column_mapping_log.csv).
"""
import pandas as pd
import pytest

from ingest import config as C
from ingest import download as D
from ingest import load as L

FX = C.ROOT / "tests" / "fixtures" / "raw"


def test_every_year_fy2016_to_fy2027_is_configured():
    assert sorted(C.HRRP_YEARS) == list(range(2016, 2028))
    for fy, spec in C.HRRP_YEARS.items():
        start, end = spec["period"]
        assert start < end, fy
        assert spec["period_checked"] in {"file", "cms", "rule"}, fy
        assert spec["landing_page"].startswith("https://www.cms.gov/"), fy
        if spec["period_checked"] == "cms":
            assert spec.get("period_source", "").startswith("https://"), f"FY{fy}: say which document"


def test_periods_follow_cms_rules():
    # FY2027 is the first 2-year period; FY2022 stops at Dec 1, 2019 (COVID-19 exception).
    assert C.HRRP_YEARS[2027]["period"] == ("2023-07-01", "2025-06-30")
    assert C.HRRP_YEARS[2022]["period"] == ("2017-07-01", "2019-12-01")
    # Every other year is a 3-year window ending June 30 two years before the FY.
    for fy, spec in C.HRRP_YEARS.items():
        if fy in (2022, 2027):
            continue
        assert spec["period"] == (f"{fy - 5}-07-01", f"{fy - 2}-06-30"), fy


def test_zip_links_on_landing_page(monkeypatch):
    html = ('<a href="/files/zip/fy-2023-hrrp-supplemental-data-file.zip-0">ZIP</a>'
            '<a href="https://www.cms.gov/files/zip/other.zip">x</a><a href="/page">no</a>')

    class R:
        text = html
    monkeypatch.setattr(D, "_get", lambda url, **kw: R())
    links = D.zip_links_on("https://www.cms.gov/some/landing-page")
    assert links == ["https://www.cms.gov/files/zip/fy-2023-hrrp-supplemental-data-file.zip-0",
                     "https://www.cms.gov/files/zip/other.zip"]


def test_unique_norm_keeps_duplicate_headers_apart():
    assert L._unique_norm(["ERR for AMI", "ERR for AMI", "Hospital CCN"]) == [
        "err_for_ami", "err_for_ami_2", "hospital_ccn"]


@pytest.mark.parametrize("member, end_date, fy", [
    ("FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv", "06/30/2024", 2026),
    ("Hospital_Readmissions_Reduction_Program.csv", "12/01/2019", 2022),   # by End Date
    ("Hospital_Readmissions_Reduction_Program.csv", "06/30/2017", 2019),
    ("Hospital_Readmissions_Reduction_Program.csv", "03/31/2018", None),   # unknown -> skipped
])
def test_fiscal_year_of_a_pdc_file(member, end_date, fy):
    df = pd.DataFrame({"end_date": [end_date, end_date]})
    assert L._fy_from_pdc(member, df) == fy


def test_pick_sheet_on_real_fy2026_rows(tmp_path):
    log = pd.read_csv(FX / "column_mapping_log.csv", dtype=str)
    original = {L.norm(m): m for m in log.query("source == 'hrrp_supplemental'").matched_column.dropna()}
    df = pd.read_csv(FX / "hrrp_supplemental_original.csv", dtype=str, keep_default_na=False)
    df.columns = [original[c] for c in df.columns]
    df.to_csv(tmp_path / "fy2026.csv", index=False)
    label, sheet, ccn_col = L.pick_sheet(tmp_path)
    assert ccn_col == "Hospital CCN"
    assert len(sheet) == len(df)
    assert "ERR for AMI" in sheet.columns


def test_years_named_in_cms_file_names():
    # Real names from CMS's zips (FY2016, FY2019, FY2026, and the FY2024 file that the
    # FY2023 archive link served).
    assert L.years_named("FY 2016 IPPS Final Rule Readmissions PUF revised 08-04-15.xlsx:Final Rule FY 2016") == {2016}
    assert L.years_named("fy_2019_ipps_final_rule_hrrp_supplemental_file.xlsx:FR FY 2019") == {2019}
    assert L.years_named("FY2026_HRRP_Supplemental_File.xlsx:FR FY 2026") == {2026}
    assert L.years_named("FY2024_Final_Rule_Supplemental_File.xlsx:FR FY 2024") == {2024}
    assert L.years_named("Supplemental.xlsx:Sheet1") == set()


def test_fy2023_does_not_use_the_link_that_serves_fy2024():
    assert not any(u.endswith(".zip-0") for u in C.HRRP_YEARS[2023]["supplemental_urls"])
