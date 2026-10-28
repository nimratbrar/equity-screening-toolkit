# WRDS datasets for screening (our working notes)

Short notes written for this toolkit, not vendor documentation. Table and column names only; check the
official WRDS documentation and `w.columns(...)` for definitions. What you can read depends on your
institution's subscription.

Latest dates are NOT listed on purpose: run `w.freshness()` or `w.latest_date("lib.table")`.

## Identifiers and joins
| ID | Where | Notes |
|---|---|---|
| `gvkey` | Compustat (all), finratio, CCM | Company key. Text, zero-padded 6 chars. |
| `iid` | comp.secd/secm | Issue within a company. Primary: `comp.company.priusa` (US), `prican` (Canada). |
| `permno` / `permco` | CRSP, finratio | Security / company. Link to gvkey with `crsp.ccmxpf_lnkhist`. |
| `cusip` | Compustat (9), CRSP (8), IBES (8) | First 8 chars match across. |
| `cik` | comp.company, pitchbk.company (`cikcode`) | SEC ID; links public PitchBook entries to Compustat. |
| IBES `ticker` | ibes.* | Internal IBES code, not the exchange ticker (`oftic` is the official ticker). |
| `companyid` | pitchbk.* | PitchBook company key; `dealid` for deals. |

## Compustat North America (`comp`)
- `company`: one row per gvkey. conm, fic, loc, state, city, costat (A/I), gsector, ggroup, gind, gsubind,
  sic, naics, busdesc, weburl, ipodate, priusa, prican, cik, curr_sp500_flag.
- `funda`: annual. Filter `indfmt='INDL' and datafmt='STD' and popsrc='D' and consol='C'`.
  Key items: sale, revt, cogs, xsga, xrd, oibdp (EBITDA), oiadp (EBIT), ib, ni, dp, xint, txt, pi, capx,
  oancf, at, lt, act, lct, che, invt, rect, ceq, seq, pstk, mib, dltt, dlc, csho, prcc_f, dvc, dvt, emp,
  curcd, fyear, fyr, datadate.
- `fundq`: quarterly, same filter. Items end in `q` (saleq, niq, atq); cash-flow items are
  year-to-date and end in `y` (oancfy, capxy). `rdq` = report date. TTM = sum of last 4 `q` values.
- `secd`: daily. prccd (close), cshoc (shares), ajexdi (split adj.), trfd (total-return factor), exchg,
  curcdd, div, tic. Market cap = prccd * cshoc. Adjusted price = prccd / ajexdi.
- `secm`: monthly. prccm, ajexm, trfm, trt1m (monthly total return %), cshoq.
- Also: `comp_segments_hist_daily` (seg_ann, seg_customer, seg_geo, seg_product, wrds_segmerged),
  `comp_execucomp`, `comp_pit` / `comp_snapshot` (point-in-time), `comp_ratings`.

## Compustat Global (`comp_global_daily`)
g_company, g_funda, g_fundq, g_secd (adds isin, sedol, qunit), g_secm, g_exrt_dly / g_exrt_mth
(FX rates vs GBP; convert via USD cross), g_idx_*. Net income is `nicon` and shares outstanding `cshoi` in g_funda (no `ni`/`csho`); `fundamentals_annual` maps them onto the NA names. Same standard filter but `popsrc='I'`. Values in
native currency (`curcd`); convert before comparing across countries.

## CRSP (`crsp`), CIZ/v2 format
- `msf_v2`: monthly. permno, permco, mthcaldt, mthprc, mthret (incl. dividends and delisting), mthretx,
  mthcap ($ thousands), shrout, ticker, issuernm, siccd, primaryexch, and filter flags (sharetype,
  securitytype, securitysubtype, usincflg, issuertype, conditionaltype, tradingstatusflg).
- `dsf_v2`: daily equivalent (dlycaldt, dlyprc, dlyret, dlycap, dlyvol).
- `stksecurityinfohist`: historical security info (secinfostartdt/enddt), use for historical industry.
- `ccmxpf_lnkhist`: gvkey, lpermno, linktype (use LU, LC), linkprim (P, C), linkdt, linkenddt (null = open).
- Legacy `msf`/`dsf` are frozen; don't use for current work.

## WRDS Financial Ratios Suite
- `wrdsapps_finratio.firm_ratio` (and `wrdsapps_finratio_ccm.firm_ratio_ccm`): monthly by `public_date`,
  keys gvkey + permno, US, excludes financials. About 70 ratios covering valuation (for example `bm`, `evm`, `ptb`),
  profitability (`roe`, `roa`, `gpm`), leverage (`debt_ebitda`, `de_ratio`) and liquidity; list them with
  `w.columns("wrdsapps_finratio", "firm_ratio")`.
- Can lag Compustat by months. Check `w.latest_date("wrdsapps_finratio.firm_ratio")`.

## I/B/E/S (`ibes`)
- `statsum_epsus`: monthly consensus (US). ticker, cusip, oftic, cname, statpers, measure (EPS...), fpi
  ('1' FY1, '2' FY2, '6' next Q), fpedats, numest, meanest, medest, stdev, highest, lowest, numup, numdown, actual.
- `det_epsus`: individual analyst estimates (huge, always filter). `act_epsus`: actuals.
  `det_guidance` / `tr_ibes_guidance`: management guidance. `idsum`: ID history.

## PitchBook (`pitchbk`; region cuts in `pitchbk_vc_na`, `pitchbk_pe_na`, `pitchbk_companies_deals`, ...)
- `company`: companyid, companyname, description, keywords, verticals, emergingspaces,
  primaryindustrysector/group/code, allindustries, businessstatus, ownershipstatus, companyfinancingstatus,
  hqcountry, hqstate_province, hqcity, yearfounded, employees, totalraised, revenue, grossprofit,
  netincome, ebitda, enterprisevalue, netdebt, ticker, exchange, cikcode, lastfinancingdate/size/
  valuation/dealtype, lastknownvaluation, activeinvestors, parentcompany, website. Money in USD millions.
- `deal`: dealid, companyid, dealdate, announceddate, dealsize, dealtype(2,3), dealclass,
  dealstatus, vcround, premoneyvaluation, postvaluation, investors, revenue, ebitda, valuation_revenue,
  impliedev_ebitda, percentacquired, exitscope.
- Relations: companyindustryrelation, companyinvestorrelation, companycompetitorrelation,
  companyfinancialrelation (time series), dealinvestorrelation, investor, fund, fundreturnrelation.
- Deal/company dates include placeholders in the future, so always cap at today.

## Other libraries that may be in your subscription
ciq (Capital IQ: transactions, key developments, transcripts), revelio (workforce, job postings,
layoffs), tr_13f (institutional holdings), sdc / tr_sdc_ma (M&A), boardex, execcomp, ravenpack (news
sentiment), trucost / msci (ESG), optionm (options), fisd / trace (bonds), wrdsapps_link_* (link tables),
wrdsapps_patents, wrdsapps_link_supplychain. Explore with `w.tables(lib)` + `w.sample(...)` before use.
