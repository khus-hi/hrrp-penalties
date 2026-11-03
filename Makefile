# One-word commands for the pipeline. Run `make help` to list them.
# Activate your virtual environment first (source .venv/bin/activate).

PYTHON ?= python

.PHONY: help install ingest build analysis workbook tableau test lint all

help:  ## List the targets
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

install:  ## Install the project and dev tools (pytest, ruff) into the active environment
	$(PYTHON) -m pip install -e ".[dev]"

ingest:  ## Download every source into data/raw and load it into DuckDB (needs .env)
	$(PYTHON) -m ingest.download
	$(PYTHON) -m ingest.load

build:  ## Run the SQL models and data-quality checks (docs/data_quality_report.md)
	$(PYTHON) -m models.build

analysis:  ## Penalty report, ERR model, open checks, and the Python-vs-SQL-vs-CMS factor check
	$(PYTHON) -m analysis.penalty_report
	$(PYTHON) -m analysis.err_model
	$(PYTHON) -m analysis.open_checks
	$(PYTHON) -m analysis.check_factor

workbook:  ## Rebuild the Excel workbook (overwrites analysis/output/hrrp_chain_workbook.xlsx)
	$(PYTHON) -m analysis.build_workbook

tableau:  ## Rebuild the Tableau CSVs (overwrites dashboard/tableau_exports/)
	$(PYTHON) -m dashboard.export_tableau

test:  ## Unit tests (no downloads, about a second)
	$(PYTHON) -m pytest

lint:  ## Ruff lint
	$(PYTHON) -m ruff check .

all: ingest build analysis test  ## Whole pipeline, then tests (leaves the workbook and Tableau CSVs alone)
