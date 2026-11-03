"""Schema-drift guard: fail loudly if a source file changed AND its columns changed.

The idea in one line: a new file with the same columns is a normal data refresh; a new
file with different columns means CMS/SEC/Census changed the layout, and the models
could quietly produce wrong numbers. So the pipeline stops and a person looks.

How it works:
  * ingest/schema_lock.json (committed) records, for each source in
    data/raw/manifest.json, the SHA-256 of the last file we accepted and its schema.
  * After download + load, this script compares the new manifest with the lock.
      - same SHA-256                    -> unchanged, nothing to do
      - new SHA-256, same schema        -> normal refresh; the lock gets the new hash
      - new SHA-256, different schema   -> prints what was added/removed, exits 1
      - source not in the lock          -> exits 1 (accept it with --accept)

"Schema" means the column names of the raw.* table that ingest.load built from the
file (the untouched sheet for the IPPS spreadsheets), the XBRL fact fields for SEC,
and the member file names for the IPPS impact zip. Column order is ignored, because
the loader matches columns by name.

Run:  python -m ingest.schema_check            # check (CI/refresh); updates hashes if only data changed
      python -m ingest.schema_check --accept   # after you've reviewed a schema change: write the new lock
"""
import argparse
import json
import os
import sys
import zipfile

import duckdb

from ingest import config as C

LOCK = C.ROOT / "ingest" / "schema_lock.json"
MANIFEST = C.RAW / "manifest.json"
IGNORE_COLUMNS = {"_loaded_at"}  # added by our loader, not part of the source's layout

# manifest name -> raw table whose columns are that source's schema
RAW_TABLE = {
    "hrrp_hospital": "hrrp_hospital",
    "hospital_general_info": "hospital_general_info",
    "hrrp_supplemental": "hrrp_supplemental_original",
    "hrrp_table15": "hrrp_table15_original",
    "hospital_cost_report": "hospital_cost_report",
    "hospital_enrollments": "hospital_enrollments",
    "hospital_all_owners": "hospital_all_owners",
    "zcta_county_rel": "zcta_county_rel",
    "acs_2024_acs5_county": "acs_county",
}


def schema_of(name: str, entry: dict, con) -> list[str] | None:
    """The schema of one downloaded source, or None if it has no column layout (e.g. HTML)."""
    if name in RAW_TABLE:
        cols = con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'raw' AND table_name = ?",
            [RAW_TABLE[name]]).fetchall()
        if not cols:
            raise SystemExit(f"raw.{RAW_TABLE[name]} not found. Run python -m ingest.load before this check.")
        return sorted(c[0] for c in cols if c[0] not in IGNORE_COLUMNS)
    path = C.ROOT / entry["file"]
    if name.startswith("sec_"):
        # companyfacts JSON: the fields each fact carries (start, end, val, fy, form, ...)
        facts = json.loads(path.read_text()).get("facts", {})
        keys = {k for tags in facts.values() for body in tags.values()
                for rows in body.get("units", {}).values() for f in rows for k in f}
        return sorted(keys)
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            return sorted(z.namelist())
    return None


def diff(old: list[str], new: list[str]) -> str:
    added, removed = sorted(set(new) - set(old)), sorted(set(old) - set(new))
    return f"added {added or 'none'}; removed {removed or 'none'}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--accept", action="store_true",
                    help="write the current hashes and schemas to the lock (after reviewing a change)")
    args = ap.parse_args()
    if not MANIFEST.exists():
        sys.exit(f"{MANIFEST.relative_to(C.ROOT)} not found. Run python -m ingest.download first.")
    manifest = json.loads(MANIFEST.read_text())
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {}
    con = duckdb.connect(str(C.DB_PATH), read_only=True)

    problems, refreshed, lines = [], [], []
    new_lock = dict(lock)
    for name, entry in sorted(manifest.items()):
        sha, schema = entry.get("sha256"), schema_of(name, entry, con)
        new_lock[name] = {"sha256": sha, "schema": schema}
        old = lock.get(name)
        if old is None:
            problems.append(f"{name}: new source, not in {LOCK.name}")
            lines.append(f"| {name} | new source | **FAIL** |")
        elif old["sha256"] == sha:
            lines.append(f"| {name} | unchanged | ok |")
        elif old["schema"] == schema:
            refreshed.append(name)
            lines.append(f"| {name} | new file, same schema | ok |")
        else:
            problems.append(f"{name}: file changed (sha256 {old['sha256'][:12]}... -> {sha[:12]}...) and its "
                            f"schema changed: {diff(old['schema'] or [], schema or [])}")
            lines.append(f"| {name} | new file, **schema changed** | **FAIL** |")
    con.close()

    summary = ["## Source schema check", "| Source | Status | Result |", "|---|---|---|", *lines]
    if os.getenv("GITHUB_STEP_SUMMARY"):  # shows as a table on the Actions run page
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write("\n".join(summary + [""] + [f"- {p}" for p in problems]) + "\n")

    if problems and not args.accept:
        print("SCHEMA CHECK FAILED. A source file changed and its layout no longer matches:\n")
        for p in problems:
            print(f"  - {p}")
        print("\nOpen the new file, update ingest/load.py or the staging models if needed, then run\n"
              "  python -m ingest.schema_check --accept\nand commit ingest/schema_lock.json.")
        sys.exit(1)
    if args.accept or refreshed or new_lock.keys() != lock.keys():
        LOCK.write_text(json.dumps(new_lock, indent=2, sort_keys=True) + "\n")
    print(f"Schema check passed: {len(refreshed)} source(s) refreshed with the same schema, "
          f"{len(manifest) - len(refreshed)} unchanged." if not args.accept
          else f"Wrote {LOCK.relative_to(C.ROOT)} for {len(new_lock)} sources.")


if __name__ == "__main__":
    main()
