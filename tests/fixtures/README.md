# Test fixtures: about 50 real hospitals

CI builds every model against a tiny DuckDB made from the CSVs in `raw/`, so it never
downloads from CMS, SEC or Census. **Every row here is a real row**, copied unchanged from
the `raw.*` tables that `python -m ingest.load` built from the official files. Nothing is
invented or edited; the script only chooses which rows to keep.

| File | What it is |
|---|---|
| `raw/<table>.csv` | One CSV per `raw.*` table, same columns, text exactly as loaded |
| `sample_ccns.csv` | The hospitals picked and why (Maryland, each chain, CT, join drop-outs, ...) |
| `provenance.json` | When the sample was cut, row counts, and the SHA-256 of each source file it came from (from `data/raw/manifest.json`) |

## How to (re)create them

You need the full data on your laptop first (the normal pipeline):

```bash
source .venv/bin/activate
python -m ingest.download && python -m ingest.load   # or: make ingest
python -m ingest.fixtures sample                     # or: make fixtures
git add tests/fixtures
git commit -m "Refresh CI fixtures from the latest CMS/SEC/Census files"
git push
```

`sample` reads `data/hrrp.duckdb` read-only and prints each CSV's size. It stops with an
error if the total is over 1 MB; if that happens, run `python -m ingest.fixtures sample --n 40`.

## How hospitals are chosen

So that 50 hospitals still exercise every join and edge case, the script picks, in order:
3 Maryland hospitals (no HRRP factor, state waiver), 3 from each of HCA, Tenet, CHS and
UHS, 3 Massachusetts, 2 Connecticut (Census planning regions), 2 with no payment factor,
2 with no cost report, 1 missing from General Information, 1 at the 3% cap, 3 with no
penalty, then fills up to 50 at random. "Random" means ordered by `md5(ccn)`, so the same
data always gives the same sample. Each table is then cut to what those hospitals need:
their enrollments and owners, their ZIPs and counties, and SEC facts only for the XBRL
tags and recent fiscal years the workbook reads.

## Multi-year panel tables

`raw/hrrp_supplemental_history.csv`, `hrrp_hospital_history.csv`, `hrrp_history_files.csv`
and `hrrp_program_years.csv` feed the FY2016-FY2027 panel. `sample` keeps every year for 30
of the sampled hospitals (12 years of all 50 would pass 1 MB).

**Until the next `make fixtures` they hold FY2026 only:** the same real FY2026 rows that
were already in `hrrp_supplemental_original.csv` and `hrrp_hospital.csv`, restacked by
`ingest.load`'s own functions, and the other years are marked `missing` with the note
"not in the CI fixture yet". After you run the multi-year ingest on your laptop, re-cut
the fixtures (`make fixtures`) so CI checks the cross-year harmonising on real old files too.

## How CI uses them

```bash
python -m ingest.fixtures build          # -> data/fixture.duckdb (raw.* tables)
HRRP_DB_PATH=$PWD/data/fixture.duckdb dbt build --project-dir dbt --profiles-dir dbt
```

`make ci` runs the same steps locally. The fixture numbers are for testing the code only;
never quote them as results.
