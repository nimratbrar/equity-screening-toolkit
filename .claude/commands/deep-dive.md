---
description: Run the full WRDS analysis on named companies and their peers (one Duo push)
argument-hint: "<company names, tickers or ISINs>"
---
Deep-dive these companies: $ARGUMENTS

1. Resolve each name to a ticker (US) or ISIN (non-US) from the latest cached screen CSV in `output/`; ask me
   only if a name is ambiguous. Add 3 to 6 true peers per company so multiples come from one source.
2. Write `pipelines/deepdive_<topic>.json` using watchlist mode (`"analysis": {"names": [...]}`; see
   `pipelines/watchlist_deepdive.json`). Several configs can share one connection:
   `UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config a.json b.json`
3. Tell me a Duo push is coming and run it in my Terminal.
4. From `report.md` and `analysis.xlsx` (sheets Summary, Valuation inputs, Annual history, Price performance),
   give me one table: trailing and forward EV/EBITDA, forward P/E, analysts, expected sales growth, return on
   capital (and its 10-year path), leverage, 3-month average daily value traded, 12-month return.
5. Flag data problems instead of hiding them: stale net debt, share splits that break forward P/E, estimates in
   billions for JPY or KRW, a peer group that is the wrong industry, blank fields.
6. Say what the numbers do to the hypothesis, post a BROADCAST, and suggest `/filings` for what only company
   documents can answer (segment and end-market shares, backlog, contract terms).

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
