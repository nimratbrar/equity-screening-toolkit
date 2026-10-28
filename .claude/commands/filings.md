---
description: Pull segment, end-market, backlog and guidance evidence from the companies' own documents
argument-hint: "<company names>"
---
Get the evidence that databases do not have, from company documents, for: $ARGUMENTS

Launch one Sonnet agent per two or three companies, in parallel. Each agent:
- Uses only primary documents from the company's own investor-relations site (or the stock-exchange filing
  copy linked from it): latest annual or integrated report, latest full-year and quarterly results
  presentation, medium-term plan, published Q&A. Downloads into `research/company_docs/<company>/`, converts
  with `pdftotext -layout` into `research/text/`, and greps for the relevant pages instead of reading everything.
- Extracts for the last 3 fiscal years, each with document name and page [company filing: doc, p.N], in the
  reporting currency: sales and profit by segment and by END MARKET (the share tied to our theme); segment
  margins; orders and backlog (and recurring versus one-off); geographic split including China; capex and
  capacity; medium-term targets; share count and any split; and anything that CONTRADICTS the thesis.
- Writes `research/notes/company_<name>.md` (max 500 words with a small table and a final "does the link
  hold?" paragraph labeled [inference]), lists what could not be found, and posts a BROADCAST.
Do not use third-party sites for numbers. Then summarize for me, per company: theme exposure, margin, backlog,
the main caveat, and what is still not disclosed.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
