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
import io
import json
import re
import zipfile
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
    # _loaded_at lets dbt check how old each raw table is (`dbt source freshness`).
    con.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT *, current_timestamp AS _loaded_at FROM _df")
    con.unregister("_df")
    print(f"  {table:45s} {len(df):>9,} rows  {len(df.columns)} cols")


def read_csv_text(path, **kw):
    """Read a CSV as text. `path` can also be the raw bytes of a file inside a ZIP."""
    for enc in ("utf-8", "cp1252"):
        try:
            src = io.BytesIO(path) if isinstance(path, bytes) else path
            return pd.read_csv(src, dtype=str, keep_default_na=False, encoding=enc, **kw)
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


def pick_sheet(folder: Path):
    """The data sheet in a folder: has a CCN header and an adjustment-factor column.

    Older HRRP files may carry the factor only in Table 15, so a sheet with a CCN and an
    excess-readmission-ratio column is accepted as a second choice. Returns
    (label, DataFrame with the sheet's own header names, name of the CCN column) or None.
    """
    second = None
    for label, raw in read_tables(folder):
        h = find_header_row(raw)
        if h is None:
            continue
        df = raw.iloc[h + 1:].copy()
        df.columns = [str(c).strip() for c in raw.iloc[h].tolist()]
        df = df.loc[:, [c for c in df.columns if c and c.lower() != "nan"]]
        df = df.dropna(how="all")
        ccn_cols = match(df.columns, *HOSPITAL_FIELDS["ccn"])
        if not ccn_cols:
            continue
        if match(df.columns, *HOSPITAL_FIELDS["payment_adjustment_factor"]):
            return label, df, ccn_cols[0]
        if second is None and match(df.columns, r"\berr\b|excess.?readmission.?ratio", None):
            second = (label, df, ccn_cols[0])
    return second


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


# ---------- multi-year HRRP panel (FY2016-FY2027) ------------------------------------
def _unique_norm(cols) -> list[str]:
    """snake_case names, with _2, _3 ... added if two headers normalise to the same name."""
    seen, out = {}, []
    for c in cols:
        n = norm(c) or "unnamed"
        seen[n] = seen.get(n, 0) + 1
        out.append(n if seen[n] == 1 else f"{n}_{seen[n]}")
    return out


def years_named(label: str) -> set[int]:
    """Four-digit fiscal years a CMS file or sheet name states ("FY 2024", "FY2024", "fy_2019")."""
    return {int(y) for y in re.findall(r"(?i)\bfy[\s_-]?(20\d\d)", label)}


def load_hrrp_history(con):
    """Every year's supplemental sheet, stacked into raw.hrrp_supplemental_history.

    The sheets are NOT renamed to a common layout here: each keeps its own (snake_case)
    column names, and a column that a year doesn't have is NULL for that year. The
    harmonising (which column is the ERR in FY2017 vs FY2026) happens in dbt, in
    stg_hrrp_supplemental_history, where it is visible and tested. Two helper columns:
      fiscal_year  - the HRRP payment year of the folder the file came from
      source_ccn   - the cell from the column this loader used to find the header row
    raw.hrrp_history_files gets one row per year: loaded, or missing and why.
    """
    frames, files = [], []
    missing_log = json.loads(C.MISSING_YEARS_LOG.read_text()) if C.MISSING_YEARS_LOG.exists() else {}
    for fy in C.HRRP_YEARS:
        folder = C.HRRP_HISTORY_RAW / f"fy{fy}"
        picked = pick_sheet(folder) if folder.exists() else None
        if picked is None:
            why = ("not downloaded: " + "; ".join(missing_log[str(fy)]["errors"])[:500]
                   if str(fy) in missing_log else
                   "no folder" if not folder.exists() else "no sheet with a CCN column and a factor or ERR column")
            files.append((fy, "missing", None, None, None, why))
            print(f"  hrrp history FY{fy}: MISSING ({why[:80]})")
            continue
        label, df, ccn_col = picked
        named = years_named(label)
        if named and fy not in named:
            # A CMS link can serve another year's file (FY2023's archive link served FY2024's).
            # Loading it would duplicate that year under the wrong label, so treat it as missing.
            why = (f"wrong year: {label} names FY{', FY'.join(map(str, sorted(named)))}. Delete "
                   f"data/raw/hrrp_history/fy{fy}/ and download again (see ingest/config.py HRRP_YEARS)")
            files.append((fy, "missing", label, None, None, why))
            print(f"  hrrp history FY{fy}: WRONG YEAR, not loaded ({why})")
            continue
        out = df.copy()
        out.columns = _unique_norm(df.columns)
        out.insert(0, "source_ccn", df[ccn_col].to_numpy())
        out.insert(0, "source_file", label)
        out.insert(0, "fiscal_year", str(fy))
        frames.append(out.astype("string"))
        files.append((fy, "loaded", label, str(len(out)), str(len(df.columns)), None))
        print(f"  hrrp history FY{fy}: {label}, {len(out):,} rows, {len(df.columns)} columns")
    if frames:
        load_df(con, "raw.hrrp_supplemental_history", pd.concat(frames, ignore_index=True, sort=False))
    load_df(con, "raw.hrrp_history_files", pd.DataFrame(
        files, columns=["fiscal_year", "status", "source_file", "rows", "columns", "note"]))
    load_df(con, "raw.hrrp_program_years", pd.DataFrame([
        {"fiscal_year": fy, "period_start": s["period"][0], "period_end": s["period"][1],
         "period_checked": s["period_checked"], "period_source": s.get("period_source"),
         "landing_page": s["landing_page"], "note": s.get("note")}
        for fy, s in C.HRRP_YEARS.items()]))


