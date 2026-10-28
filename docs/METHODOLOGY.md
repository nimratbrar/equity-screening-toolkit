# Methodology

How the toolkit goes from a theme to a short list of audited, scenario-tested cases. Every number in this
document is a generic illustration, not a result for any real company. The code that implements each step is
named in brackets.

Contents

1. Theme definition
2. Global screen with no hard-coded cutoffs
3. Deep dive and peer sets
4. Filings reads
5. Scenario building
6. Valuation and Monte Carlo conventions
7. Statistics: returns regressions, cross-sections and base rates
8. The multi-agent workflow
9. Pre-committed scorecards and reruns
10. Lessons the audits caught
11. Source labels

---

## 1. Theme definition

A theme is a set of sub-themes, each with a structural driver (for example grid hardening, supply-chain
reshoring, energy security). Each sub-theme becomes a machine-readable definition
[`examples/themes_security_resilience.json`, read by `theme_exposure.py`]:

- **Segment regex and segment NAICS**: business-segment names and codes that count as exposure, plus an
  exclusion regex for false positives (a "cable" segment can be television, not power cable).
- **Core GICS sub-industries** and an **include list** of names known to be in the theme.
- **Business-description keywords** for companies with no segment data (most non-US filers).
- **Anchor customers**: large buyers in the theme. Compustat customer segments then surface second-order
  suppliers that a sector screen misses.

The output per theme is a company list with the share of sales in theme segments, segment growth and margin,
US and China sales shares, analyst count (a crowding proxy), and how each company was matched (segment, GICS,
name or description only). A match by description only is flagged as unverified exposure.

Hypotheses are written before any data is pulled, each with: the driver, why it may not be priced in, the
evidence and its source, what would disprove it, and the observable metrics that would identify the winners.

## 2. Global screen with no hard-coded cutoffs

[`.claude/skills/wrds/scripts/screen.py`, `pipeline.py`, configs in `pipelines/`]

- **Universe**: Compustat North America plus Compustat Global, one row per company, all money converted to USD
  at the latest exchange rate (so growth rates stay in local currency). Non-traded and OTC exchange codes are
  excluded by default; financials are usually excluded because EBITDA and EV metrics do not apply.
- **No hard-coded dates.** Every date window is anchored on the latest date actually present in each table
  (`w.latest_date()`, `w.freshness()`), capped at today, because WRDS tables update on different schedules and
  some hold placeholder future dates. A screen can be re-run "as of" a past date, with fundamentals lagged by a
  reporting delay.
- **No hard-coded thresholds in code.** Every filter, custom metric and score weight lives in the JSON config.
  Filters start loose; the printed funnel (companies left after each step) shows which filter is binding, and
  the threshold is moved there, not elsewhere.
- **Scoring**: weighted percentile ranks of the chosen metrics, optionally within sector, so a capital-light and
  a capital-heavy business are not ranked on the same raw ROIC.
- **Watchlist mode**: instead of a ranked screen, `"analysis": {"names": [...]}` analyzes exactly the listed ISINs
  or tickers from the unfiltered dataset. This is how case companies and their peers are pulled on one basis.

## 3. Deep dive and peer sets

[`analysis.py`, `pipeline.py`]

For each shortlisted company the pipeline writes, from one WRDS session:

- 10 or more years of annual history, the quarterly trend, price performance and liquidity.
- A **peer comparison** at the GICS sub-industry level (or a named peer set) with medians and percentiles.
- **Analyst estimates** from I/B/E/S (US and international): FY1 and FY2 EPS, sales and EBITDA consensus, number
  of analysts, implied forward multiples.
- Rule-based **risk and strength flags** (leverage, dilution, margin trend, stale data).
- A per-company JSON dossier for later steps, and a "Valuation inputs" sheet in the reporting currency.

Peer sets are written as explicit configs (`pipelines/peers_*.json`) so every multiple used later comes from the
same source and date. Data problems are flagged, not hidden: stale net debt, share splits that break a forward
P/E, estimates in a different unit (thousands versus billions for JPY or KRW), peer groups from the wrong
industry, and blank fields.

