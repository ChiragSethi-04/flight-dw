# Phase 1 walkthrough: source acquisition

## What was built

- **`data/download_sources.py`.** One script that downloads all four
  sources into `data/raw/`, organised as `data/raw/bts/`,
  `data/raw/noaa/`, `data/raw/openflights/`, `data/raw/bts_lookup/`. It
  is resumable (a file already present with a size matching the server's
  `Content-Length` is skipped), computes a sha256 checksum for everything
  it touches, and writes a timestamped log to `logs/` as well as to
  stdout. A hard failure prints the exact URL rather than trying a
  mirror, per the brief's own instruction.
- **`docs/source_columns.md`.** The real column list for S1 and S3,
  taken from an actual downloaded file rather than assumed from the
  brief's summary tables, with a field-by-field comparison against the
  brief's own "important fields" list.
- **`data/sample/bts_on_time_2025_01_sample_5000rows.csv`.** The first
  5,000 data rows of the January 2025 BTS file, with its real header, so
  a reviewer can run later phases without downloading the full year.
- **`docs/DECISIONS.md`** updated: open decision 1 (data year) is now
  decided, with evidence, and a new "Blockers needing human action"
  section records the S4 lookup-table problem.

## Why each choice was made

- **One script per source, driven by a single entry point.** Matches
  hard rule 4 (one script, numbered/ordered steps) and keeps the logic
  for "is this already downloaded" in one place (`download()`), so
  every source behaves the same way under a retry.
- **Resumability by comparing size against the server, not just
  checking the file exists.** A file can exist but be a truncated
  partial download (this actually happened once during testing, see
  below), so existence alone is not a safe resume signal.
- **A dedicated opener that refuses to follow redirects
  (`NoRedirect`).** Explained in detail below, because it is the most
  important bug this phase found.
- **Per-station NOAA daily files are deliberately not downloaded yet.**
  The brief says to select stations in Phase 3, from the airport list
  loaded in this phase. Downloading all of NOAA's stations now would
  mean downloading data for thousands of stations never used.
- **S4 is reported as "blocked", not silently skipped or faked.** Hard
  rule 2 says no row is silently dropped; the equivalent here is that no
  source is silently skipped. The script says exactly what it tried,
  what happened, and what a human needs to do next.

## What went wrong and why (real debugging, not hypothetical)

Three real problems came up while building and running this phase, each
fixed and explained rather than hidden:

1. **A truncated download looked like a successful one.** The very
   first manual test of the BTS URL pattern, using `curl` with a 60
   second timeout, produced a 6.5 MB file against an expected 27 MB.
   `curl` printed its usual progress output and exited; nothing in that
   output said "this is incomplete" at a glance. Re-running without an
   artificially short timeout produced the full file, confirmed by
   comparing size against the server's `Content-Length` header. This is
   exactly why `download_sources.py`'s resume check compares size
   against the server rather than merely checking that a file exists.

2. **Python's `ssl` module could not verify any HTTPS certificate on
   this machine, while `curl` worked fine on the same URLs.** The error
   was `CERTIFICATE_VERIFY_FAILED: unable to get local issuer
   certificate`. `curl` uses the operating system's trust store; this
   particular Python installation does not pick that up automatically.
   Fixed by adding the `certifi` package and passing its CA bundle to
   `urllib.request` explicitly (`ssl.create_default_context(cafile=certifi.where())`),
   rather than disabling verification, which would be a real security
   regression for the sake of a convenience fix.

3. **The S4 lookup table "downloads" silently succeeded with the wrong
   content.** Once the certificate problem was fixed, requesting the S4
   lookup URLs returned HTTP 200 and wrote a file to disk, which looked
   like success in the summary table. Inspecting the file showed it was
   the BTS site's homepage HTML, not a CSV. `urllib`'s default behaviour
   is to follow a 3xx redirect transparently and report the status of
   the *final* page, not the original request, so the real `302 Object
   moved` response to `Homepage.asp` was invisible. Fixed two ways: a
   custom `NoRedirect` handler that turns any redirect back into a
   visible error, and a belt-and-suspenders content check that rejects
   any downloaded file whose first bytes look like an HTML document.
   This is the most important finding of the phase: it means the S4
   lookup tables are genuinely unavailable through this automated path,
   not merely blocked by a bug in this script, and a human needs to
   check whether a browser succeeds where this script's HTTP client did
   not (see `docs/DECISIONS.md`, item B1).

