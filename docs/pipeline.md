# How the pipeline works (and how to explain it)

```
python -m ingest.download  ->  data/raw/            (files exactly as published + manifest.json)
python -m ingest.load      ->  data/hrrp.duckdb raw.*   (everything as text)
python -m models.build     ->  stg.* -> int.* -> mart.hospital, qa.*  + docs/data_quality_report.md
```

## 1. Download (`ingest/download.py`)
- **What:** fetches 13 official sources (CMS, SEC, Census) into `data/raw/<source>/`.
- **Why it's built this way:** raw files are never edited, so any number can be traced back to what the agency served. `manifest.json` records URL, time and SHA-256 for each file. CMS provider-data links change on every refresh, so the script asks CMS's metastore API for the current link. data.cms.gov APIs are paged 5,000 rows at a time. SEC requests send your `User-Agent` from `.env` and stay under SEC's 10-requests-per-second limit.

## 2. Load (`ingest/load.py`)
- **What:** loads every raw file into DuckDB's `raw` schema as text, plus the `seeds/` tables.
- **Why text:** casting in SQL later lets a bad value become NULL *and get counted* in the checks, instead of crashing the load or being silently coerced.
- **The one tricky source:** CMS doesn't publish a column list for the FY2026 IPPS HRRP spreadsheets. The loader finds the header row, matches columns by pattern (e.g. "adjustment factor", "peer group median ERR for AMI"), and logs every match or miss to `raw.column_mapping_log`. A miss becomes a NULL column, never a guess. **On the first real run, read that printed mapping.**

## 3. Models (`models/`, plain SQL run in order)
- `staging/`: one cleaned table per source. CCN is padded to 6 characters, text numbers are cast, and suppressed values become NULL but keep their raw text.
- `intermediate/`:
  - **hospital → parent system**: CCN → enrollment → all owners → owner name matched to `seeds/system_owner_patterns.csv`. CMS never names the ultimate parent, so this is a documented crosswalk you can check.
  - **hospital → county FIPS**: state + county name matched to ACS; if that fails, ZIP → county via the Census relationship file.
- `marts/mart_hospital.sql`: **one row per hospital in the FY2026 HRRP file**, LEFT JOINed so no hospital disappears silently. It has ERR and discharges by condition, the payment adjustment factor (plus Table 15 as a cross-check), Medicare base DRG payments from the cost report, ownership, teaching status (intern/resident FTE > 0), beds, star rating, county median income, median age and share aged 65+, and parent system.

## 4. Checks (`checks/`)
- `qa.join_funnel`: hospitals left after each join, in order, with the number dropped at each step.
- `qa.source_coverage`: the same joins measured one at a time.
- `qa.unmatched_ccns`: every CCN that failed a join, with the reason.
- `qa.suppressed_values`: per condition, how many ERRs are missing, "N/A", or "Too Few to Report", and which footnote codes appear.
- `qa.assertions`: pass/fail tests. Examples: one row per CCN; adjustment factor within [0.97, 1.0], the floor in 42 CFR 412.154; supplemental factor matches Table 15; no Census sentinel codes left.

## 5. Penalty estimate (`models/marts/mart_hospital_penalty.sql`, `analysis/`)
- `mart.hospital_penalty`: (1 − factor) × annualised Medicare base DRG payments, with an `estimate_quality` flag on each row. `mart.hospital_condition_penalty` splits the dollars by condition using CMS's own inputs. The method is in [penalty_method.md](penalty_method.md).
- `python -m analysis.penalty_report` writes the state, ownership, system, condition and Massachusetts tables to `docs/penalty_report.md` and `analysis/output/*.csv`. It also quotes the FY2026 final rule's own HRRP estimates for comparison.

## 6. What explains readmission ratios (`analysis/err_model.py`)
- **Outcome:** each hospital's composite ERR, weighted by CMS's eligible discharges.
- **Main model:** OLS with HC3 robust standard errors on beds, teaching status, ownership, dual-eligible share, county income and county 65+ share. Star rating is added separately because it partly contains the outcome.
- **Sensitivity checks:** errors clustered by state, a discharge-weighted fit, and DSH % in place of the dual share.
- **Variance explained:** a Shapley split of R² shows how much social risk accounts for.
- **Nonlinearity:** a cross-validated gradient-boosted tree, compared with the linear model.
- **Output:** `docs/err_model_report.md`, which includes plain-English coefficients, the assumption checks and the causality caveats.

## Not done yet (on purpose)
- The SEC facts are staged (`stg.sec_annual`) but not yet in the mart. Revenue tags differ by company and will be chosen in the analysis step.
