# Equity Screening Toolkit

A thematic equity research toolkit: a global screen on WRDS, company deep dives with peer sets, scenario
tables, returns and multiple regressions, and a Monte Carlo valuation engine, driven by a set of Claude Code
agents that extract, compute, challenge and translate. It ships the **code and the method only**. You bring
your own licensed data.

> **DISCLAIMER.** This project is for research and educational use only and is not investment, legal or tax
> advice. It is provided "as is" without warranty of any kind (see LICENSE). It contains no data from WRDS,
> S&P Global (Compustat, Capital IQ), LSEG (I/B/E/S), CRSP or IBISWorld; example numbers are fictitious
> placeholders. To use it you need your own valid subscriptions, and you are solely responsible for complying
> with your provider and institutional agreements, including limits on commercial use and redistribution.
> The authors are not affiliated with, sponsored by or endorsed by any of these providers or by any university.
> All product names and trademarks belong to their respective owners and are used only to identify compatible
> data sources. Full text: [DISCLAIMER.md](DISCLAIMER.md).

## Who it is for

Students, researchers and analysts who already have WRDS access through their institution and want a
reproducible, auditable workflow from "here is a theme" to "here are a few cases, with scenario-weighted value
ranges, the statistics behind them and the audits they survived".

## Data sources and access

| Source | Status | Used for |
|---|---|---|
| WRDS: Compustat North America and Compustat Global | **Required** | Universe, fundamentals, prices, FX |
| WRDS: I/B/E/S (US and international) | **Required** for estimates | Consensus FY1 and FY2, analyst counts |
| WRDS: Compustat segments | Optional (recommended) | Theme exposure by business line, customers, geography |
| WRDS: CRSP, Financial Ratios Suite | Optional | Return history, US ratios |
| Capital IQ screen export (Excel or CSV you download) | Optional, **off by default** | Extra fields merged by ISIN or ticker (`connectors/`) |
| Industry figures you type from a report you license (for example IBISWorld) | Optional, **off by default** | Industry-level context merged by NAICS, GICS or SIC (`connectors/`) |
| Company filings and public sources | Manual | Segment shares, backlog, guidance, events |

You bring your own licensed access. The pipeline runs fully with WRDS alone; the connectors only read local
files you create yourself and never call or scrape any website. Templates contain column headers only.

## Install

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/nimratbrar/equity-screening-toolkit.git && cd equity-screening-toolkit
./setup.sh      # builds ~/.venvs/equity-screening-toolkit with the versions pinned in uv.lock
```

Keep the environment and the WRDS cache (`~/.cache/wrds`) outside cloud-synced folders.

## Authentication

WRDS credentials are read in this order, by the standard `wrds` package connection:

1. `~/.pgpass` (recommended). Create it yourself, in your own terminal:
   `~/.venvs/equity-screening-toolkit/bin/python store_password.py` (hidden password prompt, file mode 600),
   or the `wrds` package's own `create_pgpass_file()`.
2. Environment variables `WRDS_USERNAME` and `WRDS_PASSWORD` (see `.env.example`; keep `.env` out of git).

Your institution may require multi-factor approval (for example a Duo push) on each new connection. One
pipeline run uses one connection, and cached queries do not connect at all. Never paste a password into a chat
or an agent prompt.

Check what your account can read:

```bash
~/.venvs/equity-screening-toolkit/bin/python check_access.py      # writes output/access_report.md (git-ignored)
```

## Quick start

**1. Run a screen** (global universe, filters and weighted scores from a JSON config):

```bash
UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config pipelines/quality_growth.json
```

Outputs go to `output/<name>_<timestamp>/`: `report.md`, `analysis.xlsx`, the ranked screen, per-company JSON
dossiers and `run.json`. Edit or copy a config to change the thesis; see
`.claude/skills/wrds/references/screen_config.md`. Validate a config without connecting:
`UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run .claude/skills/wrds/scripts/screen.py --config <file> --dry-run`.

**2. Run a deep dive with a config** (watchlist mode: exact names plus peers on one basis):

```bash
UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config pipelines/watchlist_deepdive.json
```

To merge a Capital IQ export or your own industry figures, copy a template from `connectors/templates/` into
`inputs/`, fill it, and set `"enabled": true` in the config's `connectors` block.

**3. Theme exposure** (segments, geography, customers, analyst coverage):

```bash
UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run theme_exposure.py --themes examples/themes_security_resilience.json
```

**4. Run the Monte Carlo example** (no WRDS needed; fictional inputs):

```bash
uv run --no-project --with numpy python examples/monte_carlo_example.py
```

It prints expected return, raw P(loss) next to P(below hurdle), value quantiles, the entry price and an
own-history volatility cross-check, with and without multiple reversion, plus a scenario tree.

## Using the Claude Code skill and agents

Open the repository in Claude Code. It picks up:

- **Skill** `.claude/skills/wrds/`: how to query WRDS safely (credentials, caching, parameterized SQL, no
  hard-coded dataset dates), the screen engine and dataset notes.
- **Agents** `.claude/agents/`: `equity-research-analyst` (hypotheses and screens), `scenario-analyst`
  (regressions, scenarios, Monte Carlo) and `red-team-reviewer` (independent challenge).
- **Slash commands** `.claude/commands/`: `/wrds-setup`, `/research-kickoff`, `/hypotheses`, `/challenge`,
  `/screen`, `/theme-exposure`, `/deep-dive`, `/filings`, `/valuation`.
- **Shared board** `research/board.py` and house rules `research/TEAM.md`: agents post findings and challenges
  to an append-only log (git-ignored).

A typical round: `/wrds-setup`, `/research-kickoff <theme and constraints>`, `/hypotheses`, `/challenge`,
`/screen H1`, `/theme-exposure`, `/deep-dive <names>`, `/filings <names>`, `/valuation`.

## Repository map

```
pipeline.py               screen -> analysis -> report, one WRDS connection
analysis.py               history, quarterly trend, prices, peers, I/B/E/S estimates, flags
theme_exposure.py         theme tagging from segments, GICS, descriptions and anchor customers
check_access.py           which WRDS libraries your account can read
store_password.py         writes your ~/.pgpass with a hidden prompt (run it yourself)
connectors/               optional file adapters: Capital IQ export, user-entered industry figures
  templates/              header-only templates you fill in inputs/ (git-ignored)
