"""Every source URL in one place.

Each entry was checked against the official page on 2026-11-01 (see docs/data_sources.md).
"verified" says what was confirmed live; anything not confirmed is flagged so the
pipeline can check it on first download rather than trusting it blindly.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
# HRRP_DB_PATH lets CI point every script (and dbt) at the small fixture database
# instead of the full one, without changing any code.
DB_PATH = Path(os.getenv("HRRP_DB_PATH", ROOT / "data" / "hrrp.duckdb"))

PROGRAM_YEAR = 2026  # HRRP payment year = federal FY2026 (Oct 1 2025 to Sep 30 2026)

# --- Plain file downloads -------------------------------------------------------
FILES = {
    # CMS Provider Data Catalog. URLs come from the dataset metastore API, which we
    # re-query at download time so a CMS refresh doesn't break the pipeline.
    "hrrp_hospital": {
        "metastore_id": "9n3s-kdb3",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "a171bc36c488d3e0dc33ec63abb469a6_1770163617/"
        "FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv",
        "verified": "columns + row count via datastore API",
    },
    "hospital_general_info": {
        "metastore_id": "xubh-q36u",
        "fallback_url": "https://data.cms.gov/provider-data/sites/default/files/resources/"
        "893c372430d9d71a1c52737d01239d47_1785189955/Hospital_General_Information.csv",
        "verified": "columns + row count via datastore API",
    },
    # FY2026 IPPS final rule (CMS-1833-F) HRRP files.
    "hrrp_supplemental": {
        "url": "https://www.cms.gov/files/zip/fy2026-hospital-readmissions-reduction-program-supplemental-data-file.zip",
        "verified": "link on FY2026 IPPS final rule page; columns NOT yet seen (zip)",
    },
    "hrrp_table15": {
        "url": "https://www.cms.gov/files/zip/fy-2026-hospital-readmissions-reduction-program-payment-adjustment-factors.zip",
        "verified": "link on FY2026 IPPS final rule page; columns NOT yet seen (zip)",
    },
    "ipps_impact_file": {
        "url": "https://www.cms.gov/files/zip/fy2026-ipps-fr-impact-file.zip",
        "verified": "link on FY2026 IPPS final rule page; loaded to raw.ipps_impact for the payment-base cross-check",
    },
    # Full text of the FY2026 IPPS final rule (Federal Register 2025-14681), linked from
    # the CMS FY2026 IPPS final rule page. Used only to quote CMS's own HRRP estimates.
    "ipps_fy2026_final_rule_text": {
        "url": "https://www.govinfo.gov/content/pkg/FR-2025-08-04/html/2025-14681.htm",
        "verified": "link on CMS FY2026 IPPS final rule page; page opened 2026-11-01",
    },
    # Census 2020 ZCTA -> county relationship file (pipe-delimited). Used only as a
    # fallback when a hospital's county name doesn't match ACS.
    "zcta_county_rel": {
        "url": "https://www2.census.gov/geo/docs/maps-data/data/rel2020/zcta520/tab20_zcta520_county20_natl.txt",
        "verified": "file name + columns from Census record layout page; URL path NOT fetched",
    },
}

# --- data.cms.gov "data-api" datasets (paged JSON) --------------------------------
CMS_DATA_API = "https://data.cms.gov/data-api/v1/dataset/{uuid}/data"
CMS_API_DATASETS = {
    "hospital_cost_report": "44060663-47d8-4ced-a115-b53b4c270acb",  # HCRIS flat file
    "hospital_enrollments": "f6f6505c-e8b0-4d57-b258-e2b94133aaf2",
    "hospital_all_owners": "029c119f-f79c-49be-9100-344d31d10344",
}
CMS_PAGE_SIZE = 5000

# --- SEC EDGAR XBRL --------------------------------------------------------------
SEC_COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
# CIKs confirmed from sec.gov/files/company_tickers.json and the submissions API.
SEC_COMPANIES = {
    "HCA Healthcare": 860730,
    "Tenet Healthcare": 70318,
    "Community Health Systems": 1108109,
    "Universal Health Services": 352915,
}
SEC_MAX_REQUESTS_PER_SEC = 10  # SEC fair-access limit

# --- Census ACS 2024 5-year, county level -----------------------------------------
ACS_URL = "https://api.census.gov/data/2024/acs/acs5"
# Detailed-table variables (stable names across years, unlike profile tables).
ACS_VARIABLES = {
    "B01001_001E": "total_population",
    "B01002_001E": "median_age",
    "B19013_001E": "median_household_income",
    # Population 65+ = sum of the male (020-025) and female (044-049) age cells.
    **{f"B01001_{i:03d}E": f"pop_m_{i:03d}" for i in range(20, 26)},
    **{f"B01001_{i:03d}E": f"pop_f_{i:03d}" for i in range(44, 50)},
}

# --- Multi-year HRRP panel (FY2016-FY2027) ------------------------------------------
# One entry per HRRP payment year. Every URL below was read off a cms.gov page on
# 2026-11-03 (the landing page is listed too). The downloader tries each URL in order,
# then scrapes the landing page for a .zip link, and logs the year as MISSING if all
# of that fails. A missing year is never filled in.
#
# Performance period ("applicable period"): the discharges CMS measured for that
# payment year. `period_checked` says where the dates came from:
#   "file"   - Start/End Date columns of the CMS Provider Data Catalog HRRP file
#   "cms"    - quoted from a CMS or CMS-contractor (QualityNet / QRC) document
#   "rule"   - the standard 3-year rule (July 1 five years before the FY to June 30 two
#              years before), NOT yet checked against that year's final rule. The dbt
#              test assert_panel_period_matches_file compares these with the file dates
#              once the archived Provider Data Catalog files are loaded.
ARCHIVE_PAGE = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/archived-supplemental-data-files"
_OLD = "https://www.cms.gov/medicare/medicare-fee-for-service-payment/acuteinpatientpps/"
_NEW = "https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/"
_QRC_FY2022 = "https://www.qualityreportingcenter.com/globalassets/iqr2021events/vbp81921/vbp_transcript081921_vfinal508.pdf"
_QRC_FY2021 = ("https://www.qualityreportingcenter.com/globalassets/iqr2020events/hrrp080720/"
               "hrrp_fy2021_hsrrelease_webinar_slides_vfinal508.pdf")

HRRP_YEARS = {
    2016: {
        "supplemental_urls": [_OLD + "downloads/fy2016-cms-1632-fr-readmissions.zip"],
        "landing_page": _OLD + "archived-supplemental-data-files/fy2016-ipps-final-rule-hrrp-supplemental-data-file",
        "period": ("2011-07-01", "2014-06-30"), "period_checked": "rule",
    },
    2017: {
        "supplemental_urls": [],  # the landing page showed no direct link to our reader; scraped at run time
        "landing_page": _OLD + "archived-supplemental-data-files/fy2017-ipps-final-rule-hrrp-supplemental-data-file",
        "period": ("2012-07-01", "2015-06-30"), "period_checked": "rule",
    },
    2018: {
        "supplemental_urls": [_OLD + "downloads/fy2018-fr-hospital-readmissions.zip"],
        "landing_page": _OLD + "archived-supplemental-data-files/fy2018-ipps-final-rule-hrrp-supplemental-data-file",
        "period": ("2013-07-01", "2016-06-30"), "period_checked": "rule",
    },
    2019: {
        "supplemental_urls": [],  # as FY2017: scraped from the landing page at run time
        "landing_page": _OLD + "archived-supplemental-data-files/fy2019-ipps-final-rule-hrrp-supplemental-data-file",
        "period": ("2014-07-01", "2017-06-30"), "period_checked": "rule",
    },
    2020: {
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2020-ipps-final-rule-hospital-readmissions-"
                              "reduction-program-supplemental-data-file.zip"],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2020-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        "period": ("2015-07-01", "2018-06-30"), "period_checked": "rule",
    },
    2021: {
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2021-ipps-final-rule-hospital-readmissions-"
                              "reduction-program-supplemental-data-file.zip"],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2021-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        # "The FY 2021 three-year performance period includes hospital discharges from
        #  July 1, 2016 through June 30, 2019."
        "period": ("2016-07-01", "2019-06-30"), "period_checked": "cms", "period_source": _QRC_FY2021,
    },
    2022: {
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2022-ipps-final-rule-hospital-readmissions-"
                              "reduction-program-supplemental-data-file.zip"],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2022-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        # "The HRRP performance period for fiscal year 2022 is July 1, 2017, to December 1,
        #  2019." Claims for January 1 - June 30, 2020 are excluded (COVID-19 exception).
        "period": ("2017-07-01", "2019-12-01"), "period_checked": "cms", "period_source": _QRC_FY2022,
    },
    2023: {
        # Link from CMS's "Files for FY 2023 Final Rule and Correction Notice" page,
        # https://www.cms.gov/medicare/payment/prospective-payment-systems/acute-inpatient-pps/acute-inpatient-files-download/files-fy-2023-final-rule-correction-notice
        # (The archive page's ...supplemental-data-file.zip-0 link serves CMS's FY2024 file, checked
        # 2026-11-03 on a real download: FY2024_Final_Rule_Supplemental_File.xlsx, sheet "FR FY 2024".)
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2023-ipps-final-rule-hrrp-supplemental-file.zip"],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2023-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        "period": ("2018-07-01", "2021-06-30"), "period_checked": "rule",
        "note": "CMS excludes January-June 2020 from this period (COVID-19); see seeds/hrrp_known_breaks.csv",
    },
    2024: {
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2024-ipps-final-rule-hospital-readmissions-"
                              "reduction-program-supplemental-data-file.zip"],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2024-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        "period": ("2019-07-01", "2022-06-30"), "period_checked": "rule",
        "note": "CMS excludes January-June 2020 from this period (COVID-19); see seeds/hrrp_known_breaks.csv",
    },
    2025: {
        "supplemental_urls": [
            "https://www.cms.gov/files/zip/fy-2025-ipps-final-rule-hospital-readmissions-reduction-program-"
            "supplemental-data-file.zip",  # archive page link
            "https://www.cms.gov/files/zip/fy-2025-hospital-readmissions-reduction-program-supplemental-data-file.zip",
        ],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2025-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        "period": ("2020-07-01", "2023-06-30"), "period_checked": "rule",
    },
    2026: {
        "supplemental_urls": [FILES["hrrp_supplemental"]["url"]],
        "landing_page": _NEW + "archived-supplemental-data-files/fy-2026-ipps-final-rule-hospital-readmissions-"
                               "reduction-program-supplemental-data-file",
        # Start/End Date columns of the FY2026 Provider Data Catalog file (9n3s-kdb3).
        "period": ("2021-07-01", "2024-06-30"), "period_checked": "file",
    },
    2027: {
        "supplemental_urls": ["https://www.cms.gov/files/zip/fy-2027-hospital-readmissions-reduction-program-"
                              "supplemental-data-file.zip"],
        "landing_page": _NEW + "fy-2027-ipps-final-rule-home-page",
        # "The FY 2027 performance period is July 1, 2023, to June 30, 2025." CMS cut the
        # period from 3 years to 2 starting this year.
        "period": ("2023-07-01", "2025-06-30"), "period_checked": "cms",
        "period_source": "https://www.cms.gov/files/document/fy-2027-hrrp-fact-sheet-pdf.pdf",
    },
}
HRRP_HISTORY_RAW = RAW / "hrrp_history"          # one folder per year: fy2016/, fy2017/, ...
MISSING_YEARS_LOG = HRRP_HISTORY_RAW / "missing_years.json"

# Archived Provider Data Catalog snapshots (Hospitals topic). They hold the per-hospital
# HRRP file of each year with its Start/End Date columns. The archive page is a
# JavaScript app with no stable file links, so these are downloaded by hand: save any
# Hospitals archive ZIP into data/raw/pdc_archive/ and ingest.load finds the HRRP CSV in
# it, reads the fiscal year from the file's End Date, and keeps the newest snapshot per
# year. See docs/panel_report.md, "How to get the archived files".
PDC_ARCHIVE_PAGE = "https://data.cms.gov/provider-data/archived-data/hospitals"
PDC_ARCHIVE_RAW = RAW / "pdc_archive"
