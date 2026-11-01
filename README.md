# Hospital readmission penalties in dollars

_README to be written at the end of the project._

Quick start:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add SEC_USER_AGENT (required) and CENSUS_API_KEY (optional)
python -m ingest.download   # 1. fetch every source into data/raw/
python -m ingest.load       # 2. load raw files into data/hrrp.duckdb
python -m models.build      # 3. build SQL models + data-quality checks
```
