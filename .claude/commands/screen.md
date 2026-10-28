---
description: Turn an approved hypothesis into a screen config, show it in plain language, then run it
argument-hint: "<hypothesis ID or description>"
---
Build and run a screen for: $ARGUMENTS

1. Read `.claude/skills/wrds/references/screen_config.md` and copy a template from `pipelines/` or
   `.claude/skills/wrds/templates/`. Write `pipelines/<name>.json`.
2. Before running, show me in plain language: universe filters (active, market cap >= $1B, countries, GICS codes
   or keywords), hypothesis filters with a one-line reason each, ranking metrics with direction and weights,
   known blind spots, and the expected result count. Keep thresholds loose on the first pass.
3. Validate without connecting: `~/.venvs/equity-screening-toolkit/bin/python .claude/skills/wrds/scripts/screen.py --config pipelines/<name>.json --dry-run`
4. Tell me a Duo push is coming, then run in my Terminal:
   `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config pipelines/<name>.json`
5. Report: the funnel (companies left after each filter); the top 15 as a table (company, ticker or ISIN,
   country, sub-industry, market cap, revenue growth, margin, leverage, EV/EBITDA versus peers, 12-month price
   change, analysts); three to five names worth a closer look with one line on why and one on the main risk;
   anything surprising; data caveats; output paths. Aggregates and top-N only, no bulk rows.
6. Stop and offer: tighten or loosen (say which filter and why), `/deep-dive` on selected names, drop the
   hypothesis, or generate new ones. Log the result in `research/hypothesis_log.md`.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
