---
name: wrds
description: Access WRDS (Wharton Research Data Services) through your institution's WRDS account to pull financial data and screen companies. Use whenever a task involves WRDS, Compustat, CRSP, I/B/E/S, PitchBook, the WRDS Financial Ratios Suite, Capital IQ, pulling company fundamentals / prices / valuations / analyst estimates / private-company deals, or building, running or automating a company screen or ranked shortlist (e.g. a stock pitch or thesis-driven screen).
---

# WRDS: pull data and screen companies

Scripts live in `.claude/skills/wrds/scripts/` (project-level skill; copy the folder to `~/.claude/skills/wrds/` to use it from any project):
- `wrds_client.py`: the `WRDS` session class (cached, lazily connected) with pull helpers.
- `screen.py`: config-driven **global** screen (Compustat North America + Compustat Global, all money
  converted to USD) that writes ranked Excel, CSV and meta JSON.

References (read when needed):
- `references/datasets.md`: libraries, tables, key columns, identifiers and joins.
- `references/recipes.md`: SQL recipes for CCM merge, CRSP v2, I/B/E/S, PitchBook, segments, global.
- `references/screen_config.md`: full screen config spec and metric list.
- `templates/*.json`: starting configs.

## Rules (non-negotiable)

1. **Credentials.** Never ask for the WRDS password in chat, never echo, log or commit it. Two sources only:
   - **Local machine:** `~/.pgpass`. If missing, have the user run this in their own Terminal (launch it with
     `run_in_terminal` so they type into it themselves):
     `<python> -c "import wrds; wrds.Connection().create_pgpass_file()"`.
   - **Claude Code cloud environment:** `WRDS_USERNAME` and `WRDS_PASSWORD` set by the user in the
     environment's **Environment variables** (claude.ai/code > environment settings). Never write them to a
     file, and never print `env` or the variable's value. If they're missing, tell the user where to add them.
   `WRDS()` picks the source automatically and fails with a clear message (no interactive prompt) if neither exists.
2. **Duo.** Every new connection sends a Duo push to the user's phone. Tell the user *before* running anything
   that connects. Use **one `WRDS` session per run** (one push). Cached queries don't connect at all.
   Run connecting scripts with `run_in_terminal` (the user can see the prompt), then read the output.
3. **No hard-coded dataset dates.** WRDS tables update on their own schedules and some hold placeholder
   future dates. Always anchor on `w.latest_date(table)` (max date <= today) or `w.freshness()`, and cap every
   date filter at today. Don't write "dataset X ends in <date>" into code or docs; check it live.
4. **Licensing.** Use WRDS data only as your institution's licence allows (usually academic use only). Keep extracts local (`data/`, `output/`, git-ignored). Don't upload raw
   extracts to outside services. In chat, report aggregates, funnels and top-N names, not bulk rows.
5. **Queries.** Parameterized SQL only (`%(name)s`; write `%%` for a literal `%`). Add `LIMIT` when exploring
   an unfamiliar table. Big tables (`comp.secd`, `crsp.dsf_v2`, `ibes.det_*`) always need a date and/or ID filter.

## Running in a Claude Code cloud session

- Detect it with `CLAUDE_CODE_REMOTE=true`. First run `uv run python .claude/skills/wrds/scripts/wrds_client.py --network-only`.
  If it reports WRDS unreachable, the environment's egress (HTTP/HTTPS proxy) blocks PostgreSQL: stop and tell
  the user to run WRDS steps on their local machine. Don't try to work around the proxy.
- Multi-factor approval (Duo) still applies: tell the user to watch their phone before connecting.
- Dependencies: the environment's setup script (`cloud_setup.sh`) runs `uv sync --frozen`; run scripts with
  `uv run python ...`. If imports fail, run `uv sync --frozen` again.
- The VM is temporary and `data/`, `output/` are git-ignored: never commit or push extracts. Summarize results in
  the session and tell the user which files exist; licensed data stays out of git.

## Python environment

Managed with **uv** (never `python -m venv` or bare `pip`). Python 3.12; versions are pinned in the project's
`pyproject.toml` + `uv.lock` at the repository root, so local and cloud environments get the same packages.
- Local: the environment is `~/.venvs/equity-screening-toolkit`, kept outside cloud-synced folders on purpose (sync clients
  evict files to cloud-only, which stalls a venv). Build or refresh it with `./setup.sh`, i.e.
  `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv sync`.
- Run scripts with `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run <script.py> ...` from the project
  folder, or directly with `~/.venvs/equity-screening-toolkit/bin/python <script.py> ...` (`<python>` below).
- Add a package with `uv add <name>` (updates pyproject.toml and uv.lock), then re-run `./setup.sh`.
- Keep `wrds>=3.5`: the client relies on its connection arguments. If uv isn't installed, see https://docs.astral.sh/uv/ (for example `brew install uv` on macOS).

## Pulling data

