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
import re
import sys
import time
import zipfile
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from dotenv import load_dotenv

from ingest import config as C

load_dotenv(C.ROOT / ".env")
MANIFEST = C.RAW / "manifest.json"
SESSION = requests.Session()
# Identify the script honestly with a contact address, the convention SEC requires and
# other public data sites prefer. If a site still refuses (403), main() tells you which
# file to download by hand in your browser instead.
_contact = os.getenv("SEC_USER_AGENT", "").strip()
SESSION.headers["User-Agent"] = f"hrrp-penalties research script ({_contact or 'no contact set'})"


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
            status = getattr(getattr(e, "response", None), "status_code", None)
            if attempt == 3 or status in (401, 403, 404):  # retrying won't fix these
                raise
            wait = 2 ** (attempt + 1)
            print(f"  retry in {wait}s after: {e}")
            time.sleep(wait)


def fetch_file(name, url, force=False, extract=False, log_name=None):
    out_dir = C.RAW / name
    out_dir.mkdir(parents=True, exist_ok=True)
    # cms.gov sometimes serves a re-upload as "file.zip-0"; save it as file.zip
    path = out_dir / re.sub(r"\.zip-\d+$", ".zip", url.rsplit("/", 1)[-1])
    if path.exists() and not force:
        print(f"[skip] {name}: {path.name} already downloaded")
        if extract and zipfile.is_zipfile(path):  # e.g. a zip you saved by hand
            with zipfile.ZipFile(path) as z:
                z.extractall(out_dir)
        return path
    print(f"[get ] {name}: {url}")
    with _get(url, stream=True) as r, open(path, "wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    if extract and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            z.extractall(out_dir)
            print(f"       extracted: {z.namelist()}")
    _log({"name": log_name or name, "url": url, "file": str(path.relative_to(C.ROOT)),
          "bytes": path.stat().st_size, "sha256": _sha256(path),
          "downloaded_at": datetime.now(timezone.utc).isoformat()})
    return path


def provider_data_url(metastore_id, fallback):
    """Ask the CMS metastore for the current CSV link (it changes on each refresh)."""
    try:
        meta = _get(f"https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{metastore_id}").json()
    except requests.RequestException as e:
        print(f"  metastore lookup failed ({e}); using the link verified on 2026-11-01")
        return fallback
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
        try:
            json.loads(path.read_text())
            print("[skip] ACS")
            return
        except ValueError:
            print("  existing ACS file is not valid JSON; downloading again")
    params = {"get": ",".join(["NAME", *C.ACS_VARIABLES]), "for": "county:*"}
    # Census now rejects keyless requests with a "Missing Key" page, so a key is required.
    key = os.getenv("CENSUS_API_KEY", "").strip()
    if not key:
        raise ValueError("CENSUS_API_KEY is empty in .env. Get a free key at "
                         "https://api.census.gov/data/key_signup.html, click the activation "
                         "link in the email Census sends, then paste the key into .env.")
    params["key"] = key
    print(f"[get ] ACS 2024 5-year county: {C.ACS_URL}")
    r = _get(C.ACS_URL, params=params)
    # Census can answer 200 OK with an HTML/text message (e.g. a bad or unactivated
    # API key) instead of data. Check before saving so a bad file never reaches load.
    try:
        rows = r.json()
        assert isinstance(rows, list) and rows and rows[0][0] == "NAME"
    except (ValueError, AssertionError, IndexError, TypeError):
        raise ValueError("Census did not return ACS data. First 300 characters of its reply:\n"
                         + r.text[:300].strip()
                         + ("\nTip: if this mentions a key, activate it from the Census email "
                            "or leave CENSUS_API_KEY empty in .env." if key else ""))
    path.write_text(r.text)
    _log({"name": "acs_2024_acs5_county", "url": C.ACS_URL,
          "variables": list(C.ACS_VARIABLES), "file": str(path.relative_to(C.ROOT)),
          "sha256": _sha256(path), "downloaded_at": datetime.now(timezone.utc).isoformat()})


def zip_links_on(page_url: str) -> list[str]:
    """The .zip links on a cms.gov landing page (used when we have no direct link)."""
    html = _get(page_url).text
    links = re.findall(r'href="([^"]+?\.zip(?:-\d+)?)"', html, re.I)
    return [urljoin(page_url, u) for u in dict.fromkeys(links)]


def fetch_hrrp_history(force=False, years=None):
    """Download every year's IPPS HRRP supplemental file; log the years we can't get.

    For each fiscal year: try the URLs in config.HRRP_YEARS, then any .zip linked from the
    year's landing page. Each success goes in the manifest (url, sha256, size) like every
    other source. Each failure goes in data/raw/hrrp_history/missing_years.json with the
    reason, so the panel shows the year as missing instead of silently skipping it.
    """
    C.HRRP_HISTORY_RAW.mkdir(parents=True, exist_ok=True)
    missing = {}
    for fy, spec in C.HRRP_YEARS.items():
        if years and fy not in years:
            continue
        name = f"hrrp_supplemental_fy{fy}"
        folder = C.HRRP_HISTORY_RAW / f"fy{fy}"
        if not force and folder.exists() and any(folder.glob("*.zip")):
            print(f"[skip] {name}: already downloaded")
            for z in folder.glob("*.zip"):
                if zipfile.is_zipfile(z):
                    with zipfile.ZipFile(z) as zf:
                        zf.extractall(folder)
            continue
        tried, errors = list(spec["supplemental_urls"]), []
        got = None
        for url in tried:
            try:
                got = fetch_file(f"hrrp_history/fy{fy}", url, force=force, extract=True, log_name=name)
                break
            except (requests.RequestException, OSError) as e:
                errors.append(f"{url}: {e}")
        if got is None:
            try:
                scraped = [u for u in zip_links_on(spec["landing_page"]) if u not in tried]
                scraped = [u for u in scraped if re.search(r"readmission|hrrp", u, re.I)] or scraped
            except requests.RequestException as e:
                scraped = []
                errors.append(f"{spec['landing_page']}: {e}")
            for url in scraped:
                try:
                    got = fetch_file(f"hrrp_history/fy{fy}", url, force=force, extract=True, log_name=name)
                    break
                except (requests.RequestException, OSError) as e:
                    errors.append(f"{url}: {e}")
        if got is None:
            print(f"[MISS] FY{fy}: no supplemental file could be downloaded")
            missing[str(fy)] = {"landing_page": spec["landing_page"], "errors": errors or ["no .zip link found"],
                                "checked_at": datetime.now(timezone.utc).isoformat()}
    log = json.loads(C.MISSING_YEARS_LOG.read_text()) if C.MISSING_YEARS_LOG.exists() else {}
    for fy in C.HRRP_YEARS:
        if (years is None or fy in years) and str(fy) not in missing:
            log.pop(str(fy), None)  # a year we now have is no longer missing
    log.update(missing)
    C.MISSING_YEARS_LOG.write_text(json.dumps(dict(sorted(log.items())), indent=2) + "\n")
    if missing:
        # A missing year is a gap in the panel, not a broken pipeline: warn and carry on.
        # ingest.load records it in raw.hrrp_history_files and the panel report lists it.
        print(f"\nWARNING: {len(missing)} HRRP year(s) missing: {', '.join('FY' + y for y in missing)}. "
              f"Details in {C.MISSING_YEARS_LOG.relative_to(C.ROOT)}. If CMS still publishes one, save its "
              f"ZIP by hand into data/raw/hrrp_history/fy<YEAR>/ and re-run.")
    return missing


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-download even if present")
    ap.add_argument("--history-only", action="store_true",
                    help="only the FY2016-FY2027 HRRP supplemental files (skip the other sources)")
    args = ap.parse_args()
    C.RAW.mkdir(parents=True, exist_ok=True)

    # Each source is tried on its own, so one refused site doesn't stop the rest.
    failures = []

    def attempt(label, fn, manual_url=None, folder=None):
        try:
            fn()
        except (requests.RequestException, OSError, ValueError) as e:
            print(f"[FAIL] {label}: {e}")
            failures.append((label, manual_url, folder))

    attempt("HRRP history FY2016-FY2027", lambda: fetch_hrrp_history(force=args.force),
            manual_url=C.ARCHIVE_PAGE, folder=C.HRRP_HISTORY_RAW)
    if args.history_only:
        C.FILES, C.CMS_API_DATASETS = {}, {}
    for name, spec in C.FILES.items():
        url = spec.get("url") or spec["fallback_url"]
        attempt(name,
                lambda n=name, s=spec, u=url: fetch_file(
                    n, s.get("url") or provider_data_url(s["metastore_id"], s["fallback_url"]),
                    force=args.force, extract=u.lower().endswith(".zip")),
                manual_url=url, folder=C.RAW / name)
    for name, uuid in C.CMS_API_DATASETS.items():
        attempt(name, lambda n=name, u=uuid: fetch_cms_api(n, u, force=args.force))
    if not args.history_only:
        attempt("SEC companyfacts", lambda: fetch_sec(force=args.force))
        attempt("Census ACS", lambda: fetch_acs(force=args.force))

    if failures:
        print(f"\n{len(failures)} source(s) failed:")
        for label, url, folder in failures:
            print(f"  - {label}")
            if url:
                print(f"      manual fix: open {url} in your browser, save the file into "
                      f"{folder.relative_to(C.ROOT)}/ , then re-run this script")
        sys.exit(1)  # non-zero exit so "download && load && build" stops here
    print(f"\nDone. Manifest: {MANIFEST.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
