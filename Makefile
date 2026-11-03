PY ?= python

.PHONY: install ingest build analysis test lint all

install:
	$(PY) -m pip install -e ".[dev]"

ingest:
	$(PY) -m ingest.download && $(PY) -m ingest.load

build:
	$(PY) -m models.build

analysis:
	$(PY) -m analysis.penalty_report
	$(PY) -m analysis.err_model
	$(PY) -m analysis.build_workbook
	$(PY) -m dashboard.export_tableau
	$(PY) -m analysis.open_checks

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

all: ingest build analysis test
