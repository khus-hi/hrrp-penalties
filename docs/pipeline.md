# How the pipeline works (and how to explain it)

```
python -m ingest.download  ->  data/raw/            (files exactly as published + manifest.json)
python -m ingest.load      ->  data/hrrp.duckdb raw.*   (everything as text)
python -m models.build     ->  dbt build: seed.*, stg.* -> int.* -> mart.*, qa.*, tests  + docs/data_quality_report.md
```

## 1. Download (`ingest/download.py`)
- **What:** fetches 13 official sources (CMS, SEC, Census) into `data/raw/<source>/`, plus the FY2016-FY2027 HRRP supplemental files into `data/raw/hrrp_history/fy<YEAR>/` (section 9).
- **Why it's built this way:** raw files are never edited, so any number can be traced back to what the agency served. `manifest.json` records URL, time and SHA-256 for each file. CMS provider-data links change on every refresh, so the script asks CMS's metastore API for the current link. data.cms.gov APIs are paged 5,000 rows at a time. SEC requests send your `User-Agent` from `.env` and stay under SEC's 10-requests-per-second limit.

## 2. Load (`ingest/load.py`)
- **What:** loads every raw file into DuckDB's `raw` schema as text, with a `_loaded_at` timestamp on each table (used by `dbt source freshness`). The `seeds/` CSVs are loaded by `dbt seed` in the next step.
- **Why text:** casting in SQL later lets a bad value become NULL *and get counted* in the checks, instead of crashing the load or being silently coerced.
- **The one tricky source:** CMS doesn't publish a column list for the FY2026 IPPS HRRP spreadsheets. The loader finds the header row, matches columns by pattern (e.g. "adjustment factor", "peer group median ERR for AMI"), and logs every match or miss to `raw.column_mapping_log`. A miss becomes a NULL column, never a guess. **On the first real run, read that printed mapping.**

## 3. Models (`dbt/`, a dbt-duckdb project)
- **Why dbt:** each table is a `SELECT` in its own file, and `ref()` / `source()` tell dbt how they depend on each other, so dbt works out the build order, draws the lineage graph, and runs the tests right after the table they check. It is free, open source and runs locally against the same DuckDB file; there is no server.
- **Layout:** `dbt/dbt_project.yml` (settings), `dbt/profiles.yml` (points at `data/hrrp.duckdb`; override with `HRRP_DB_PATH`), `dbt/models/{staging,intermediate,marts,qa}/`, `dbt/macros/`, `dbt/tests/`. Seeds stay in the repo-root `seeds/` folder.
- **Same table names as before:** two small macros in `dbt/macros/naming.sql` keep the schemas (`stg`, `int`, `mart`, `qa`, `seed`) and drop the layer prefix from table names, so `models/marts/mart_hospital.sql` builds `mart.hospital`. `analysis/` and `dashboard/` read exactly the tables they did before.
- `staging/`: one cleaned table per source, declared on top of the `raw` sources in `_sources.yml`. CCN is padded to 6 characters, text numbers are cast, and suppressed values become NULL but keep their raw text. The cleaning helpers `clean_ccn`, `to_num` and `norm_county` are dbt macros (`dbt/macros/cleaning.sql`).
- `intermediate/`:
  - **hospital → parent system**: CCN → enrollment → all owners → owner name matched to `seeds/system_owner_patterns.csv`. CMS never names the ultimate parent, so this is a documented crosswalk you can check.
  - **hospital → county FIPS**: state + county name matched to ACS; if that fails, ZIP → county via the Census relationship file.
- `marts/mart_hospital.sql`: **one row per hospital in the FY2026 HRRP file**, LEFT JOINed so no hospital disappears silently. It has ERR and discharges by condition, the payment adjustment factor (plus Table 15 as a cross-check), Medicare base DRG payments from the cost report, ownership, teaching status (intern/resident FTE > 0), beds, star rating, county median income, median age and share aged 65+, and parent system.
- **Docs:** every source, model and column has a description in the `_*.yml` files. `make docs` builds and serves the dbt docs site (lineage graph plus column descriptions).

