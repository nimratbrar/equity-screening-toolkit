---
description: Connect this machine to the Wharton database (WRDS) and check what data my account can read
---
Set up and verify my WRDS access. Do these in order and stop at the first thing that needs me.
1. Check that uv is installed (`uv --version`); if not, point me to https://docs.astral.sh/uv/ (for example `brew install uv` on macOS). Then run `./setup.sh`
   to build the Python environment (`~/.venvs/equity-screening-toolkit`).
2. Check whether `~/.pgpass` has a WRDS line. If not, open my Terminal with `run_in_terminal` and run
   `~/.venvs/equity-screening-toolkit/bin/python store_password.py` so I can type my own WRDS username and password
   (hidden). Never ask for my password in chat and never write it to any file.
3. Warn me that a Duo push is coming, then run `~/.venvs/equity-screening-toolkit/bin/python check_access.py` in my Terminal.
4. Read `output/access_report.md` and tell me, in a short table, which datasets are usable (Compustat North
   America and Global, CRSP, I/B/E/S US and international, segments, PitchBook) and how current each is.
   Say plainly which libraries are samples only.
5. Finish with the next command to run: `/research-kickoff`.

---
Rules for every step: load the `wrds` skill and follow it exactly (credentials, Duo, licensing, parameterized SQL,
no hard-coded dataset dates). Read `research/TEAM.md` and the board (`python3 research/board.py read --last 15`)
before you start, and post your result to the board when you finish. Never invent data: label every claim
[WRDS data], [company filing], [report], or [inference]. No buy or sell recommendation. Lead with the result,
be concise, and never use em dashes. Tell me before any WRDS connection (it sends a Duo push to my phone),
use one session per run, and use the cache when you can.
