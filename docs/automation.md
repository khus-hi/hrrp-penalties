# CI and the monthly refresh (setup and how to explain it)

Two GitHub Actions workflows, both free on a public repository.

| Workflow | When | What it does | Touches CMS/SEC/Census? |
|---|---|---|---|
| [CI](../.github/workflows/ci.yml) | every push and pull request, plus a manual button | ruff, pytest, builds the fixture DuckDB, `dbt build` | No |
| [Monthly data refresh](../.github/workflows/refresh.yml) | 06:17 UTC on the 5th of each month, plus a manual button | download, load, schema check, build, analysis, tests, then a pull request if any output changed | Yes |

## One-time setup (about 10 minutes)

Do these in order. Steps 1 and 2 run on your Mac, in the repo folder, with the virtual environment active (`cd ~/Downloads/hrrp-penalties && source .venv/bin/activate`).

### 1. Get the branch and make the fixture CSVs

```bash
git fetch origin
git switch claude/project-thread-kbtiwy     # the branch with these workflows
pip install -e ".[dev]"                     # picks up any new dependencies
python -m ingest.load                       # only if data/hrrp.duckdb is older than your last download
python -m ingest.fixtures sample            # writes tests/fixtures/ (prints sizes, must be < 1 MB)
```

The script reads your full `data/hrrp.duckdb` read-only and copies the rows for about 50 hospitals into `tests/fixtures/raw/*.csv`. How the hospitals are picked is in [tests/fixtures/README.md](../tests/fixtures/README.md).

### 2. Record today's source schemas, then commit and push

```bash
python -m ingest.schema_check --accept      # writes ingest/schema_lock.json from data/raw/manifest.json
make ci                                     # optional: the same steps CI runs, on your laptop
git add tests/fixtures ingest/schema_lock.json
git commit -m "Add CI fixtures (50 real hospitals) and the source schema lock"
git push
```

The push starts CI on the pull request. It will be red until this commit is pushed, because there are no fixtures before it.

### 3. Add the two repository secrets

Secrets are encrypted by GitHub and never show in logs, which is why the refresh reads keys from them instead of a `.env` file (that file stays on your laptop and is git-ignored).

1. Open https://github.com/khus-hi/hrrp-penalties/settings/secrets/actions (Settings → Secrets and variables → Actions).
2. Click **New repository secret**. Name: `SEC_USER_AGENT`. Value: the same text as in your `.env`, for example `Your Name your.email@example.com`. Click **Add secret**.
3. Click **New repository secret** again. Name: `CENSUS_API_KEY`. Value: your key from `.env`. Click **Add secret**.

### 4. Let Actions open pull requests

Open https://github.com/khus-hi/hrrp-penalties/settings/actions, scroll to **Workflow permissions**, select **Read and write permissions**, tick **Allow GitHub Actions to create and approve pull requests**, and click **Save**. Without this, the last refresh step fails with "GitHub Actions is not permitted to create or approve pull requests".

### 5. Try the refresh once by hand

Actions tab → **Monthly data refresh** → **Run workflow** → branch `main` (after merging) → **Run workflow**. It takes 10 to 30 minutes, mostly the cost report download. The run page shows a schema-check table, and the download manifest is saved under **Artifacts**.

## What the refresh does when something changes

- **New files, same columns:** a normal refresh. If any file in `docs/` or `analysis/output/` changed (lines that only differ in their `_Generated <time>` stamp don't count), it opens or updates a pull request named "Monthly data refresh" on the branch `automated/data-refresh`. Nothing reaches `main` until you merge it.
- **A file changed and its columns changed:** the run fails at the schema check and lists the added and removed columns. Fix `ingest/load.py` or the staging models, run `python -m ingest.schema_check --accept` locally, and commit `ingest/schema_lock.json`.
- **A site refuses the download** (for example a 403 from data.cms.gov): the run fails at the download step and the log names the source. Rerun later, or download that file by hand as `python -m ingest.download` explains.

## Things worth knowing

- **Pull requests opened by the refresh don't start CI on their own.** GitHub does this on purpose so workflows can't trigger each other in loops. The refresh run already built the models and ran the tests on the full data; if you also want CI on that branch, open Actions → CI → Run workflow and pick `automated/data-refresh`.
- **Scheduled workflows pause after 60 days without commits** on a public repository. GitHub emails you first; one click on "Enable workflow" in the Actions tab turns it back on.
- **The fixture data is for testing code only.** It's 50 hospitals, so its totals mean nothing; never quote them.
- **Refreshing the fixtures:** rerun `python -m ingest.fixtures sample` after a refresh that changed a schema, and commit the CSVs.

## Interview talking points

- **Why fixtures instead of the real download in CI?** CI has to be fast, free and deterministic. Hitting CMS on every push would be slow, rate-limited and flaky, and a CMS outage would turn my build red for reasons unrelated to my code. A stratified sample of real rows keeps every edge case (Maryland waiver, each chain, Connecticut planning regions, join drop-outs, the 3% cap) in under 1 MB.
- **Why sample real rows rather than make up test data?** The bugs that matter in this project come from real quirks: suppressed values, leading zeros in CCNs, odd county names. Made-up rows would not have them.
- **What does the schema check protect against?** Silent breakage. CMS republishes files with the same name; if a column is renamed, a loader that matches by name would just produce NULLs and the penalty total would quietly drop. Comparing the file hash and the column list separates "new data" (fine) from "new layout" (stop and look).
- **Why a pull request instead of committing to main?** A person reviews changed numbers before they become the published result, and the diff on the PR shows exactly what moved.
- **Secrets:** API keys live in GitHub's encrypted secrets for the workflow and in a git-ignored `.env` locally. Neither is ever committed.
