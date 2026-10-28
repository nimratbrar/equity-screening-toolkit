---
description: Generate 4 to 6 investment hypotheses from the report notes and data, for me to approve
argument-hint: "[optional focus, e.g. a sub-theme or region]"
---
Generate investment hypotheses. Focus (optional): $ARGUMENTS

Read the notes in `research/notes/`, `research/data_notes/` if present, the board, and
`research/hypothesis_log.md` (do not repeat rejected ideas). Write 4 to 6 hypotheses covering at least three
sub-themes, in `research/hypotheses_draft.md`, each under 180 words with:
- ID and a one-line statement (example: "Japanese chip materials makers earn higher returns than US peers at a lower multiple").
- Sub-theme and the structural driver.
- Why it might not be priced in.
- Evidence with source and page, or "my own reasoning".
- What would disprove it.
- Which observable metrics would identify the companies that benefit (use metrics the screener has:
  `~/.venvs/equity-screening-toolkit/bin/python .claude/skills/wrds/scripts/screen.py --list-metrics`).
- Screenable today: yes / partly / no. Confidence: high / medium / low.
Post each hypothesis to the board as its own BROADCAST. Do not connect to WRDS and do not run anything.
Stop and let me approve, edit or reject each one. Suggest running `/challenge` next.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
