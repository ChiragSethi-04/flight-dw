# AI use log

This log records every use of Claude Code on this project: what it
generated, and what the human reviewed or changed. It feeds the AI-use
acknowledgement in the final report. By explicit instruction from the
human, commits in this repository are not tagged with an AI co-author
trailer; this log is the record of AI involvement instead.

## 2026-11-17, Phase 0: Setup

**What Claude generated:**
- Repository scaffold: `data/`, `etl/`, `sql/`, `docs/`, `tests/`, `logs/`, `exports/` directories matching section 7 of the brief, plus the extra `tests/` and `logs/` directories the project's own CLAUDE.md asks for.
- `.gitignore`, `.env.example`, `requirements.txt`, `docker-compose.yml` (MySQL 8 with `local_infile=1`), `Makefile`.
- `etl/db.py` (shared SQLAlchemy/PyMySQL connection helper) and `run_all.py` (step-status orchestrator skeleton with a `--check-db` acceptance check).
- `docs/DECISIONS.md`, `docs/AI_USE_LOG.md` (this file), `docs/walkthrough/phase0.md`, `README.md`.
- Read and summarised `docs/brief.pdf`, the project's `CLAUDE.md`, and `docs/BUILD_PLAN.md` before writing any code, per the brief's own kickoff prompt, and surfaced the gaps noted in `docs/walkthrough/phase0.md`.

**What the human reviewed or changed:**
- Chose to scope this session to the Phase 0 scaffold only, deferring the real data downloads and full ETL build to later phases (see `docs/DECISIONS.md`, P1).
- Decided commits carry no AI co-author trailer; AI involvement is disclosed here instead (P2).
- Chose a public GitHub repository (P3).
- Ran the Phase 0 acceptance check (`docker compose up -d`, then `python run_all.py --check-db`) and confirmed the real output before accepting the phase as done.
- During that run, found a real conflict (a pre-existing local MySQL 8.4 service already on port 3306) and a real auth-plugin incompatibility (`caching_sha2_password` over plain TCP). Both are fixed in `docker-compose.yml` and explained in `docs/walkthrough/phase0.md` rather than worked around silently.

**Not yet decided (see docs/DECISIONS.md, open decisions 1-7):** data year,
destination weather dimension, wind coverage threshold, midnight handling,
station distance threshold, SCD2 evidence approach, dashboard tool. These
require team agreement, professor confirmation, or Phase 2 profiling
evidence, so they are left open rather than guessed.