**Optional inputs.** A Capital IQ screen export the user downloads under their own licence, and industry figures
the user types from a report they license (for example IBISWorld), can be merged in through `connectors/`.
Both are off by default; the pipeline runs on WRDS alone.

## 4. Filings reads

Databases do not hold what decides most theses: the share of sales tied to the theme by end market, segment
margins, backlog and its duration, contract terms, capacity plans and management targets. Extractor agents read
the company's own documents (annual report, results presentation, medium-term plan) converted to text, search
for the relevant pages rather than reading everything, and write a short note with a page reference on every
figure, a list of what could not be found, and anything that contradicts the thesis.

## 5. Scenario building

[`methodology/scenario/simulate_v2.py`, `methodology/*/..._simulate.py`, `methodology/scenario/geo_check.py`]

- **Mutually exclusive states** for the variable that cannot be in two states at once (for example the demand
  cycle: downturn, plateau, boom). Their probabilities sum to one; the base state takes the residual and is
  reported as it comes out, never forced to a target.
- **Overlays** for events that can co-occur with any state and with each other (policy changes, a blockade, a
  currency move, an execution failure). Overlays are **two-sided**: the table must contain upside overlays as
  well as downside ones, and an impact range may straddle zero.
- **Joint distribution**: a Gaussian copula with **signed** pairwise correlations stated in the code (a recession
  and a commodity spike can be negatively related), projected to the nearest positive semi-definite matrix if
  needed. Do not solve one common correlation to hit a target base probability: it creates implausible joint
  events.
- **Impacts** are ranges on EBITDA and on the exit multiple, checked against the company's own history in past
  episodes of the same kind (what did EBITDA actually do in the last memory downturn?) and against backlog
  timing (a backlog delays a demand hit but not a hit from lost access to a site).
- **Probabilities** come from a stated source with a date: prediction markets and surveys are quoted as given;
  any adjustment (time-value haircut on a long-dated contract, contract wording that does not match the economic
  event, thin liquidity) is labelled [inference]. Play-money or very thin markets are dropped.

## 6. Valuation and Monte Carlo conventions

[`examples/monte_carlo_example.py` is a self-contained, runnable version of these rules]

1. **Forward multiple on the not-yet-reported year.** Today's forward multiple is
   (price x shares - net cash) / EBITDA of the first fiscal year not yet reported. At a horizon, value is the
   EBITDA of the first fiscal year still unreported at that horizon times the multiple, plus net cash at the
   horizon. The multiple and the EBITDA must refer to the same year.
2. **No double discounting.** A forward multiple already prices the forward year, so a 12-month value is not
   discounted again. The hurdle enters only through the probability in rule 4.
3. **Multiple path.** Start at today's forward multiple, apply a triangular spread from the peer multiple range,
   then the scenario factors. **Reversion rule**: the log residual of today's multiple versus the cross-section
   fit (section 7) closes at a slope per year estimated from history, capped at full closure. Results are shown
   with and without reversion (variants a and b), because one rule can carry a whole ranking.
4. **Raw P(loss) versus hurdle.** Report P(value < price) and P(return < hurdle) side by side and never label one
   as the other.
5. **Idiosyncratic EBITDA noise** is calibrated so the simulated one-in-ten EBITDA shortfall versus the forecast
   mode matches the peer group's historical one-in-ten fall, measured as a deviation from forecast, not as a
   year-on-year change (which includes trend growth). A floor stops scenario shocks from driving sigma to zero.
6. **Own-history volatility scaled by the square root of time.** As a cross-check, rescale the log value
   dispersion so its standard deviation equals the stock's own 12-month log-return volatility times
   sqrt(years), keeping the median. If the conclusion flips, say so.
7. **Entry-price rule.** Entry price = min(35th percentile of simulated value, mean value / 1.15): the highest
   price at which raw P(loss) is below 35% and the expected return above 15%. State which variant it uses.
8. **One consistent basis.** Shares, net debt, pensions and leases come from one dated source; never mix a
   database share count with a diluted count from a filing. Working-capital and one-off cash effects of
   scenarios are deducted explicitly.