pipelines/                example screen and watchlist configs (a handful of public identifiers each)
examples/                 example theme set, illustrative Monte Carlo inputs and a runnable example
methodology/              the analysis engines from the original case work, inputs replaced by placeholders
  scenario/               data layer, returns / multiple / driver regressions, base rates, simulations, audits
  amkor/ atkins/ hdhyundai/   single-company case engines (drivers, multiples, returns, simulation, finals, audits)
  cross_case/             cross-case ranking after a rerun, scorecard arithmetic
docs/METHODOLOGY.md       the end-to-end process in plain English
research/                 TEAM.md house rules and board.py (everything else there is git-ignored)
.claude/                  skill, agents and slash commands
```

## Methodology summary

1. **Theme definition**: sub-themes as segment, code, keyword and anchor-customer rules.
2. **Global screen** across Compustat North America and Global in USD, with every threshold in config and every
   date window anchored on the data's own latest date.
3. **Deep dives and peer sets** on one source and date; data problems flagged, not hidden.
4. **Filings reads** for what databases do not hold: segment and end-market shares, backlog, guidance.
5. **Scenarios**: mutually exclusive states plus two-sided overlays, signed correlations, sourced probabilities.
6. **Statistics**: returns regressions with event dummies, HAC errors and permutation tests; multiple
   cross-sections on several samples with robust variants; driver elasticities clustered by year; base rates.
7. **Monte Carlo conventions**: forward multiple on the not-yet-reported year, a stated reversion rule shown on
   and off, raw P(loss) next to P(below hurdle), an entry-price rule, own-history volatility scaled by the
   square root of time.
8. **Multi-agent workflow**: extractors, quant, red-team challenger, reconciler and translator on a shared
   append-only board, with pre-committed scorecards before results.

Details and the lessons the audits caught: [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Responsible use

- **No data in git.** `data/`, `output/`, `inputs/`, `research/` notes, `*.csv`, `*.xlsx` and similar are
  git-ignored. Check `git status` before every commit; scrub history if anything slips in.
- **Outputs stay local.** Screen results, reports and dossiers are built from licensed data. Share conclusions
  and aggregates as your agreements allow, not extracts.
- **Use only your own credentials.** Do not share accounts, and do not automate any provider's website.
- **Label sources.** Every figure carries [WRDS data], [company filing], [report], [source] or [inference].
- **No advice.** The toolkit produces evidence, likelihoods and projections, never buy or sell calls.
- If you publish results built with it, follow your providers' citation and credit requirements.

## License

MIT, see [LICENSE](LICENSE). The licence covers the code only, not any data you use with it.
