#!/usr/bin/env bash
# Build the models against whatever DuckDB HRRP_DB_PATH points at.
# Used by CI (fixture DB), the monthly refresh (full DB) and `make ci`.
#   - With a dbt project (dbt/dbt_project.yml): `dbt build` = seeds + models + tests.
#   - Before dbt lands: the plain-SQL runner, python -m models.build.
# KEEP_REPORT=1 puts docs/data_quality_report.md back afterwards, so a fixture run
# never overwrites the real report with numbers from the 50-hospital sample.
set -euo pipefail
: "${HRRP_DB_PATH:?set HRRP_DB_PATH to the DuckDB file to build}"
export HRRP_DB_PATH="$(cd "$(dirname "$HRRP_DB_PATH")" && pwd)/$(basename "$HRRP_DB_PATH")"  # dbt needs an absolute path
report=docs/data_quality_report.md
if [[ "${KEEP_REPORT:-0}" == 1 && -f "$report" ]]; then
  backup="$(mktemp)"; cp "$report" "$backup"
  trap 'cp "$backup" "$report"; rm -f "$backup"' EXIT
fi
if [[ -f dbt/dbt_project.yml ]]; then
  echo "dbt build against $HRRP_DB_PATH"
  dbt build --project-dir dbt --profiles-dir dbt
else
  echo "python -m models.build against $HRRP_DB_PATH"
  python -m models.build
fi