9. **Reproducibility.** Fixed seed, 20,000 paths per company, horizon and variant; every output table written to
   disk; a rerun "bridge" decomposes any change into price, consensus and parameter steps.

Outputs per case: summary statistics, a scenario tree (for exclusive states: P x E[return | state]; for overlays:
P x (E[return | on] - E[return | off])), a tornado of the inputs that move the result most, a base-rate cross-check
and entry prices.

## 7. Statistics: returns regressions, cross-sections and base rates

[`methodology/scenario/reg_*.py`, `methodology/*/..._returns.py`, `..._multiples.py`, `..._drivers.py`, audits in `audit_*.py`]

**Returns regressions with event dummies.** Weekly log total returns on the local market index, an equal-weight
peer basket and the relevant exchange rate, plus one dummy per event week (events in the same week share a
dummy, otherwise the design matrix is rank-deficient).

- Standard errors are **HAC** (Newey-West), with the result checked at several lag lengths.
- For a one-week dummy HAC and HC1 errors are degenerate; quote the classical t or, better, a **permutation
  test**: the mean factor-model residual in the event weeks versus 5,000 random draws of the same number of
  non-event weeks.
- Events are pooled by expected sign into a few dummies, and a single signed dummy (+1 in good-news weeks, -1 in
  bad-news weeks) tests whether the signs predict the move at all.
- A peer basket absorbs industry-wide reactions, which is exactly what a macro event causes. Run a market-only
  version and a pooled daily event study (CAR from day -1 to +5, estimation window ending 10 days before) on an
  equal-weight portfolio of the whole group, so cross-correlation stays in the variance.
- Correct for multiple testing (Bonferroni over the number of tests) and check Friday or after-close events by
  shifting them a week.
- The market coefficient next to a correlated peer basket is a *partial* beta. Report the total beta with the
  basket orthogonalised to the market.

