# Research team protocol (read this first)

This folder is the shared workspace for the research agents. Project-specific write-ups, notes and the board log
are git-ignored: they can contain licensed figures.

## Roles
- **equity-research-analyst**: owns the hypotheses and screens. Reads notes and the board, not raw reports.
- **extractors**: read report or filing text in `research/text/` and write short notes to `research/notes/`
  with page references.
- **scenario-analyst** (quant): regressions, scenario tables and Monte Carlo runs (`methodology/`).
- **red-team-reviewer**: attacks one lens at a time (statistics, geopolitics, business logic) and re-runs numbers.
- **reconciler**: merges challenge results into one revised table and states which argument it accepted.
- **translator**: turns audited results into a plain-English decision document with pre-committed scorecards.

## Shared board (everyone reads and writes)
`research/board.md` (append-only), through the helper so posts never collide:
- Read: `python3 research/board.py read` (add `--last 10`, `--type CHALLENGE`, `--from analyst`)
- Post: `python3 research/board.py post --from <your-name> --type <TYPE> --to <ALL or name> "text"`
- Types: BROADCAST, QUESTION, CHALLENGE, REPLY, DECISION, STATUS.
- Under 150 words per post, one idea per post. Refer to hypotheses by ID (H1, H2) and posts by number (#7).
- Read the board before you start and before you finish. If a post is addressed to you, REPLY to it.

## Rules for everyone
- Never invent data. Label every claim [WRDS data], [company filing: doc, p.N], [report: file, p.N],
  [source: name, date, URL] or [inference].
- Licensed reports and database extracts stay local: paraphrase, quote at most one short phrase per report.
- Do not connect to WRDS (it may send a Duo push to the user) unless the orchestrator says so.
  No web search for company financials.
- No buy or sell recommendations. Never use em dashes. Be concise and lead with the result.
