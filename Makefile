# One-word commands for the pipeline. Run `make help` to list them.
# Activate your virtual environment first (source .venv/bin/activate).

PYTHON ?= python

.PHONY: help install ingest build docs analysis uncertainty panel rd did workbook tableau report test lint all fixtures fixture-db ci schema-check

help:  ## List the targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install:  ## Install the project and dev tools (pytest, ruff) into the active environment
	$(PYTHON) -m pip install -e ".[dev]"

ingest:  ## Download every source into data/raw and load it into DuckDB (needs .env)
	$(PYTHON) -m ingest.download
	$(PYTHON) -m ingest.load

build:  ## dbt build: seeds, models and tests, then docs/data_quality_report.md
	$(PYTHON) -m models.build

docs:  ## Generate the dbt docs site (lineage graph, column descriptions) and serve it on localhost:8080
	cd dbt && HRRP_DB_PATH="$(CURDIR)/data/hrrp.duckdb" dbt docs generate && HRRP_DB_PATH="$(CURDIR)/data/hrrp.duckdb" dbt docs serve

analysis:  ## Penalty interval + report, ERR model, open checks, factor check, and the FY2016-FY2027 panel report
	$(PYTHON) -m analysis.penalty_uncertainty
	$(PYTHON) -m analysis.penalty_report
	$(PYTHON) -m analysis.err_model
	$(PYTHON) -m analysis.open_checks
	$(PYTHON) -m analysis.check_factor
	$(PYTHON) -m analysis.panel_report

uncertainty:  ## Impact File cross-check + Monte Carlo 90% interval (docs/penalty_uncertainty.md), after make build
	$(PYTHON) -m analysis.penalty_uncertainty

panel:  ## FY2016-FY2027 panel report only (docs/panel_report.md), after make build
	$(PYTHON) -m analysis.panel_report

rd:  ## Penalty -> later readmissions regression discontinuity (docs/rd_report.md), after the panel is built
	$(PYTHON) -m analysis.rd_report

did:  ## Cures Act peer-group reform event study (docs/did_report.md), after make build (and make rd for the comparison)
	$(PYTHON) -m analysis.did_report

workbook:  ## Rebuild the Excel workbook (overwrites analysis/output/hrrp_chain_workbook.xlsx)
	$(PYTHON) -m analysis.build_workbook

tableau:  ## Rebuild the Tableau CSVs (overwrites dashboard/tableau_exports/)
	$(PYTHON) -m dashboard.export_tableau

report:  ## Render the findings report (report/hrrp.qmd -> report/_site/hrrp.html) from the committed outputs; needs Quarto
	cd report && quarto render

test:  ## Unit tests (no downloads, about a second)
	$(PYTHON) -m pytest

lint:  ## Ruff lint
	$(PYTHON) -m ruff check .

all: ingest build analysis test  ## Whole pipeline, then tests (leaves the workbook and Tableau CSVs alone)

fixtures:  ## Cut ~50 real hospitals from data/hrrp.duckdb into tests/fixtures/ (run after ingest)
	$(PYTHON) -m ingest.fixtures sample

fixture-db:  ## Build data/fixture.duckdb from tests/fixtures/raw/*.csv
	$(PYTHON) -m ingest.fixtures build --db data/fixture.duckdb

schema-check:  ## Fail if a source file changed and its columns changed too (see ingest/schema_lock.json)
	$(PYTHON) -m ingest.schema_check

ci: lint test fixture-db  ## What GitHub Actions CI runs: lint, tests, then the models on the fixture DB
	HRRP_DB_PATH=$(CURDIR)/data/fixture.duckdb KEEP_REPORT=1 bash .github/scripts/build_models.sh
