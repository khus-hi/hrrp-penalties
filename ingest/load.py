"""Step 2: load data/raw/ into a local DuckDB file (data/hrrp.duckdb).

Design choices worth explaining in an interview:
  * Everything lands in a `raw` schema as text (VARCHAR). Type casting happens later
    in SQL staging models, where a bad value becomes NULL *and gets counted*, instead
    of silently breaking the load or being coerced.
  * Column names are normalised to snake_case so the CSV download and the API agree
    (e.g. "County/Parish" -> countyparish, "ASSOCIATE ID - OWNER" -> associate_id_owner).
  * The FY2026 IPPS spreadsheets have no published column list, so their columns are
    matched by pattern to the fields we need. Every match (or miss) is written to
    raw.column_mapping_log; a miss becomes a NULL column, never a guess.

Run:  python -m ingest.load
"""
import json
import re
from pathlib import Path

import duckdb
import pandas as pd

from ingest import config as C

CONDITIONS = {
    "ami": r"\bami\b|myocardial",
    "hf": r"\bhf\b|heart.?failure",
    "pn": r"\bpn\b|pneumonia",
    "copd": r"copd",
    "cabg": r"cabg|bypass",
    "tha_tka": r"\btha\b|\btka\b|hip|knee",
}
# Metric patterns for the per-condition columns of the supplemental file.
COND_METRICS = {
    "err": (r"\berr\b|excess.?readmission.?ratio", r"median|peer"),
    "peer_median_err": (r"median", None),
    "eligible_discharges": (r"discharge|number.?of.?(eligible|cases)", r"readmission"),
    "penalty_indicator": (r"penalty.?indicator|penalized", None),
    "drg_payment_ratio": (r"payment.?ratio|drg.?payment|ratio.?of.?(base|drg)", r"excess.?readmission"),
}
HOSPITAL_FIELDS = {
    "ccn": (r"\bccn\b|provider.?(number|id|ccn)|^provider$|facility.?id", None),
    "payment_adjustment_factor": (r"adjustment.?factor", r"neutral|peer"),
    "payment_reduction_pct": (r"reduction.?(percent|pct|%)|percent.?reduction", None),
    "dual_proportion": (r"dual.?(proportion|eligible.?(share|proportion|ratio))", None),
    "peer_group": (r"peer.?group(?!.?median)", r"median"),
    "neutrality_modifier": (r"neutrality", None),
}


def norm(col: str) -> str:
    c = str(col).strip().lower()
    c = re.sub(r"[\s\-]+", "_", c)
    c = re.sub(r"[^a-z0-9_]", "", c)
    return re.sub(r"_+", "_", c).strip("_")


def load_df(con, table, df):
    df = df.copy()
    df.columns = [norm(c) for c in df.columns]
    df = df.astype("string")
    con.register("_df", df)
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM _df")
    con.unregister("_df")
    print(f"  {table:45s} {len(df):>9,} rows  {len(df.columns)} cols")


def read_csv_text(path, **kw):
    for enc in ("utf-8", "cp1252"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc, **kw)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path}")


def only_file(folder: Path, pattern: str) -> Path:
    hits = sorted(folder.glob(pattern))
    if not hits:
        raise FileNotFoundError(f"no {pattern} in {folder}; run python -m ingest.download first")
    return hits[0]


# ---------- spreadsheets with unknown layout (FY2026 IPPS HRRP files) --------------
def find_header_row(raw: pd.DataFrame) -> int | None:
    for i in range(min(25, len(raw))):
        cells = [str(v) for v in raw.iloc[i].tolist() if pd.notna(v) and str(v).strip()]
        if len(cells) >= 2 and any(re.search(HOSPITAL_FIELDS["ccn"][0], c, re.I) for c in cells):
            return i
    return None


def read_tables(folder: Path):
    """Yield (sheet_label, DataFrame) for the data tables in a folder.

    CMS zips mix the data spreadsheet with .txt copies and "Variable Description"
    notes. Prefer the spreadsheet; only fall back to delimited text when there is none.
    """
    files = sorted(p for p in folder.rglob("*") if p.is_file())
    sheets = [p for p in files if p.suffix.lower() in (".xlsx", ".xls")]
    if sheets:
        for p in sheets:
            for sheet, raw in pd.read_excel(p, sheet_name=None, header=None, dtype=str).items():
                yield f"{p.name}:{sheet}", raw
        return
    for p in files:
        if p.suffix.lower() in (".csv", ".txt") and "description" not in p.name.lower():
            sep = "\t" if "\t" in p.read_text(errors="ignore")[:2000] else ","
            yield p.name, read_csv_text(p, header=None, sep=sep, on_bad_lines="skip")


def match(cols, include, exclude):
    out = [c for c in cols if re.search(include, c, re.I) and not (exclude and re.search(exclude, c, re.I))]
    return out


