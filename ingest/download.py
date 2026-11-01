"""Step 1: download every source into data/raw/ exactly as published.

Why keep raw files untouched: if a number looks odd later, you can always trace it
back to the file CMS/SEC/Census actually served. Every download is logged in
data/raw/manifest.json with its URL, time, size and SHA-256 hash.

Run:  python -m ingest.download            (skips files already downloaded)
      python -m ingest.download --force    (re-download everything)
"""
import argparse
import hashlib
import json
import os
import sys
import time
import zipfile
from datetime import datetime, timezone

import requests
from dotenv import load_dotenv

from ingest import config as C

load_dotenv(C.ROOT / ".env")
MANIFEST = C.RAW / "manifest.json"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "hrrp-penalties portfolio project (python-requests)"


def _log(entry: dict) -> None:
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    manifest[entry["name"]] = entry
    MANIFEST.write_text(json.dumps(manifest, indent=2))


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _get(url, **kw):
    """GET with a few retries; CMS and Census occasionally time out."""
    for attempt in range(4):
        try:
            r = SESSION.get(url, timeout=120, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException as e:
            if attempt == 3:
                raise
            wait = 2 ** (attempt + 1)
            print(f"  retry in {wait}s after: {e}")
            time.sleep(wait)


def fetch_file(name, url, force=False, extract=False):
    out_dir = C.RAW / name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / url.rsplit("/", 1)[-1]
    if path.exists() and not force:
        print(f"[skip] {name}: {path.name} already downloaded")
        return path
    print(f"[get ] {name}: {url}")
    with _get(url, stream=True) as r, open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    if extract and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            z.extractall(out_dir)
            print(f"       extracted: {z.namelist()}")
    _log({"name": name, "url": url, "file": str(path.relative_to(C.ROOT)),
          "bytes": path.stat().st_size, "sha256": _sha256(path),
          "downloaded_at": datetime.now(timezone.utc).isoformat()})
    return path


def provider_data_url(metastore_id, fallback):
    """Ask the CMS metastore for the current CSV link (it changes on each refresh)."""
    meta = _get(f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{metastore_id}").json()
    urls = [d.get("downloadURL") for d in meta.get("distribution", []) if d.get("downloadURL")]
    if not urls:
        print(f"  metastore gave no downloadURL for {metastore_id}; using fallback")
        return fallback
    if urls[0] != fallback:
        print(f"  note: CMS has refreshed {metastore_id} since 2026-11-01 -> {urls[0]}")
    return urls[0]


def fetch_cms_api(name, uuid, force=False):
    """Page through a data.cms.gov data-api dataset and save it as JSON lines."""
    out_dir = C.RAW / name
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.jsonl"
    if path.exists() and not force:
        print(f"[skip] {name}: already downloaded")
        return path
    url = C.CMS_DATA_API.format(uuid=uuid)
    print(f"[get ] {name}: {url}")
    n, offset = 0, 0
    with open(path, "w") as f:
        while True:
            rows = _get(url, params={"size": C.CMS_PAGE_SIZE, "offset": offset}).json()
            if not rows:
                break
            for row in rows:
                f.write(json.dumps(row) + "\n")
            n += len(rows)
            offset += C.CMS_PAGE_SIZE
            print(f"       {n:,} rows", end="\r")
    print(f"       {n:,} rows total")
    _log({"name": name, "url": url, "file": str(path.relative_to(C.ROOT)), "rows": n,
          "sha256": _sha256(path), "downloaded_at": datetime.now(timezone.utc).isoformat()})
    return path


def fetch_sec(force=False):
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if not ua or "@" not in ua:
        sys.exit("SEC_USER_AGENT missing in .env. SEC requires 'Your Name your.email@example.com'.")
    out_dir = C.RAW / "sec_companyfacts"
    out_dir.mkdir(parents=True, exist_ok=True)
    for company, cik in C.SEC_COMPANIES.items():
        url = C.SEC_COMPANYFACTS.format(cik=cik)
        path = out_dir / f"CIK{cik:010d}.json"
        if path.exists() and not force:
            print(f"[skip] SEC {company}")
            continue
        print(f"[get ] SEC {company}: {url}")
        r = _get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"})
        path.write_bytes(r.content)
        _log({"name": f"sec_{cik}", "url": url, "file": str(path.relative_to(C.ROOT)),
              "sha256": _sha256(path), "downloaded_at": datetime.now(timezone.utc).isoformat()})
        time.sleep(1 / C.SEC_MAX_REQUESTS_PER_SEC + 0.05)  # stay under SEC's limit


def fetch_acs(force=False):
    out_dir = C.RAW / "acs_2024_acs5_county"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "acs_county.json"
    if path.exists() and not force:
        print("[skip] ACS")
        return
    params = {"get": ",".join(["NAME", *C.ACS_VARIABLES]), "for": "county:*"}
    key = os.getenv("CENSUS_API_KEY", "").strip()
    if key:
        params["key"] = key
    print(f"[get ] ACS 2024 5-year county: {C.ACS_URL}")
    r = _get(C.ACS_URL, params=params)
    path.write_text(r.text)
    _log({"name": "acs_2024_acs5_county", "url": C.ACS_URL,
          "variables": list(C.ACS_VARIABLES), "file": str(path.relative_to(C.ROOT)),
          "sha256": _sha256(path), "downloaded_at": datetime.now(timezone.utc).isoformat()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    args = ap.parse_args()
    C.RAW.mkdir(parents=True, exist_ok=True)

    for name, spec in C.FILES.items():
        url = spec.get("url") or provider_data_url(spec["metastore_id"], spec["fallback_url"])
        fetch_file(name, url, force=args.force, extract=url.lower().endswith(".zip"))
    for name, uuid in C.CMS_API_DATASETS.items():
        fetch_cms_api(name, uuid, force=args.force)
    fetch_sec(force=args.force)
    fetch_acs(force=args.force)
    print(f"\nDone. Manifest: {MANIFEST.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
