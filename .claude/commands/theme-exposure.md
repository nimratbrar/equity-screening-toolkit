---
description: Tag the global universe by theme using segments, geography, customers and analyst coverage
argument-hint: "[optional: edits to themes, or 'refresh']"
---
Build the data view that lets us test hypotheses against real companies. Notes: $ARGUMENTS

1. Open `research/themes.json`. Adjust the theme definitions to the approved hypotheses: segment name keywords,
   segment NAICS, exclusions for false positives, core GICS codes, a named-company include list, business
   description keywords, and anchor customers (to find second-order suppliers). Show me the changes in plain language.
2. Tell me a Duo push is coming, then run in my Terminal:
   `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run theme_exposure.py`
3. Read `research/data_notes/theme_exposure.md`. For each theme report: how many companies (by segment, by
   GICS or name, by description only), the clean "core group" medians with n, the by-country table, pure plays
   versus hidden minority segments, non-US names whose exposure is unverified, and second-order suppliers.
4. Audit before quoting: open two or three per-theme CSVs in `output/theme_exposure_*/` and check the matched
   segment names for false positives. Fix `themes.json` and re-run from cache (no new Duo push) if needed.
5. Say what the data shows that we did not expect (where non-US is cheaper or less covered, where capex signals
   a glut, where China share is a risk), and whether each hypothesis is supported, weakened or killed.
Post a BROADCAST and stop for my decision.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