def map_ipps_table(con, source: str, folder: Path, wanted_conditions: bool):
    """Pick the sheet that has CCN + adjustment factor, then map columns by pattern."""
    best = None
    for label, raw in read_tables(folder):
        h = find_header_row(raw)
        if h is None:
            continue
        df = raw.iloc[h + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[h].tolist()]
        df = df.loc[:, [c for c in df.columns if c and c.lower() != "nan"]]
        df = df.dropna(how="all")
        if match(df.columns, *HOSPITAL_FIELDS["payment_adjustment_factor"]):
            best = (label, df)
            break
    if best is None:
        raise RuntimeError(f"{source}: no sheet with a CCN column and an adjustment-factor column "
                           f"in {folder}. Open the file and add patterns in ingest/load.py.")
    label, df = best
    print(f"  {source}: using {label}; columns = {list(df.columns)}")
    load_df(con, f"raw.{source}_original", df)  # keep the untouched sheet too

    log, out = [], pd.DataFrame(index=df.index)
    fields = dict(HOSPITAL_FIELDS)
    for name, (inc, exc) in fields.items():
        hits = match(df.columns, inc, exc)
        out[name] = df[hits[0]] if hits else pd.NA
        log.append((source, name, hits[0] if hits else None, "; ".join(hits)))
    if wanted_conditions:
        for cond, cpat in CONDITIONS.items():
            ccols = [c for c in df.columns if re.search(cpat, c, re.I)]
            for metric, (inc, exc) in COND_METRICS.items():
                hits = match(ccols, inc, exc)
                name = f"{metric}_{cond}"
                out[name] = df[hits[0]] if hits else pd.NA
                log.append((source, name, hits[0] if hits else None, "; ".join(hits)))
    load_df(con, f"raw.{source}", out)
    con.executemany("INSERT INTO raw.column_mapping_log VALUES (?, ?, ?, ?)", log)


# ---------- SEC companyfacts JSON -> long table -----------------------------------------
def load_sec(con):
    rows = []
    for p in sorted((C.RAW / "sec_companyfacts").glob("CIK*.json")):
        j = json.loads(p.read_text())
        for taxonomy, tags in j.get("facts", {}).items():
            for tag, body in tags.items():
                for unit, facts in body.get("units", {}).items():
                    for f in facts:
                        rows.append({
                            "cik": str(j.get("cik")), "entity_name": j.get("entityName"),
                            "taxonomy": taxonomy, "tag": tag, "label": body.get("label"),
                            "unit": unit, "start_date": f.get("start"), "end_date": f.get("end"),
                            "val": f.get("val"), "fy": f.get("fy"), "fp": f.get("fp"),
                            "form": f.get("form"), "filed": f.get("filed"),
                            "frame": f.get("frame"), "accn": f.get("accn"),
                        })
    load_df(con, "raw.sec_facts", pd.DataFrame(rows))


def load_acs(con):
    path = C.RAW / "acs_2024_acs5_county" / "acs_county.json"
    try:
        data = json.loads(path.read_text())
    except ValueError:
        raise SystemExit(f"{path.relative_to(C.ROOT)} is not Census data (starts with: "
                         f"{path.read_text()[:120]!r}). Delete it and re-run python -m ingest.download.")
    df = pd.DataFrame(data[1:], columns=data[0]).rename(columns=C.ACS_VARIABLES)
    load_df(con, "raw.acs_county", df)


def main():
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(C.DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw; CREATE SCHEMA IF NOT EXISTS seed;")
    con.execute("CREATE OR REPLACE TABLE raw.column_mapping_log "
                "(source VARCHAR, field VARCHAR, matched_column VARCHAR, all_candidates VARCHAR)")
    print("Loading raw tables:")

    load_df(con, "raw.hrrp_hospital", read_csv_text(only_file(C.RAW / "hrrp_hospital", "*.csv")))
    load_df(con, "raw.hospital_general_info",
            read_csv_text(only_file(C.RAW / "hospital_general_info", "*.csv")))
    map_ipps_table(con, "hrrp_supplemental", C.RAW / "hrrp_supplemental", wanted_conditions=True)
    map_ipps_table(con, "hrrp_table15", C.RAW / "hrrp_table15", wanted_conditions=False)

    for name in C.CMS_API_DATASETS:
        df = pd.read_json(C.RAW / name / f"{name}.jsonl", lines=True, dtype=str)
        load_df(con, f"raw.{name}", df)

    load_df(con, "raw.zcta_county_rel",
            read_csv_text(only_file(C.RAW / "zcta_county_rel", "*.txt"), sep="|"))
    load_sec(con)
    load_acs(con)

    for seed in sorted((C.ROOT / "seeds").glob("*.csv")):
        load_df(con, f"seed.{seed.stem}", read_csv_text(seed))

    print("\nColumn mapping for the IPPS spreadsheets (NULL = not found, left empty):")
    for r in con.execute("SELECT source, field, matched_column FROM raw.column_mapping_log").fetchall():
        print(f"  {r[0]:18s} {r[1]:32s} <- {r[2]}")
    con.close()


if __name__ == "__main__":
    main()