## 4. Checks (dbt tests and `qa` tables)
- **Report tables** (`dbt/models/qa/`): `qa.join_funnel` (hospitals left after each join, in order, with the number dropped at each step), `qa.source_coverage` (the same joins one at a time), `qa.unmatched_ccns` (every CCN that failed a join, with the reason), `qa.suppressed_values` (per condition, how many ERRs are missing, "N/A", or "Too Few to Report", and which footnote codes appear).
- **Generic tests**, next to each column in the `_*.yml` files: `unique` and `not_null` on every `ccn` key, `accepted_values` on ownership, condition codes and `estimate_quality`, `relationships` from the marts back to staging and the seeds, and `expression_is_true` for ranges (factor within [0.97, 1.0], the floor in 42 CFR 412.154; ERR > 0; no Census sentinel codes left).
- **Singular tests** (`dbt/tests/*.sql`, each a query that returns the rows that break the rule): the CMS factor recompute (must match CMS within 0.0001 for every hospital), the join funnel (7 steps, starts at every HRRP hospital, never grows, ends at the complete rows), supplemental factor = Table 15, condition shares sum to 1, condition dollars add up, the 3% cap, and factor 1 ⇒ $0.
- **Severity:** most tests warn and the build carries on, like the old checks did. The grain of `mart.hospital` (unique, not null CCN) and the factor recompute are errors: if one fails, dbt skips everything downstream rather than computing dollars from a broken table, and `make build` exits with an error.
- **Results:** `python -m models.build` writes one row per test to `qa.assertions` and prints them in `docs/data_quality_report.md`. Failing rows are kept in the `qa_failures` schema.
- **Freshness:** `dbt source freshness` warns when a raw table was loaded more than 100 days ago and errors after 400 (CMS provider data refreshes quarterly, the HRRP payment files yearly). It is reported, never fatal.

## 5. Penalty estimate (`dbt/models/marts/mart_hospital_*.sql`, `analysis/`)
- `mart.hospital_penalty`: (1 − factor) × annualised Medicare base DRG payments, with an `estimate_quality` flag on each row. `mart.hospital_condition_penalty` splits the dollars by condition using CMS's own inputs. The method is in [penalty_method.md](penalty_method.md).
- `python -m analysis.penalty_report` writes the state, ownership, system, condition and Massachusetts tables to `docs/penalty_report.md` and `analysis/output/*.csv`. It also quotes the FY2026 final rule's own HRRP estimates for comparison.

## 6. What explains readmission ratios (`analysis/err_model.py`)
- **Outcome:** each hospital's composite ERR, weighted by CMS's eligible discharges.
- **Main model:** OLS with HC3 robust standard errors on beds, teaching status, ownership, dual-eligible share, county income and county 65+ share. Star rating is added separately because it partly contains the outcome.
- **Sensitivity checks:** errors clustered by state, a discharge-weighted fit, and DSH % in place of the dual share.
- **Variance explained:** a Shapley split of R² shows how much social risk accounts for.
- **Nonlinearity:** a cross-validated gradient-boosted tree, compared with the linear model.
- **Output:** `docs/err_model_report.md`, which includes plain-English coefficients, the assumption checks and the causality caveats.

## 7. Tests (`hrrp/`, `tests/`, `make test`)
- **What:** the calculations the scripts depend on live in the `hrrp` package as plain functions: the CMS payment adjustment factor (`hrrp/penalty.py`), the discharge-weighted composite ERR and the 0-1 vs 0-100 percent fix (`hrrp/err.py`), and the Shapley R² split (`hrrp/shapley.py`). `pytest` tests them on small hand-typed tables, so no download is needed.
- **The factor test** is a worked example: one hospital's inputs exactly as CMS published them in the FY2026 supplemental file, worked through the 42 CFR 412.152/412.154 steps by hand, landing on CMS's published factor.
- **Python vs SQL:** dbt still builds every table. `python -m analysis.check_factor` recomputes the factor in Python for every hospital and checks it against both the SQL and CMS.
- **Run it:** `make test` (unit tests) or `make all` (whole pipeline, then tests). `make help` lists every target.

## 8. CI and the monthly refresh (`.github/workflows/`, `ingest/fixtures.py`, `ingest/schema_check.py`)
- **CI:** on every push and pull request, ruff, pytest, then the models and data tests on a fixture DuckDB of about 50 real hospitals (`tests/fixtures/`). No downloads.
- **Refresh:** monthly, the full pipeline runs on GitHub's machines and opens a pull request if any output changed.
- **Schema check:** a source whose file hash changed *and* whose columns changed stops the refresh, so a renamed CMS column can't quietly become NULLs.
- Setup and talking points: [automation.md](automation.md).

