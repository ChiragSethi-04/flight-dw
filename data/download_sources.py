"""Downloads S1-S4 source files for the flight-dw warehouse into data/raw/.

Usage:
    python data/download_sources.py                # download everything for DATA_YEAR
    python data/download_sources.py --year 2025     # override the year
    python data/download_sources.py --only s1       # just one source (s1, s2, s3, s4)
    python data/download_sources.py --force         # re-download even if present and size matches

Resumable: a file already present with a size matching the server's
Content-Length is skipped, so a second run only fetches what is missing or
changed. Every attempt is logged to logs/download_<timestamp>.log with size
and a sha256 checksum. On a hard failure (non-200 response) the script
prints the exact URL and does not retry with a mirror. S4 (BTS lookup
tables) is a known, verified exception: see BTS_LOOKUP_URLS below and
docs/DECISIONS.md. A failed S4 download is reported as "blocked", with the
exact manual-download instructions, and does not stop S1-S3.
"""
import argparse
import hashlib
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import certifi
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT_DIR / "data" / "raw"
LOG_DIR = ROOT_DIR / "logs"

load_dotenv(ROOT_DIR / ".env")

# The system Python on macOS does not always ship a working CA bundle for
# the ssl module (separate from curl, which uses the OS trust store), so
# urlopen is given certifi's bundle explicitly rather than skipping
# certificate verification.
SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())


