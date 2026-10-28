# Equity Screening Toolkit: guide for Claude Code

## What this is
A thematic equity screening and analysis toolkit on WRDS (Compustat NA and Global, I/B/E/S, optional segments
and CRSP), with optional file connectors for Capital IQ exports and user-entered industry figures. The method is
in `docs/METHODOLOGY.md`.

## Environment
- Python 3.12 managed with uv. Build with `./setup.sh` (environment in `~/.venvs/equity-screening-toolkit`).
- Run scripts with `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run <script.py>`.

## Credentials
- Never ask for a password in chat and never write one to a file. The user creates `~/.pgpass` in their own
  terminal (`store_password.py`) or sets `WRDS_USERNAME` / `WRDS_PASSWORD` in their environment.
- A new WRDS connection may trigger a multi-factor prompt on the user's phone: say so before connecting, and use
  one session per run.

## Data rules
- Licensed data stays local: `data/`, `output/`, `inputs/` and research notes are git-ignored. Never commit,
  upload or paste bulk rows; report aggregates and top-N names.
- Parameterized SQL only; add `LIMIT` when exploring; never hard-code dataset dates.
- Label every figure [WRDS data], [company filing], [report], [source] or [inference]. No buy or sell advice.
- Never use em dashes in written output.
