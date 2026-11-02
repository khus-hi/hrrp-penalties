# Hospital readmission penalties in dollars

_README to be written at the end of the project._

Quick start:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add SEC_USER_AGENT and CENSUS_API_KEY (both required, both free)
python -m ingest.download && python -m ingest.load && python -m models.build   # each step stops the chain if it fails
python -m analysis.penalty_report   # penalty estimate -> docs/penalty_report.md + analysis/output/*.csv
python -m analysis.err_model        # what explains ERR -> docs/err_model_report.md + docs/figures/
python -m analysis.build_workbook   # Excel: chain penalties vs SEC financials, scenarios, ROI (docs/workbook_guide.md)
python -m dashboard.export_tableau   # CSVs for the Tableau Public dashboard (docs/tableau_build_guide.md)
```
