# Phase 0 walkthrough: setup

## What was built

This phase does not touch any flight or weather data. It sets up the
skeleton that every later phase builds on, so the project has one place
for configuration, one place for credentials, and one place for the
database to run.

- **Repository layout.** Folders for `data/` (raw downloads and small
  samples), `etl/` (the Python pipeline, empty for now except a shared
  database connection helper), `sql/` (the numbered SQL scripts, empty
  for now), `docs/` (everything a reviewer or examiner needs to read),
  `tests/`, `logs/` and `exports/`. This matches section 7 of the brief.
- **`docker-compose.yml`.** Defines a single MySQL 8 container with a
  named volume, so the database survives a container restart, and with
  `local_infile=1` turned on. That flag matters later: Phase 4 bulk-loads
  millions of rows with `LOAD DATA LOCAL INFILE` instead of inserting row
  by row, because row-by-row inserts would take hours on this volume of
  data. The host port is mapped to 3307, not 3306, and the server is set
  to `mysql_native_password` instead of MySQL 8's default
  `caching_sha2_password`. Both came from running the acceptance check
  for real, not from guessing ahead of time: see "What went wrong and
  why" below.
- **`.env.example` and `.env`.** Database credentials live in `.env`,
  which is listed in `.gitignore` so it never reaches GitHub. `.env.example`
  is the template that shows what variables are needed without exposing
  real values.
- **`etl/db.py`.** One function, `get_engine()`, builds the SQLAlchemy
  connection from the `.env` variables. Every later script imports this
  instead of writing its own connection string, so there is exactly one
  place to change if the connection details ever change.
- **`run_all.py`.** The orchestrator the brief asks for (hard rule 4: one
  script, numbered steps). Right now every step shows as `pending`
  because no phase has filled one in yet. `python run_all.py --check-db`
  is the Phase 0 acceptance check: it opens a connection and runs
  `SELECT 1`.
- **`docs/DECISIONS.md` and `docs/AI_USE_LOG.md`.** Started empty-but-structured
  so later phases append to them rather than inventing a new format.

## Why each choice was made

- **MySQL over another database.** Locked by the brief itself (section
  11 lists MySQL with MySQL Workbench as the proposed tool).
- **A named Docker volume, not a bind mount.** Keeps the data directory
  out of the git-tracked folder entirely, which is simpler than relying
  on `.gitignore` to catch it.
- **`local_infile=1` set now, not later.** Easy to forget, and the brief
  explicitly calls it out as a requirement for bulk loading in Phase 4.
  Setting it in Phase 0 means every later phase can assume it is there.
- **A step-status skeleton instead of a bigger program.** The brief's
  own build plan asks for a skeleton in Phase 0 and the real steps in
  Phases 2 through 5. Writing more now would mean guessing at a design
  that Phase 3's dimensional model has not been reviewed yet.

## How the pieces connect

`docker-compose.yml` starts MySQL. `.env` tells both Docker Compose and
`etl/db.py` how to reach it with the same credentials. `run_all.py`
imports `etl/db.py` and will, phase by phase, import and call the real
`extract`, `clean`, `load_dims`, `load_facts` and `audit` modules in the
order the brief's section 6 specifies: dimensions before facts, weather
fact before flight fact.

## What went wrong and why (real debugging, not hypothetical)

Running the acceptance check surfaced two real problems, fixed in order:

1. **`Access denied for user 'flight_dw_user'@'localhost'`, from PyMySQL
   and from the `mysql` CLI, even though the password was correct.**
   `docker exec` into the container and connecting from inside it worked
   fine with the same credentials, which pointed at a connection-routing
   problem rather than a credentials problem. `lsof -iTCP:3306` showed a
   second, pre-existing MySQL 8.4 server (installed via Homebrew, running
   since before this project started) already bound to
   `127.0.0.1:3306` on the host. Every host-side client was reaching that
   other server, not the Docker container, and failing because that
   server has no `flight_dw_user` account. Fix: remap the container's
   host port to 3307 in `docker-compose.yml` and `.env`, leaving the
   pre-existing local server untouched.
2. **After fixing the port, the same access-denied error persisted at
   first.** MySQL 8's default authentication plugin is
   `caching_sha2_password`, which needs either an encrypted connection or
   an RSA key exchange to send a password over plain TCP, and the
   PyMySQL/mysql-client combination in use here did not complete that
   exchange. Fix: set `--authentication_policy=mysql_native_password` in
   `docker-compose.yml`, which is a standard, documented trade-off for
   local development and is noted here so no one mistakes it for the
   production-grade setting.

