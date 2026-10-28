---
description: Have three reviewer agents attack the current hypotheses, then revise them
argument-hint: "[optional: hypothesis IDs to challenge]"
---
Stress-test the hypotheses in `research/hypotheses_draft.md` (or `research/hypotheses_final.md`). Scope: $ARGUMENTS

Launch three Sonnet agents in parallel. Each reads `research/TEAM.md`, the board and the hypotheses (and may
consult `research/notes/` and `research/data_notes/`, never the raw reports), then posts ONE `CHALLENGE` per
hypothesis to the board, under 110 words, without repeating another reviewer's point:
1. **challenger-pm**, a skeptical long-only portfolio manager: is it already consensus or a cyclical peak
   dressed as structural? Who captures the economics? Bear case over 12 to 24 months? A sharper, less crowded version?
2. **challenger-theme**, a thematic-investing reviewer: is the link from theme to financial performance causal and
   provable by business line? Sustainability or governance red flags? Is it differentiated from the obvious consensus names?
3. **challenger-quant**, a screening specialist who reads `.claude/skills/wrds/references/`: can it be screened
   with this tool and data? Which GICS codes or keywords define the universe, and what false positives? If data
   was already pulled, audit it: are quoted medians computed on clean groups with enough companies?
Then, as the lead analyst (use Opus), read all challenges, decide keep / sharpen / merge / drop for each
hypothesis, say which argument you accepted where reviewers disagree, write `research/hypotheses_final.md`,
update the log, and post one DECISION per hypothesis. Show me a compact table and the decisions you need from me.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
