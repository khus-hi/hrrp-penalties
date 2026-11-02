# Data sources, join keys, and where the dollars are approximate

*Verified 2026-11-01 by fetching each official page or API. Nothing here is a computed result; it's a map of what exists and how it fits together.*

## 1. Source-by-source

| # | Source | Exact endpoint / file | Format | Grain | Join key | Key / cost |
|---|---|---|---|---|---|---|
| 1 | CMS HRRP FY2026 hospital file (`9n3s-kdb3`) | CSV: `https://data.cms.gov/provider-data/sites/default/files/resources/a171bc36c488d3e0dc33ec63abb469a6_1770163617/FY_2026_Hospital_Readmissions_Reduction_Program_Hospital.csv` · API: `https://data.cms.gov/provider-data/api/1/datastore/query/9n3s-kdb3/0` | CSV / JSON | hospital × measure (18,330 rows) | `facility_id` = CCN | Free, no key |
| 2 | CMS Hospital General Information (`xubh-q36u`) | CSV: `https://data.cms.gov/provider-data/sites/default/files/resources/893c372430d9d71a1c52737d01239d47_1785189955/Hospital_General_Information.csv` · API: `.../datastore/query/xubh-q36u/0` | CSV / JSON | hospital (5,419 rows) | `facility_id` = CCN | Free, no key |
| 3a | FY2026 IPPS final rule, HRRP Supplemental Data File | `https://www.cms.gov/files/zip/fy2026-hospital-readmissions-reduction-program-supplemental-data-file.zip` | ZIP (spreadsheet) | hospital | CCN | Free, no key |
| 3b | FY2026 IPPS Table 15 (payment adjustment factors) | `https://www.cms.gov/files/zip/fy-2026-hospital-readmissions-reduction-program-payment-adjustment-factors.zip` | ZIP | hospital | CCN | Free, no key |
| 3c | FY2026 IPPS Impact File | `https://www.cms.gov/files/zip/fy2026-ipps-fr-impact-file.zip` | ZIP | hospital | CCN | Free, no key |
| 4a | HCRIS raw cost reports (Form 2552-10), by provider fiscal year | e.g. `https://downloads.cms.gov/FILES/HCRIS/HOSP10FY2024.ZIP` (FY2010 to FY2026 listed [here](https://www.cms.gov/data-research/statistics-trends-and-reports/cost-reports/cost-reports-fiscal-year)) | ZIP of RPT / NMRC / ALPHA CSVs keyed by worksheet, line, column | cost report | `PRVDR_NUM` = CCN | Free, no key |
| 4b | HCRIS flattened "Hospital Provider Cost Report" | API: `https://data.cms.gov/data-api/v1/dataset/44060663-47d8-4ced-a115-b53b4c270acb/data` | JSON / CSV | cost report | `Provider CCN` | Free, no key |
| 5a | CMS Hospital All Owners | API: `https://data.cms.gov/data-api/v1/dataset/029c119f-f79c-49be-9100-344d31d10344/data` · [data dictionary](https://data.cms.gov/sites/default/files/2025-05/90b341cf-89fd-41c6-bf8a-a74e0fc4d1a7/Hospital_All_Owners_Data_Dictionary.pdf) | JSON / CSV | enrollment × owner | `ENROLLMENT ID` (no CCN!) | Free, no key |
| 5b | CMS Hospital Enrollments (needed bridge) | API: `https://data.cms.gov/data-api/v1/dataset/f6f6505c-e8b0-4d57-b258-e2b94133aaf2/data` · [guidance PDF](https://data.cms.gov/sites/default/files/2026-07/Hospital_Data_Guidance.pdf) | JSON / CSV | enrollment | `ENROLLMENT ID` ↔ `CCN` | Free, no key |
| 6 | SEC EDGAR XBRL | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`, `.../companyconcept/CIK##########/us-gaap/<Tag>.json`, bulk `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` | JSON | company × concept × period | CIK (10-digit, zero-padded) | Free, **no key**, but must send a `User-Agent` header with your name + email; max 10 requests/second |
| 7 | Census ACS 2024 | 5-year: `https://api.census.gov/data/2024/acs/acs5` · 1-year: `https://api.census.gov/data/2024/acs/acs1` | JSON | county | `state` + `county` FIPS | Free, but a key is **required** (free email signup, activate from the email, store in `.env` as `CENSUS_API_KEY`). Keyless requests now get a "Missing Key" page (checked 2026-11-02) |

Nothing on this list needs a credit card or billing account.

### Fields worth knowing

- **HRRP file (1):** `facility_name, facility_id, state, measure_name, number_of_discharges, footnote, excess_readmission_ratio, predicted_readmission_rate, expected_readmission_rate, number_of_readmissions, start_date, end_date`. Measures are `READM-30-{AMI,HF,PN,COPD,CABG,HIP-KNEE}-HRRP`. Performance period is 07/01/2021 to 06/30/2024. Values like `N/A` and `Too Few to Report` are strings, so parse carefully. **This file has no payment adjustment factor and no peer group.** Those come only from 3a/3b.
- **General Info (2):** includes `zip_code`, `countyparish` (county *name*, not FIPS), `hospital_type`, `hospital_ownership` (e.g. "Government - Hospital District or Authority"), and `hospital_overall_rating`.
- **Supplemental file (3a):** CMS describes it as "final FY 2026 payment adjustment factors and discharge counts." CMS's methodology guide says these files carry the CCN, dual proportion, peer group (quintile 1 to 5), and for each of the six conditions the ERR, eligible discharges, peer-group median ERR, and a penalty indicator. **I couldn't open the ZIP from this environment**, so exact column names are still to be confirmed at ingest, including whether per-condition DRG payment ratios are included.
- **HCRIS flat file (4b):** includes `Fiscal Year Begin Date`, `Fiscal Year End Date`, `DRG Amounts Other Than Outlier Payments`, `DRG Amounts Before/After October 1`, `Outlier Payments For Discharges`, `Disproportionate Share Adjustment`, `Total IME Payment`, `Total Discharges Title XVIII` (Title XVIII = Medicare), `Net Patient Revenue`, `Total Patient Revenue`, `Net Income`, and `County` (a name). The catalog lists 2022 as the latest annual CSV, but the API's first record has a fiscal year starting 2023-10-01, so the year coverage needs checking at ingest. The raw HCRIS files (4a) go through FY2026, but recent years are incomplete because hospitals file about 5 months after their year ends.
- **All Owners (5a):** `ENROLLMENT ID, ASSOCIATE ID, ORGANIZATION NAME, ASSOCIATE ID - OWNER, ORGANIZATION NAME - OWNER, ROLE CODE - OWNER` (34 = direct, 35 = indirect 5%+), `PERCENTAGE OWNERSHIP`, plus flags (`FOR PROFIT`, `PRIVATE EQUITY COMPANY`, `REIT`, `CHAIN HOME OFFICE`, `OWNED BY ANOTHER ORG OR IND`).
- **SEC CIKs (confirmed via `company_tickers.json` and the submissions API):** HCA Healthcare 860730, Tenet Healthcare 70318, Universal Health Services 352915, Community Health Systems 1108109 (fiscal year ends Dec 31).

## 2. How the sources join

```
HRRP file (1) ──CCN── General Info (2) ──CCN── Supplemental / Table 15 (3a/3b) ──CCN── HCRIS (4)
                         │
                         ├── ZIP / county name ──► county FIPS ──► ACS 2024 (7)
                         │
                       CCN
                         │
               Hospital Enrollments (5b) ──ENROLLMENT ID── All Owners (5a)
                                                               │
                                     owner org name / ASSOCIATE ID - OWNER
                                                               │
                                          hand-built system → CIK table ──► SEC XBRL (6)
```

1. **CCN is the backbone.** It's a 6-character string (keep leading zeros: `010001`, not `10001`). Sources 1 to 4 and 5b all have it.
2. **Owners to CCN:** All Owners has no CCN. You join All Owners → Hospital Enrollments on `ENROLLMENT ID` to get `CCN`. One provider can have several enrollments and CCNs, and multiple CCNs can be joined with `|` in a single field.
3. **Hospital to parent system:** the files list direct and indirect owners but, in CMS's words, the ultimate parent "is not identified in these data." HCA, Tenet, CHS and UHS hospitals sit under layers of LLCs. So the join is a small hand-built crosswalk: match `ORGANIZATION NAME - OWNER` (and the `ASSOCIATE ID - OWNER` values you find) to each of the four parents, then check the list against hospital counts in each company's 10-K. Save it as a documented CSV in the repo (that counts as self-collected data).
4. **System to SEC:** a 4-row table mapping the parent to its CIK (the CIKs above).
5. **Hospital to county FIPS:** General Info only gives a county *name*. Two free options:
   - Match `state` + normalized `countyparish` to the ACS `NAME` field ("Houston County, Alabama"). Watch for "St." vs "Saint", Louisiana parishes, Alaska boroughs, and Virginia independent cities.
   - Or use ZIP → county via the Census ZCTA-to-county relationship file (free, no key). A ZIP can span counties, so take the largest overlap.
   - **Connecticut gotcha:** ACS 2022 and later use CT's 9 planning regions in place of its 8 old counties, so CT hospitals need a separate mapping.
6. **ACS vintage:** use the **5-year 2020–2024** release for counties. The 1-year file only covers areas with 65,000+ people, so it would leave out most rural counties.

## 3. Where the dollar estimates will be approximate (honest list)

**The core estimate.** Under CMS's methodology, the HRRP penalty for a hospital is

> penalty $ ≈ (1 − payment adjustment factor) × the hospital's FY2026 Medicare fee-for-service **base operating DRG payments**

**Formula, now verified against the regulation (42 CFR 412.154(c) and 412.152):** the factor is the higher of 0.97 (the floor for FY2015 onward) and *1 − (aggregate payments for excess readmissions ÷ aggregate payments for all discharges)*. Payments for excess readmissions add up, over the six conditions, *base operating DRG payment for the condition × number of admissions × (ERR − peer-group median ERR) × neutrality modifier*. Base operating DRG payment means the wage-adjusted DRG operating payment plus new-technology add-ons. It **excludes** IME, DSH, outlier and low-volume payments and ignores Value-Based Purchasing adjustments.

The factor is exact. The dollar base is the approximate part:

1. **No public file gives FY2026 base operating DRG payments per hospital.** The closest is HCRIS `DRG Amounts Other Than Outlier Payments`. It's a reasonable proxy but:
   - it's the hospital's own **cost-report year**, not the federal year (Oct 1 to Sep 30) the factor applies to. Many hospitals' fiscal years end Jun 30 or Dec 31, so the base is 1 to 3 years old and needs aligning or labeling;
   - HCRIS line 1 already leaves out outliers, and DSH and IME are reported on separate lines, so its scope is close to the regulatory definition. But it may already be net of that year's HRRP and Value-Based Purchasing adjustments, which the regulation's base leaves out, so it isn't a clean "before penalty" figure;
   - the latest years are incomplete (filing lag), and as-submitted reports can be revised later.
   - *Possible cross-check, unconfirmed:* Worksheet E Part A of the 2552-10 may have a line for the hospital's readmissions adjustment amount. If it's filled in, that's a hospital-reported HRRP dollar figure to compare against. I'll check the HCRIS documentation before relying on it.
2. **Fee-for-service only.** The penalty doesn't apply to Medicare Advantage payments (CMS did not finalize adding MA), and HCRIS DRG amounts are FFS. So don't scale by total Medicare revenue from SEC filings.
3. **Condition attribution is an allocation, not a CMS number.** "Which conditions drive it" splits each hospital's penalty in proportion to each condition's (payment share × excess ERR). If the supplemental file has no per-condition payment shares, they'd have to be approximated (for example, by discharge counts), which is a weaker method.
4. **Ownership is today's snapshot.** All Owners holds current enrollments only, with no history. Hospitals bought or sold during FY2026 (CHS has been selling hospitals) will be assigned to their current owner. Ownership percentages can sum to over 100%, and joint ventures (e.g. HCA at 80%) raise the question of whether to count 100% of the penalty or the owned share. Pick one rule and document it.
5. **SEC filings don't break out by hospital.** 10-K XBRL gives consolidated revenue and net income. Medicare revenue or payer mix is usually tagged by dimension or only in the text, and the `companyfacts` API **doesn't return dimensional facts**. So "penalty as % of system revenue" is solid, but "% of Medicare revenue" would need the filing's XBRL instance or manual reading of the 10-K. Revenue tags also differ by company (HCA's `Revenues` concept came back empty), so tags are chosen per company at ingest. The companies' fiscal years end Dec 31 (confirmed for CHS), while the federal year runs October to September, so expect a mismatch of about one quarter.
6. **Program scope.** HRRP covers only subsection(d) IPPS hospitals. Maryland, critical access, and some other hospitals are left out, so system totals cover only part of a chain's hospitals. Hospitals marked "Too Few to Report" or N/A on a measure add nothing for that measure.
7. **"Public hospital chains."** I read this as the four investor-owned chains listed on the stock market. Government-owned hospitals (General Info's `hospital_ownership` = "Government - …") could make a useful comparison group.

## 4. Timing note

FY2027 started on Oct 1, 2026. CMS has posted the FY2027 HRRP Supplemental Data File and Table 15 (`https://www.cms.gov/files/zip/fy-2027-hospital-readmissions-reduction-program-supplemental-data-file.zip`, final rule CMS-1849-F, correction notice published Sep 29, 2026). FY2027 also changes the performance period from 3 years to 2. FY2026 is the most recent *completed* year that matches your provider-data file, so it's a sound choice. FY2027 is one more file if you want to show a trend.

## 5. Practical note for ingest

Direct downloads (curl) to cms.gov, sec.gov and census.gov were blocked from the cloud sandbox I used, so I checked the endpoints through the web instead. They'll work normally from your laptop. Exact column names inside the CMS ZIPs (3a/3b/3c and HCRIS) are the one thing still to confirm on first download.