**Multiple cross-sections and residuals.** Log trailing (or forward) EV/EBITDA on ROIC, three-year revenue
growth, EBITDA margin, leverage and log size, with country and industry dummies, on several samples: the case and
peer core, the broad universe above a size floor, and the broad universe restricted to the peer industries.
Robustness: winsorized inputs, Huber and median regression, trimmed multiple ranges, dropping high-influence
points (Cook's distance), and a control for expected growth (FY2 EPS growth from I/B/E/S). A case's residual is
used only if it survives most specifications; the reversion slope comes from regressing the next 12-month change
in the log multiple on this year's residual (an upper bound, since it includes EBITDA noise).

**Driver elasticities.** Revenue growth and margin change on an external driver (industry billings, a commodity
price, a policy rate) at lag 0 and lag 1, firm fixed effects. Because the driver is common to all firms in a
year, cluster by **year**, not by firm: there are only as many independent observations as years. Check
sub-period stability and lag 2.

**Base rates.** The distribution of 12-month total returns (overlapping daily windows) and maximum drawdown per
case and per peer group, and the frequency of EBITDA falls of 10, 20 and 30% in the peer group and in the
broad industry. Peer baskets chosen with today's screen are survivorship-biased upward; say so.

## 8. The multi-agent workflow

Agents are defined in `.claude/agents/` and driven by the playbooks in `.claude/commands/`. House rules are in
`research/TEAM.md`.

| Role | What it does | What it never does |
|---|---|---|
| Extractors | Turn reports and filings into short, page-referenced notes | Interpret beyond the document |
| Equity research analyst | Hypotheses, screen configs, shortlists | Read raw licensed reports directly |
| Quant (scenario analyst) | Regressions, scenario tables, Monte Carlo | Change inputs without logging the change |
| Red-team challenger | Attacks one lens (statistics, geopolitics, business logic), re-runs from code | Accept the author's summary as evidence |
| Reconciler | Merges challenges, states which argument it accepted and why | Average two conflicting answers |
| Translator | Plain-English decision document with pre-committed scorecards | Add buy or sell language |

**Shared append-only board.** All agents post to `research/board.md` through `research/board.py` (atomic appends,
numbered posts, types BROADCAST, QUESTION, CHALLENGE, REPLY, DECISION, STATUS, under 150 words each). Nothing
is edited after posting; corrections are new posts that cite the old number. Every agent reads the board before
starting and before finishing.

**Labels.** Every number carries [WRDS data], [company filing: doc, p.N], [report: file, p.N],
[source: name, date, URL] or [inference]. Code and arithmetic are shown so any figure can be audited.

## 9. Pre-committed scorecards and reruns

Before a company reports, the translator writes a scorecard: five or six lines (for example organic growth in
the theme segment, margin, orders or backlog, cash flow, guidance), each with PASS / IN-BETWEEN / FAIL thresholds
taken from filings, and the **consequence** of each outcome (re-rank, re-base the EBITDA path, drop the case).
After the results, a separate agent scores each line from the company's documents
[`methodology/cross_case/q3_2026_arith.py`] and the rerun applies only the pre-committed consequences
[`methodology/*/..._final_1027.py`, `methodology/cross_case/ranking_1027.py`]. If the scorecard pre-committed only
a ranking change, scenario weights and the EBITDA path are left alone. Inconsistencies between two documents'
rules are reported for the user to decide, not resolved silently.

Reruns keep the engine, scenario set, correlations and seed unchanged and change inputs only, so a diff of the
two scripts is the audit trail, and a bridge table shows how much of the change came from price, consensus and
parameters.

## 10. Lessons the audits caught

Generic versions of what the red-team reviews found in the original work:

1. **One rule carried a ranking.** The top case was first only because of multiple mean reversion; without it,
   it ranked last. Always show results with and without reversion.
2. **Mislabelled loss probability.** "P(loss)" was really P(return < hurdle) on an already-discounted value.
   Report raw P(loss) and P(below hurdle) separately, and do not discount a forward-multiple value again.
3. **Double-counted re-rating.** Base exit multiples were set above today's forward multiple and reversion then
   added more re-rating on top. Start at today's forward multiple and apply reversion once.
4. **Mismatched years.** A forward multiple was applied to the wrong year's EBITDA. Use the first year not yet
   reported at the horizon.
5. **Partial betas reported as total betas.** "All below-one beta" became above one once the peer basket was
   orthogonalised.
6. **Degenerate standard errors on single-week dummies.** The same code produced HC1 t-statistics of opposite
   signs; permutation tests showed no effect.
7. **Overstated panel t-statistics.** Firm-clustered errors on a year-level driver overstated significance;
   year clustering removed it for some groups.
8. **Forced base probabilities.** Solving one correlation to hit a target base share created implausible joint
   events; signed pairwise correlations fixed it.
9. **Probability sources that do not match the event.** A prediction-market contract resolved on a different
   event than the one modelled, at long horizon and thin liquidity. Map contract wording to the economic event and
   apply a time-value haircut.
10. **Sigma calibrated on the wrong basis.** Year-on-year falls include trend growth; calibrate against
    deviation from forecast.
11. **Stale holiday rows.** A market holiday left stale prices in the file, biasing daily betas slightly.
12. **Inconsistent share counts and net debt.** Database share counts and filing-diluted counts differ; so does
    net debt at different dates when capex is front-loaded. Use one dated basis and model the net debt build.
13. **Survivorship in peer baskets.** Peers chosen by today's market cap inflate historical return base rates.
14. **Reproducibility check.** Every table was regenerated from a clean cache before any conclusion was used.

## 11. Source labels

| Label | Meaning |
|---|---|
| [WRDS data] | Pulled from a WRDS library (Compustat, I/B/E/S, CRSP, segments) under the user's own licence |
| [company filing: doc, p.N] | The company's own published document |
| [report: file, p.N] | A licensed or public industry report the user supplied |
| [source: name, date, URL] | Any other public source, such as a statistics agency or a prediction market |
| [inference] | The analyst's own judgment or computation |

No licensed data ships with this repository. Scripts under `methodology/` keep the original logic but their
company-specific inputs are replaced by clearly marked illustrative placeholders; real inputs must come from the
user's own licensed data and the companies' filings.
