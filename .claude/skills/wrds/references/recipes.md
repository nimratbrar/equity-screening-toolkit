# SQL recipes (run with `w.sql(sql, params)`)

## Compustat + CRSP (CCM merge)
```sql
select f.gvkey, f.datadate, f.sale, l.lpermno as permno
from comp.funda f
join crsp.ccmxpf_lnkhist l on l.gvkey = f.gvkey
 and l.linktype in ('LU','LC') and l.linkprim in ('P','C')
 and f.datadate between l.linkdt and coalesce(l.linkenddt, current_date)
where f.indfmt='INDL' and f.datafmt='STD' and f.popsrc='D' and f.consol='C'
  and f.fyear >= %(y0)s
```

## Trailing returns from CRSP v2 (window anchored on the latest month in the data)
```python
end = w.latest_date("crsp.msf_v2")
m = w.crsp_monthly(str((end - pd.DateOffset(months=12)).date()), str(end.date()), permnos=ids)
ret_12m = m.groupby("permno")["mthret"].apply(lambda r: (1 + r).prod() - 1)
```
For fresher returns than CRSP has, use comp.secm total return index `prccm / ajexm * trfm`
(`w.monthly_prices_compustat`) or daily `prccd / ajexdi * trfd` from comp.secd.

## TTM from quarterly
```python
q = w.fundamentals_quarterly(start_date=..., gvkeys=...).sort_values(["gvkey","datadate"])
ttm = q.groupby("gvkey").tail(4).groupby("gvkey")[["saleq","oibdpq","niq"]].sum(min_count=4)
```

## I/B/E/S consensus onto Compustat
```python
est = w.ibes_consensus(fpi="1")                     # window anchored on latest statpers
fa = w.fundamentals_annual(start_year=...)
key = fa.drop_duplicates("gvkey", keep="last")[["gvkey","cusip"]].assign(cusip8=lambda d: d.cusip.str[:8])
est = est.merge(key, left_on="cusip", right_on="cusip8")
# forward P/E = price / meanest ; dispersion = stdev / abs(meanest) ; revisions = numup - numdown
```

## PitchBook: private companies in a theme, with latest round
```sql
select c.companyid, c.companyname, c.hqcountry, c.totalraised, c.lastfinancingdate,
       c.lastfinancingdealtype, c.lastfinancingvaluation, c.revenue
from pitchbk.company c
where c.ownershipstatus ilike %(own)s
  and (c.description ilike any(%(kw)s) or c.verticals ilike any(%(kw)s))
  and c.lastfinancingdate <= current_date
order by c.lastfinancingdate desc nulls last
limit 500
```
params: `{"own": "%Privately Held%", "kw": ["%robot%", "%automation%"]}`. Check real category values
first: `w.sql("select ownershipstatus, count(*) as n from pitchbk.company group by 1 order by 2 desc limit 20")`.

Public comps from PitchBook to Compustat: `pitchbk.company.cikcode` = `comp.company.cik` (strip leading zeros).
Private deal multiples for a sector: `pitchbk.deal` columns `valuation_revenue`, `impliedev_ebitda`; filter
`dealdate` within N years of `w.latest_date("pitchbk.deal")`.

## Segments (revenue by business line / geography / customer)
```python
w.columns("comp_segments_hist_daily", "wrds_segmerged")   # check columns first
seg = w.sql("select * from comp_segments_hist_daily.wrds_segmerged where gvkey in %(g)s", {"g": tuple(gvkeys)})
```
`seg_customer` lists major customers (useful for supply-chain theses).

## Compustat Global (non-US)
Use `comp_global_daily.g_funda` with `popsrc='I'`. Values are in native `curcd`. Convert with
`g_exrt_dly` (rates quoted vs GBP: `value_usd = value / exratd[curcd] * exratd['USD']` on the same date).
Market cap: `g_secd.prccd * cshoc`, divided by `qunit` when prices are quoted in units.

## Checking what's current
```python
w.freshness()                                   # all key datasets
w.latest_date("comp.fundq")                     # one table
w.latest_date("some_lib.some_table", "date_col")
```
