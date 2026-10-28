# Screen config (JSON)

Every key is optional; defaults are shown. Dates are never hard-coded: freshness windows are measured
from the latest date in the data.

```jsonc
{
  "name": "screen",                 // output file prefix
  "history_years": 5,               // fiscal years pulled (need >= 4 for 3y CAGR)
  "max_staleness_months": 18,       // drop firms whose latest FY end is this far behind the newest FY in the data
  "report_lag_days": 90,            // with --as-of: only use fundamentals dated this long before as-of
  "region": "global",               // global = Compustat NA + Global; "na" or "intl" to narrow

  "universe": {
    "countries": null,              // HQ country (loc), ISO-3, e.g. ["USA", "GBR", "DEU", "JPN"]. null = world
    "incorporation_countries": null,// fic
    "currency": null,               // reporting currency filter, e.g. "EUR"
    "active_only": true,            // costat == 'A'
    "exchanges": null,              // whitelist of comp exchg codes (US: 11 NYSE, 12 NYSE American, 14 NASDAQ)
    "exclude_exchanges": [0, 1, 2, 3, 4, 13, 19],   // non-traded / subsidiary / OTC
    "include_gsectors": null,       // e.g. ["45"]
    "exclude_gsectors": [],         // e.g. ["40", "60"] to drop financials and REITs
    "gics_prefixes": null,          // prefix of the 8-digit gsubind, e.g. ["4530", "452030"]
    "sic_ranges": null,             // [[2830, 2839], [3841, 3845]]
    "naics_prefixes": null,         // ["5112", "5182"]
    "keywords_any": null,           // matched in busdesc + name, case-insensitive
    "keywords_none": null,
    "min_market_cap": null,         // USD mm, latest daily price
    "max_market_cap": null,
    "min_revenue": null             // USD mm, latest FY
  },

  "filters": [                      // applied in order; each step is reported in the funnel
    {"metric": "rev_growth_1y", "min": 0.10},
    {"metric": "net_debt_to_ebitda", "max": 3, "allow_missing": true},
    {"column": "gsubind", "in": ["45103010"]}   // any column works via "column"
  ],

  "custom_metrics": {               // pandas eval over Compustat items + built-in metrics
    "rd_to_gross_profit": "xrd / (sale - cogs)",
    "capex_to_da": "capx / dp"
  },

  "extra_ratios": ["bm", "evm", "accrual"],   // WRDS Financial Ratios Suite columns (US only), joined as fr_<name>

  "scoring": {
    "metrics": [                    // weighted percentile ranks -> score 0-100
      {"metric": "rev_cagr_3y", "weight": 2, "direction": "high"},
      {"metric": "ev_to_ebitda", "weight": 1, "direction": "low", "winsorize": 0.02}
    ],
    "rank_within": null,            // e.g. "sector", "gsubind" or "loc" to rank against peers
    "min_coverage": 0.6             // share of total weight a firm needs non-missing to be scored
  },

  "output": {"dir": "output", "top_n": 50, "columns": ["gross_margin", "fcf_yield"]}
}
```
(Comments are for reading only; real config files must be plain JSON.)

Built-in metrics: run `screen.py --list-metrics`. Compustat items usable in `custom_metrics` or
`"column"` filters: sale, cogs, xsga, xrd, oibdp, oiadp, ni, ib, dp, xint, txt, pi, capx, oancf, at, lt, act,
lct, che, invt, rect, ceq, seq, pstk, mib, dltt, dlc, csho, prcc_f, dvc, dvt, emp, plus `_l1` / `_l3` lags
of sale, cogs, oibdp, oiadp, ni, at, ceq, emp, csho, oancf, capx, and market_cap, total_debt, net_debt,
invested_capital, price_usd. All money is USD millions after conversion. An item missing from a region's
table (e.g. prcc_f in g_funda) comes back blank rather than failing. To add a Compustat item, append it to `FUNDA_COLS` in `wrds_client.py`.