4. **A dropped connection mid-download crashed the whole script,
   losing track of files already downloaded.** While downloading the
   full year, the connection was reset by the server partway through
   month 3 (`ConnectionResetError`). That exception is not a subclass
   of `urllib.error.URLError`, so the original `except` clause did not
   catch it, and the script exited with an unhandled traceback, even
   though months 1 and 2 had already saved correctly to disk. Fixed by
   widening the caught exceptions to `OSError` (which covers a
   connection reset, a timeout, and a TLS-layer error, since all three
   are `OSError` subclasses in Python) and adding a bounded retry (4
   attempts, 5 second backoff) specifically for that category of error,
   while still treating an HTTP error status and the HTML-content check
   as immediate, non-retried failures, since retrying those would not
   help. Re-running after the fix completed the remaining 9 months with
   zero manual intervention, including surviving further transient
   errors automatically.

## How the pieces connect

`download_sources.py` reads `DATA_YEAR` from `.env` (resolved to 2025,
see `docs/DECISIONS.md`), builds the twelve BTS URLs from the verified
PREZIP pattern, and the fixed NOAA and OpenFlights URLs, and writes
everything under `data/raw/`, which stays gitignored. Phase 2's
`etl/extract.py` will read these same files into staging tables, using
the column lists this phase recorded in `docs/source_columns.md` to
decide the staging schema.

## Acceptance check run