## 9. Multi-year panel, FY2016-FY2027 (`mart.fct_hospital_condition_year`)
- **Sources:** each year's IPPS final rule HRRP supplemental file (CMS's payment inputs), listed with its cms.gov landing page and performance period in `ingest/config.py` `HRRP_YEARS`, and optionally the archived Provider Data Catalog HRRP files saved by hand in `data/raw/pdc_archive/`. `python -m ingest.download` tries each URL, then scrapes the landing page; a year it can't get goes in `data/raw/hrrp_history/missing_years.json` and shows as `missing` in `qa.panel_year_coverage`. A missing year is never filled in.
- **Harmonising names:** CMS renamed the columns several times. The loader stacks every year with its own column names (`raw.hrrp_supplemental_history`); `dbt/macros/harmonize.sql` maps them to one set by regex when the model compiles. `qa.panel_column_map` is the audit trail (which raw column fed which field, each year), and a test fails if two columns of one year compete for a field.
- **The mart:** one row per CCN x condition x year: ERR, peer group (dual-proportion quintile, FY2019+), CMS's peer median, eligible discharges, DRG ratio, CMS's penalty indicator, `penalized_condition`, the payment factor, the performance period, and where each came from (`err_source`, `penalized_source`, `perf_period_source`).
- **Known breaks** (`seeds/hrrp_known_breaks.csv`, each with the CMS page and sentence): FY2022-FY2024 leave out January-June 2020 (COVID-19), FY2023 pneumonia was suppressed from payment, FY2019 started peer groups, CABG starts FY2017, FY2027 uses 2 years. Rows carry `covid_2020_excluded`, `measure_suppressed` and `break_notes`.
- **Tests:** one row per CCN x condition x year (error); ERR between 0.5 and 2; peer median recomputed from the panel = CMS's published median (FY2019+, full data only); one published median per group; config periods = the file's Start/End Date; seed breaks agree with the data; the panel's FY2026 rows = the single-year pipeline's (error).
- **Report:** `make panel` writes [panel_report.md](panel_report.md): hospitals per year, how many appear in every year, and attrition.

## 10. Does a penalty lower later readmissions? Regression discontinuity (`hrrp/causal/rd.py`)
- **Design:** from FY2019 a condition is penalized only if its ERR is above its peer group's median (and it had 25+ eligible discharges). Running variable = ERR minus peer median, cutoff 0; outcome = the same condition's ERR 3 payment years later (no overlap with FY t's window). FY t+1 is shown but labelled contaminated (its window shares two years with FY t's); FY t+4 is a timing check.
- **Sharp, not fuzzy:** with the 25-case rule applied first, CMS's indicator is exactly ERR > median (checked every run, and on FY2026: all 1,551 above-median "N" rows have fewer than 25 discharges). The full sample is fuzzy and is run as a fuzzy RD for comparison. Rows exactly at the median are dropped (CMS's rule is strictly "above").
- **Estimation:** rdrobust local-linear, triangular kernel, MSE-optimal bandwidth, robust bias-corrected CIs; pooled with condition x year fixed effects as covariates and SEs clustered by hospital, then each condition.
- **Checks:** rddensity density test, covariate balance (beds, dual share, ownership, teaching, the pre-period ERR, attrition), placebo cutoffs at -0.05 and +0.05, a donut without abs(x) < 0.002, half and double bandwidth.
- **Report:** `make rd` writes [rd_report.md](rd_report.md), `docs/figures/rd/*.png` and `analysis/output/rd_*.csv`.

## 11. Did the FY2019 peer-group reform change readmissions? Event study (`hrrp/causal/did.py`)
- **Natural experiment:** the 21st Century Cures Act switched HRRP from "ERR above 1" to "ERR above your dual-eligible peer group's median" in FY2019. Applying both rules to the same FY2019 ERRs gives each hospital a simulated penalty change (dpen, pp of base DRG payments) that depends only on the rule. The new-rule code is checked by recomputing CMS's FY2019 adjustment factors.
- **Estimation:** pyfixest, ERR on year x dpen (FY2018 reference), hospital and condition x year fixed effects, errors clustered by hospital, FY2016 to the last loaded year.
- **Checks:** joint pre-trend test on the FY2016-FY2017 leads, placebo reform years FY2017 and FY2018, dropping hospitals that changed peer group, a binary down-vs-up version, hospital x condition fixed effects, and "rule-only" controls (year-specific slopes in the FY2019 ERR and old-rule penalty that dpen is built from, against mean reversion).
- **Tests:** `tests/test_did.py` plants a known effect in a simulated panel and checks the estimator recovers it, the pre-trend test catches a planted pre-trend, and the rules match hand-worked examples. Simulated data are only used there.
- **Report:** `make did` writes [did_report.md](did_report.md), `docs/figures/did/*.png` and `analysis/output/did_*.csv`, including the comparison with the RD.

## Not done yet (on purpose)
- The SEC facts are staged (`stg.sec_annual`) but not yet in the mart. Revenue tags differ by company and will be chosen in the analysis step.