def _fy_from_pdc(member: str, df: pd.DataFrame) -> int | None:
    """HRRP payment year of a Provider Data Catalog HRRP file.

    First the "FY_2026" in the file name; otherwise match the file's End Date to a
    period end in config.HRRP_YEARS. None if neither works (the file is then skipped
    and reported, not guessed).
    """
    m = re.search(r"fy[ _-]?(20\d\d)", member, re.I)
    if m:
        return int(m.group(1))
    if "end_date" in df.columns:
        ends = pd.to_datetime(df["end_date"], errors="coerce", format="mixed").dropna()
        if not ends.empty:
            end = ends.mode().iloc[0].date().isoformat()
            for fy, spec in C.HRRP_YEARS.items():
                if spec["period"][1] == end:
                    return fy
    return None


def _pdc_members(path: Path, depth=0):
    """(member name, bytes) of every HRRP CSV in an archive ZIP (and ZIPs inside it)."""
    with zipfile.ZipFile(path) as z:
        for info in z.infolist():
            name = info.filename
            if name.lower().endswith(".zip") and depth == 0:
                inner = C.PDC_ARCHIVE_RAW / "_inner" / Path(name).name
                inner.parent.mkdir(parents=True, exist_ok=True)
                inner.write_bytes(z.read(info))
                yield from _pdc_members(inner, depth + 1)
            elif (name.lower().endswith(".csv") and re.search(r"readmissions?.?reduction|hrrp", name, re.I)
                  and "description" not in name.lower()):
                yield name, z.read(info)


def load_hrrp_hospital_history(con, current: pd.DataFrame):
    """Per-hospital HRRP files of every year, stacked into raw.hrrp_hospital_history.

    The current year's file (raw.hrrp_hospital) is always included as snapshot
    'current'. Archived years come from ZIPs saved by hand in data/raw/pdc_archive/.
    One HRRP year shows up in many monthly snapshots; all are kept here (with the
    snapshot name) and dbt keeps the latest one per year.
    """
    cur = current.copy()
    cur.columns = _unique_norm(current.columns)
    frames = [cur.assign(fiscal_year=str(C.PROGRAM_YEAR), snapshot="current")]
    if C.PDC_ARCHIVE_RAW.exists():
        for z in sorted(C.PDC_ARCHIVE_RAW.glob("*.zip")):
            for member, blob in _pdc_members(z):
                df = read_csv_text(blob)
                df.columns = _unique_norm(df.columns)
                fy = _fy_from_pdc(member, df)
                if fy is None:
                    print(f"  pdc archive {z.name}:{member}: fiscal year not recognised, skipped")
                    continue
                frames.append(df.assign(fiscal_year=str(fy), snapshot=f"{z.name}:{member}"))
                print(f"  pdc archive FY{fy}: {z.name}:{member} ({len(df):,} rows)")
    load_df(con, "raw.hrrp_hospital_history", pd.concat(frames, ignore_index=True, sort=False))


def main():
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(C.DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw;")
    con.execute("CREATE OR REPLACE TABLE raw.column_mapping_log "
                "(source VARCHAR, field VARCHAR, matched_column VARCHAR, all_candidates VARCHAR)")
    print("Loading raw tables:")

    hrrp_hospital = read_csv_text(only_file(C.RAW / "hrrp_hospital", "*.csv"))
    load_df(con, "raw.hrrp_hospital", hrrp_hospital)
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

    print("\nMulti-year HRRP panel:")
    load_hrrp_history(con)
    load_hrrp_hospital_history(con, hrrp_hospital)

    # The seeds/ CSVs are loaded by `dbt seed` (part of `python -m models.build`).

    print("\nColumn mapping for the IPPS spreadsheets (NULL = not found, left empty):")
    for r in con.execute("SELECT source, field, matched_column FROM raw.column_mapping_log").fetchall():
        print(f"  {r[0]:18s} {r[1]:32s} <- {r[2]}")
    con.close()


if __name__ == "__main__":
    main()