```python
import sys; sys.path.insert(0, ".claude/skills/wrds/scripts")   # run from the repository root
from wrds_client import WRDS

with WRDS() as w:                          # cache: ~/.cache/wrds (WRDS_CACHE_DIR), TTL 24h (WRDS_CACHE_TTL_HOURS)
    print(w.freshness())                   # latest available date per key dataset, live
    co   = w.company_info()                # comp.company (region="intl" for g_company): GICS, country, busdesc
    fa   = w.fundamentals_annual(start_year=2018)                 # comp.funda (region="na")
    ga   = w.fundamentals_annual(start_year=2018, region="intl")  # g_funda, rest of world
    fx   = w.fx_to_usd()                   # USD per unit of each currency, latest g_exrt_dly date
    fq   = w.fundamentals_quarterly(start_date="2023-01-01", gvkeys=co.gvkey[:50])
    mkt  = w.latest_market_data()          # comp.secd latest price + market cap (region="intl" for g_secd)
    rat  = w.fin_ratios(columns=["bm", "roe", "evm", "ptb"])   # WRDS Financial Ratios Suite, latest per firm
    lnk  = w.ccm_links()                   # gvkey <-> CRSP permno
    crsp = w.crsp_monthly("2020-01-01", permnos=lnk.permno.unique()[:100])
    est  = w.ibes_consensus(fpi="1")       # EPS consensus, current FY
    pb   = w.pitchbook_companies(keywords=["vertical farming"], countries=["United States"])
    df   = w.sql("select ... where x = %(v)s", {"v": 1})   # anything else
```

Exploring an unknown table: `w.tables("lib")`, `w.columns("lib", "table", contains="rev")`,
`w.describe("lib", "table")`, `w.sample("lib", "table", n=5)`. See `references/datasets.md` first.

## Screening

1. Turn the user's thesis into a JSON config (copy a `templates/` file). `region` is `global` by default
   (`na` or `intl` to narrow); restrict countries with `universe.countries` (HQ, ISO-3). Most thesis logic fits in
   `universe` (country/sector/GICS/SIC/NAICS/keywords/size), `filters` (metric thresholds), `custom_metrics`
   (pandas expressions over Compustat items) and `scoring` (weighted percentile ranks, optionally within sector).
2. Validate without connecting: `<python> .claude/skills/wrds/scripts/screen.py --config cfg.json --dry-run`
3. Tell the user to expect a Duo push, then run it in their Terminal with `run_in_terminal`:
   `<python> .claude/skills/wrds/scripts/screen.py --config cfg.json`
   (`--as-of YYYY-MM-DD` for a historical screen, `--refresh` to bypass the cache).
4. Read the printed funnel and top names. If the funnel collapses at one step, loosen that filter and re-run
   (cached, so no new Duo push).
5. Outputs in `output/`: `<name>_<stamp>.xlsx` (Ranked, All passing, Funnel, Metric definitions, Notes incl.
   data vintage), `.csv` (every column, for downstream steps), `.meta.json` (funnel, vintage, config).

Pipeline use: `from screen import run_screen; res = run_screen(cfg, session=w)` returns
`ranked` (DataFrame), `funnel`, `paths`. Share one `WRDS` session across steps to keep to one Duo push.

## Gotchas

- Compustat money is in **millions** of the reporting currency `curcd`; `emp` is in **thousands**. The screen
  converts money to USD at the latest `g_exrt_dly` rate (one rate for all years, so growth is local-currency);
  in your own pulls, convert with `w.fx_to_usd()` before comparing firms across currencies.
- Global prices: `g_secd.prccd` is per `qunit` shares; the helpers divide by `qunit`. Global exchange codes
  differ from US ones; the screen excludes non-traded/OTC codes (0-4, 13, 19) by default.
- The WRDS Financial Ratios Suite and I/B/E/S `statsum_epsus` cover US firms; for non-US names those
  columns are blank (I/B/E/S international is in `statsum_epsint`).
- `fic` = country of incorporation, `loc` = HQ country (the screen's `countries` filter uses `loc`). Financials (GICS 40) distort EBITDA/EV
  metrics, so exclude them unless the thesis is about them.
- CRSP: use the v2 tables (`msf_v2`, `dsf_v2`); the legacy `msf`/`dsf` stopped updating. CRSP lags Compustat,
  so use `comp.secd` for current prices and CRSP for return history. Check `w.freshness()`.
- I/B/E/S tickers are not exchange tickers. Link on 8-char CUSIP (`ibes.cusip == comp.cusip[:8]`) or via
  `wrdsapps_link_crsp_ibes`.
- `fyear` can repeat after a fiscal-year-end change. The helpers keep the latest `datadate`.
- For true point-in-time backtests, use `comp_pit` / `comp_snapshot` (restated vs as-first-reported data);
  `--as-of` only approximates by lagging fundamentals `report_lag_days`.