Full run, all four sources, after every file had already been downloaded
once (demonstrates resumability: everything that exists and matches the
server's size is skipped, nothing is re-downloaded needlessly):

```
$ python data/download_sources.py --year 2025
...
status     size_bytes  sha256 (first 12 hex chars)  name
skipped      27108664  868387dcedae...  S1 2025-01
skipped      25302583  12dc8dbdb3c8...  S1 2025-02
skipped      30544825  9c80fbc2112c...  S1 2025-03
skipped      29369186  f3718431e988...  S1 2025-04
skipped      30830593  17c3419d7169...  S1 2025-05
skipped      31131411  087b75e4e059...  S1 2025-06
skipped      32208704  74309a3a734d...  S1 2025-07
skipped      30864245  405668b8a807...  S1 2025-08
skipped      28151630  adc722b1c149...  S1 2025-09
skipped      30723803  05d14d3fd67f...  S1 2025-10
skipped      28847755  6d5b68eea3eb...  S1 2025-11
skipped      30337431  a2af96d186bc...  S1 2025-12
skipped      11441526  437ee87f0343...  S2 ghcnd-stations.txt
skipped      36403986  95be02499a07...  S2 ghcnd-inventory.txt
skipped       1127225  9387cdb38df5...  S3 airports.dat
blocked             0  -               S4 L_UNIQUE_CARRIERS.csv
blocked             0  -               S4 L_AIRPORT_ID.csv
blocked             0  -               S4 L_CANCELLATION.csv
Totals: {'skipped': 15, 'blocked': 3}
$ echo $?
0
```

All 12 BTS monthly files for 2025 are present (392 MB total in
`data/raw/bts/`), confirmed one at a time against the server's
`Content-Length` as they were downloaded (`logs/download_20261117T060315Z.log`
has the per-file sizes and checksums from that run). S2 and S3 are
present and verified. S4 is blocked, as recorded in
`docs/DECISIONS.md`, item B1.

```
$ python -m pytest -q
...
3 passed in 0.14s
```

## Likely examiner questions

1. **Why does the resume check compare file size against the server
   instead of just checking the file exists?**
   Because a partial download (for example from a timeout mid-transfer)
   leaves a real file on disk that would otherwise be mistaken for a
   complete one on the next run. This was an actual bug hit while
   testing, not a hypothetical.

2. **Why is `certifi` an added dependency instead of just telling
   Python to skip certificate verification?**
   Skipping verification would defeat the purpose of HTTPS (no
   protection against a tampered or impersonated server) to solve what
   is actually a local configuration gap: this Python installation
   does not share the operating system's certificate trust store.
   `certifi` ships a current, maintained CA bundle as a normal Python
   package, so verification still happens, just using an explicit,
   known-good source of trusted certificates.

3. **What exactly does the `NoRedirect` handler do, and why not just
   check the final HTTP status code?**
   By default, `urllib` follows a redirect automatically and only the
   final response's status (here, 200 for the homepage) is visible to
   calling code; the original 302 is hidden. `NoRedirect` overrides the
   redirect handler to refuse the redirect, which makes `urllib` raise
   the real 302 as a visible error instead of quietly following it.

4. **The brief said not to hunt for mirrors if a download is blocked.
   Why does S4 try three different URL parameters, then?**
   Those three URLs are not mirrors of each other; they are the three
   different lookup tables needed (carriers, airport IDs, cancellation
   codes), all served by the same BTS mechanism. Trying all three is
   checking whether the real target works, not substituting an
   alternative source for one that does not.

5. **Why download NOAA's full station list and inventory now, but not
   any per-station weather data yet?**
   The station list and inventory are small reference files needed to
   decide, in Phase 3, which station is nearest to each airport. The
   actual daily weather readings are only needed for stations that get
   selected that way, and NOAA's per-station files for every station
   worldwide would be a large, mostly wasted download.

6. **How was the choice of 2025 as the data year actually verified,
   rather than assumed?**
   By requesting the real BTS PREZIP URL for December 2025 directly
   (`curl -I`) and confirming it returns HTTP 200 with a real
   `Content-Length` and a `Last-Modified` date in the past (March 2026),
   proving the file is a finished, published file rather than missing
   or a placeholder. 2026 was ruled out because it is the current,
   still-in-progress calendar year as of the check (2026-11-17).

7. **What happens to the raw zip files after this phase? Are they
   loaded as-is into MySQL?**
   No. They stay as zip files in `data/raw/bts/`, which is gitignored.
   Phase 2's `etl/extract.py` is what will unzip and load them into a
   staging table with every column as text, per hard rule 1. This phase
   only acquires and verifies the files.

8. **Why is `data/sample/` one BTS month's first 5,000 rows, and not a
   sample of every source?**
   The brief asks for this specifically so a reviewer can run the
   pipeline without downloading the full year of BTS data, which is the
   only source large enough to be a real burden (tens of megabytes per
   month, versus roughly a megabyte each for the OpenFlights and S4
   files, which are small enough to just re-download).

9. **Is the S4 blocker Claude's fault, or a real limitation?**
   Verified as a real server-side behaviour: every one of the three
   lookup URLs, requested with and without a prior session cookie,
   returns the same 302 redirect to the site's homepage. That is
   consistent with the old ASP-based lookup download mechanism having
   been retired. It has not been confirmed whether a real browser,
   with full JavaScript and cookie handling, succeeds where this
   script's HTTP client does not; that check needs a human.

10. **Why does the script retry a dropped connection but not an HTTP
    404 or the S4 redirect?**
    A dropped connection or timeout is transient: the same request
    often succeeds a few seconds later, which is exactly what happened
    when a connection reset mid-download during the real Phase 1 run
    (see finding 4 above). A 404 or a redirect to the wrong page is not
    transient. The server is answering normally; it is just answering
    with the wrong thing, and no number of retries changes that.
    Retrying those would waste time and make a real, permanent problem
    look like a slow, eventually-successful one.

11. **What would you do differently if this had to run unattended, for
    example as a monthly scheduled job?**
    Alert a human specifically when S4 stays blocked for more than one
    run, since that is the kind of failure that will not fix itself by
    retrying, and cap the total retry time per file so a persistently
    unreachable host cannot stall the whole run indefinitely.
