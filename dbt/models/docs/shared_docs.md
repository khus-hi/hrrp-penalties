{% docs ccn %}
CMS Certification Number: the 6-character hospital ID (e.g. "010001"), kept as text
so leading zeros survive. It joins the HRRP file, General Information, the IPPS
files and the cost report.
{% enddocs %}

{% docs condition %}
HRRP condition code: ami (heart attack), hf (heart failure), pn (pneumonia),
copd, cabg (bypass surgery), tha_tka (elective hip/knee replacement).
{% enddocs %}

{% docs err %}
Excess readmission ratio: the hospital's predicted 30-day readmission rate divided by
the expected rate for an average hospital with the same patients. Above 1 means more
readmissions than expected. NULL when CMS suppressed or did not report it.
{% enddocs %}

{% docs payment_adjustment_factor %}
CMS's FY2026 HRRP payment adjustment factor from the IPPS final rule supplemental file.
1.0 = no penalty; 0.97 = the maximum 3% cut (42 CFR 412.154). Multiplies every
Medicare base operating DRG payment from Oct 2025 to Sep 2026.
{% enddocs %}

{% docs __overview__ %}
# HRRP penalties in dollars

dbt project for the FY2026 Medicare Hospital Readmissions Reduction Program (HRRP)
penalty estimate. Data flows **raw -> stg -> int -> mart**, plus **qa** report tables:

- **raw**: official CMS, Census and SEC files, loaded as text by `ingest/load.py`.
- **stg**: one cleaned table per source (CCN padded to 6 characters, text cast to numbers, suppressed values NULL).
- **int**: hospital -> county FIPS, and hospital -> parent system (HCA, Tenet, CHS, UHS).
- **mart**: `mart.hospital` (one row per hospital in the HRRP file) and the penalty tables.
- **qa**: join funnel, coverage and other report tables for `docs/data_quality_report.md`.

Tests: generic tests live next to each column in the `_*.yml` files; the singular
tests in `tests/` check the CMS factor recompute, the join funnel and the penalty sums.
{% enddocs %}
