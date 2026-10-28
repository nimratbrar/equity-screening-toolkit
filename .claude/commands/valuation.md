---
description: Re-rank the ideas and write worked valuation illustrations plus a completeness audit
argument-hint: "[optional: companies to include]"
---
Integrate everything and produce the decision-ready view. Scope: $ARGUMENTS

Use Opus. Read the board, `research/hypotheses_final.md`, all `research/notes/company_*.md`, and the latest
deep-dive outputs (report.md and the "Valuation inputs" sheet).
1. Re-rank the ideas on the evidence now in hand, and say plainly if the lead should change or a peer is a better vehicle.
2. For the top three, write a WORKED valuation illustration: inputs with source, the method (re-rating to a
   stated peer forward EV/EBITDA, or sum of the parts by segment), the multiple chosen and why, implied value
   per share, a low / base / high range, and the difference from the current price. Show the arithmetic and
   every assumption. Label it an illustration of method for the team to refine, not a recommendation and not a final price target.
3. Write-up skeleton per company: thesis in one sentence, theme link with segment numbers, the three biggest risks, what would disprove it.
4. Completeness audit: every input each write-up needs (theme exposure, segment margin, backlog, growth forecast,
   valuation inputs, peer multiples, liquidity, sustainability evidence, risks) marked HAVE, PARTIAL or MISSING,
   and for each gap whether filling it would change the conclusion (high / medium / low) and where it could come from.
5. Rewrite `research/hypotheses_final.md`, update the log, post DECISION posts, and give me the decisions you need.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
