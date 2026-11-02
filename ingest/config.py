"""Every source URL in one place.

Each entry was checked against the official page on 2026-11-01 (see docs/data_sources.md).
"verified" says what was confirmed live; anything not confirmed is flagged so the
pipeline can check it on first download rather than trusting it blindly.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB_PATH = ROOT / "data" / "hrrp.duckdb"

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
        "verified": "link on FY2026 IPPS final rule page; downloaded for reference, not modelled yet",
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