## Acceptance check run

```
$ docker compose up -d
$ python run_all.py --check-db
MySQL connection OK, SELECT 1 returned: 1
$ python -m pytest -q
...                                                                      [100%]
3 passed in 0.14s
```

## Likely examiner questions

1. **Why MySQL and not PostgreSQL or SQL Server?**
   The brief locks MySQL as the warehouse database, with MySQL Workbench
   as the proposed modelling tool (section 11). It is also free, widely
   taught, and has a mature bulk-load path (`LOAD DATA LOCAL INFILE`)
   needed for 6 to 7 million rows.

2. **Why Docker instead of installing MySQL directly on each laptop?**
   It makes the setup identical for every team member and for a
   reviewer running a clean clone, and it is easy to tear down and
   rebuild if the schema needs to change during development.

3. **What is `local_infile` and why does it matter this early?**
   It is a MySQL server flag that allows the client to bulk-load a local
   CSV file directly into a table with `LOAD DATA LOCAL INFILE`, which is
   far faster than inserting rows one at a time. It has to be enabled on
   the server, so it is set in `docker-compose.yml` from the start rather
   than discovered as a blocker during Phase 4.

4. **Why is there a `.env.example` file as well as a `.env` file?**
   `.env` holds real credentials and is gitignored, so it never reaches
   GitHub. `.env.example` is the checked-in template that tells a new
   team member or reviewer exactly which variables to set, without
   exposing any actual password.

5. **Why does `run_all.py` not do anything yet?**
   Hard rule 4 in the project's CLAUDE.md requires one script that
   executes numbered steps, so that one `python run_all.py` run can
   reproduce the whole warehouse. The steps are added as each phase that
   builds them is completed and reviewed; filling them in now would mean
   guessing at a schema that has not been designed yet (that is Phase 3).

6. **What does the Phase 0 acceptance check actually prove?**
   That the database container starts, exposes port 3306, accepts the
   credentials from `.env`, and executes a basic SQL statement end to
   end through SQLAlchemy and PyMySQL. It does not prove anything about
   the schema yet, because there is no schema yet.

7. **Why is `data/raw/` gitignored but `data/sample/` is not?**
   The brief expects roughly 6 to 7 million rows of flight data plus
   weather data, which would be impractical and unnecessary to store in
   Git. `data/sample/` holds a small, committed slice so a reviewer can
   run the pipeline without downloading the full year.

8. **What are the open decisions, and why are they not resolved yet?**
   Seven items listed in CLAUDE.md and recorded in `docs/DECISIONS.md`,
   for example which calendar year to use and the airport-to-station
   distance threshold. Several of them explicitly depend on profiling
   evidence that does not exist until Phase 2 runs, and one depends on
   the professor confirming the approach. Deciding them now would mean
   guessing, which hard rule 7 forbids.

9. **Why is there no AI co-author on the git commits?**
   That was an explicit choice by the human running this session. AI
   involvement is disclosed instead in `docs/AI_USE_LOG.md`, which this
   project's own report process feeds into, rather than through a git
   commit trailer.

10. **Why does `docker-compose.yml` map to port 3307 instead of the
    standard MySQL port 3306?**
    Because a pre-existing, unrelated MySQL server was already running
    on `127.0.0.1:3306` on the development machine (found with
    `lsof -iTCP:3306` while debugging the first acceptance check run).
    Every client connecting to `127.0.0.1:3306` was silently reaching
    that other server, not the container, and failing because it has no
    `flight_dw_user` account. Remapping to 3307 avoids touching that
    unrelated server. `README.md` documents how to pick a different
    port if 3307 is also taken.

11. **Why `mysql_native_password` instead of MySQL 8's default
    `caching_sha2_password`?**
    `caching_sha2_password` needs a secure channel (TLS, or a Unix
    socket) to do full authentication; over a plain TCP connection
    without TLS, the client and server need to complete an extra RSA
    key exchange, which the Python client stack in use here was not
    completing. Switching the server to `mysql_native_password`, which
    does not have that requirement, is a known, accepted trade-off for
    local development. It would not be the right choice for a
    production deployment handling real credentials over an untrusted
    network.
