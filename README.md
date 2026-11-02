# Hospital readmission penalties in dollars

_README to be written at the end of the project._

Quick start:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add SEC_USER_AGENT (required) and CENSUS_API_KEY (optional)
python -m ingest.download && python -m ingest.load && python -m models.build   # each step stops the chain if it fails
```
