# Methodology scripts

The analysis engines from the original case work, kept as worked examples of the method in
`docs/METHODOLOGY.md`. Logic is unchanged; every company-specific input that came from a licensed database is
replaced by an obviously illustrative value inside a block marked `PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY`.
Public filing figures that remain are labelled with their source. Running a script end to end needs your own
data layer (`scenario/pull_data.py` and the peer configs in `pipelines/`) and your own inputs.

| Folder | Contents |
|---|---|
| `scenario/` | Data layer (`pull_data.py`, `reg_common.py`); returns regressions with event dummies (`reg_returns.py`); multiple cross-sections (`reg_multiples.py`); driver elasticities (`reg_drivers.py`); base rates (`reg_baserates.py`); scenario Monte Carlo v1, v2 and a rerun (`simulate*.py`); red-team audits (`audit_*.py`, `geo_check.py`) |
| `amkor/`, `atkins/`, `hdhyundai/` | Single-company case engines: `*_common` (inputs and loaders), `*_drivers`, `*_multiples`, `*_returns`, `*_simulate`, `*_final` and `*_final_1027` (rerun), audits |
| `cross_case/` | Cross-case ranking after a rerun (`ranking_1027.py`) and pre-committed scorecard arithmetic (`q3_2026_arith.py`) |

Each folder has a `board.py` copy of the shared board helper. Output tables go to `tables/` (git-ignored).
Company names identify the case structure only; placeholder numbers are not estimates for those companies.