class NoRedirect(urllib.request.HTTPRedirectHandler):
    """Turns a 3xx into a raised HTTPError instead of silently following it.

    Without this, a dead link that 302-redirects to an unrelated page (as
    the BTS lookup endpoints do, to Homepage.asp) looks like a successful
    200 download of the wrong content, which is worse than a loud failure.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


OPENER = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=SSL_CONTEXT))

USER_AGENT = "flight-dw-coursework-etl/0.1 (+https://github.com/ChiragSethi-04/flight-dw)"
TIMEOUT_SECONDS = 120
CHUNK_SIZE = 1024 * 256

BTS_PREZIP_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)
NOAA_BASE_URL = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/"
OPENFLIGHTS_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airports.dat"

# Verified by hand on 2026-11-17 (see docs/DECISIONS.md): the lookup page
# itself and every Lookup= query redirect with HTTP 302 to Homepage.asp,
# with or without a session cookie and with or without browser-like
# headers. This looks like the old ASP lookup-download mechanism having
# been retired, not a transient error, so the script reports it as
# "blocked" rather than treating it as a hard failure.
BTS_LOOKUP_URLS = {
    "L_UNIQUE_CARRIERS.csv": "https://www.transtats.bts.gov/Download_Lookup.asp?Lookup=L_UNIQUE_CARRIERS",
    "L_AIRPORT_ID.csv": "https://www.transtats.bts.gov/Download_Lookup.asp?Lookup=L_AIRPORT_ID",
    "L_CANCELLATION.csv": "https://www.transtats.bts.gov/Download_Lookup.asp?Lookup=L_CANCELLATION",
}


@dataclass
class DownloadResult:
    name: str
    url: str
    dest: Path
    status: str  # ok, skipped, blocked, failed
    size_bytes: int = 0
    sha256: str = ""
    note: str = ""


class DownloadContentError(Exception):
    """Raised when a response has HTTP 200 but is clearly the wrong thing,
    e.g. an HTML error/landing page where a CSV or zip was expected. This
    exists because a redirect-following client can otherwise mistake a
    homepage for a successful download (see docs/DECISIONS.md, item B1).
    """


LOG_LINES: List[str] = []


def log(line: str) -> None:
    stamped = f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {line}"
    print(stamped, flush=True)
    LOG_LINES.append(stamped)


def remote_content_length(url: str) -> Optional[int]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with OPENER.open(req, timeout=TIMEOUT_SECONDS) as resp:
            length = resp.headers.get("Content-Length")
            return int(length) if length is not None else None
    except (urllib.error.URLError, OSError):
        return None


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
            h.update(chunk)
    return h.hexdigest()


MAX_ATTEMPTS = 4
RETRY_BACKOFF_SECONDS = 5

# Network-level errors worth retrying: a connection reset or timeout mid
# transfer is transient (this sandboxed network resets connections
# occasionally even on a URL that works fine on retry), unlike a 404 or
# the S4 redirect, which will not fix itself. OSError covers
# ConnectionResetError, TimeoutError and ssl.SSLError (all subclasses).
TRANSIENT_ERRORS = (urllib.error.URLError, OSError)


def download(name: str, url: str, dest: Path, force: bool = False) -> DownloadResult:
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.exists() and not force:
        expected = remote_content_length(url)
        actual = dest.stat().st_size
        if expected is not None and expected == actual:
            checksum = sha256_of(dest)
            log(f"SKIP  {name}: already present, size matches ({actual} bytes)")
            return DownloadResult(name, url, dest, "skipped", actual, checksum)
        log(
            f"WARN  {name}: existing file size ({actual}) does not match "
            f"server ({expected}), re-downloading"
        )

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    tmp_dest = dest.with_suffix(dest.suffix + ".part")
    last_exc: Optional[Exception] = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with OPENER.open(req, timeout=TIMEOUT_SECONDS) as resp:
                if resp.status != 200:
                    raise urllib.error.HTTPError(url, resp.status, "non-200 status", resp.headers, None)
                h = hashlib.sha256()
                total = 0
                with open(tmp_dest, "wb") as out:
                    while True:
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                        h.update(chunk)
                        total += len(chunk)
            with open(tmp_dest, "rb") as f:
                head_bytes = f.read(512).lstrip().lower()
            if head_bytes.startswith(b"<!doctype html") or head_bytes.startswith(b"<html"):
                raise DownloadContentError(
                    f"response body looks like an HTML page, not the expected "
                    f"file (first bytes: {head_bytes[:80]!r})"
                )
            tmp_dest.replace(dest)
            log(f"OK    {name}: downloaded {total} bytes, sha256={h.hexdigest()}")
            return DownloadResult(name, url, dest, "ok", total, h.hexdigest())
        except urllib.error.HTTPError as exc:
            # A real HTTP error status (404, 302-turned-error, etc.) will
            # not fix itself on retry, unlike a dropped connection.
            if tmp_dest.exists():
                tmp_dest.unlink()
            log(f"FAIL  {name}: {exc}  url={url}")
            return DownloadResult(name, url, dest, "failed", note=f"{exc} url={url}")
        except DownloadContentError as exc:
            if tmp_dest.exists():
                tmp_dest.unlink()
            log(f"FAIL  {name}: {exc}  url={url}")
            return DownloadResult(name, url, dest, "failed", note=f"{exc} url={url}")
        except TRANSIENT_ERRORS as exc:
            last_exc = exc
            if tmp_dest.exists():
                tmp_dest.unlink()
            if attempt < MAX_ATTEMPTS:
                log(
                    f"RETRY {name}: attempt {attempt}/{MAX_ATTEMPTS} failed "
                    f"({exc!r}), retrying in {RETRY_BACKOFF_SECONDS}s"
                )
                time.sleep(RETRY_BACKOFF_SECONDS)
            else:
                log(f"FAIL  {name}: {exc}  url={url}  (gave up after {MAX_ATTEMPTS} attempts)")

    return DownloadResult(
        name, url, dest, "failed", note=f"{last_exc} url={url} (gave up after {MAX_ATTEMPTS} attempts)"
    )


def download_s1_bts(year: int, force: bool) -> List[DownloadResult]:
    log(f"== S1 BTS Reporting Carrier On-Time Performance, year {year} ==")
    results = []
    for month in range(1, 13):
        url = BTS_PREZIP_URL.format(year=year, month=month)
        dest = (
            RAW_DIR
            / "bts"
            / f"On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
        )
        results.append(download(f"S1 {year}-{month:02d}", url, dest, force))
    return results


def download_s2_noaa(force: bool) -> List[DownloadResult]:
    log("== S2 NOAA GHCN-Daily station list and inventory ==")
    results = []
    for fname in ("ghcnd-stations.txt", "ghcnd-inventory.txt"):
        url = NOAA_BASE_URL + fname
        dest = RAW_DIR / "noaa" / fname
        results.append(download(f"S2 {fname}", url, dest, force))
    log(
        "Per-station daily weather files are downloaded in a later phase, "
        "only for the stations actually selected by the airport-to-station "
        "map (see docs/BUILD_PLAN.md Phase 1 scope note)."
    )
    return results


def download_s2_noaa_daily_by_year(year: int, force: bool) -> List[DownloadResult]:
    """Phase 4: the actual per-station daily weather values, needed once
    airport_station_map exists and the stations to keep are known.

    Downloading all ~1,225 matched stations individually (one HTTP
    request per station) would mean over a thousand separate requests.
    NOAA also publishes one bulk file per year with every station's
    every observation worldwide (by_year/<year>.csv.gz, about 158MB for
    2025), which is filtered down to the stations actually needed after
    downloading, in etl/extract.py. One download instead of 1,225.
    """
    log(f"== S2 NOAA GHCN-Daily, full year bulk file for {year} ==")
    url = f"{NOAA_BASE_URL}by_year/{year}.csv.gz"
    dest = RAW_DIR / "noaa" / f"by_year_{year}.csv.gz"
    return [download(f"S2 by_year_{year}.csv.gz", url, dest, force)]


def download_s3_openflights(force: bool) -> List[DownloadResult]:
    log("== S3 OpenFlights airports.dat ==")
    dest = RAW_DIR / "openflights" / "airports.dat"
    return [download("S3 airports.dat", OPENFLIGHTS_URL, dest, force)]


def download_s4_bts_lookups(force: bool) -> List[DownloadResult]:
    log("== S4 BTS lookup tables (carriers, airports, cancellation codes) ==")
    results = []
    for fname, url in BTS_LOOKUP_URLS.items():
        dest = RAW_DIR / "bts_lookup" / fname
        result = download(f"S4 {fname}", url, dest, force)
        if result.status == "failed":
            result.status = "blocked"
            log(
                f"STOP  S4 {fname} could not be downloaded automatically. "
                f"The BTS lookup page ({url}) redirects away from the file "
                f"rather than serving it. ACTION NEEDED: a human should "
                f"open {url} in a real browser, and if that succeeds where "
                f"this script did not, save the result to {dest}. "
                f"Do not substitute a mirror."
            )
        results.append(result)
    return results


def print_summary(results: List[DownloadResult]) -> None:
    log("")
    log("== Summary ==")
    log(f"{'status':<8} {'size_bytes':>12}  {'sha256 (first 12 hex chars)':<14}  name")
    for r in results:
        short_sha = (r.sha256[:12] + "...") if r.sha256 else "-"
        log(f"{r.status:<8} {r.size_bytes:>12}  {short_sha:<14}  {r.name}")
    counts = {}
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
    log(f"Totals: {counts}")


def write_log_file() -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = LOG_DIR / f"download_{ts}.log"
    path.write_text("\n".join(LOG_LINES) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    env_year = os.environ.get("DATA_YEAR")
    parser.add_argument("--year", type=int, default=int(env_year) if env_year else None)
    parser.add_argument("--only", choices=["s1", "s2", "s3", "s4", "s2-daily"], action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.year is None:
        print(
            "No data year given. Set DATA_YEAR in .env or pass --year. "
            "See docs/DECISIONS.md for the verified recommendation.",
            file=sys.stderr,
        )
        return 2

    # s2-daily is Phase 4 work (needs airport_station_map to exist first)
    # and is deliberately not part of the default S1-S4 bundle.
    which = set(args.only) if args.only else {"s1", "s2", "s3", "s4"}
    all_results: List[DownloadResult] = []

    if "s1" in which:
        all_results += download_s1_bts(args.year, args.force)
    if "s2" in which:
        all_results += download_s2_noaa(args.force)
    if "s3" in which:
        all_results += download_s3_openflights(args.force)
    if "s4" in which:
        all_results += download_s4_bts_lookups(args.force)
    if "s2-daily" in which:
        all_results += download_s2_noaa_daily_by_year(args.year, args.force)

    print_summary(all_results)
    log_path = write_log_file()
    log(f"Full log written to {log_path}")

    hard_failures = [r for r in all_results if r.status == "failed"]
    if hard_failures:
        log(f"{len(hard_failures)} source(s) failed outright (not just S4-blocked). See above.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
