"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

HDE analysis 3: driver sensitivities and cycle base rates.
(a) Backlog and orders vs revenue: quarterly orders, backlog (USD m) and sales (KRW bn) [company filing: quarterly results decks],
    USD/KRW quarterly averages [source: FRED DEXKOUS]. Book-to-bill, conversion (sales in USD / opening backlog), and the 2027 revenue
    implied by the backlog under stated conversion and FX [inference]. n = 6 quarters and 3 years: descriptive, not a regression.
(b) US transformer PPI (FRED PCU335311335311, power and distribution transformers) vs margins: HDE quarterly gross and operating margin
    (Compustat quarterly, 2018 to 2026) on PPI y/y at lags 0 to 6 quarters, HAC t; annual grid-peer panel (EBITDA margin change on PPI
    y/y, t0 and t-1, firm fixed effects, year-clustered t).
(c) Cycle base rates: grid peers and HDE, Compustat annual FY2014 to FY2025 (file start): year-on-year EBITDA changes, falls, falls after a
    3-year margin expansion, and the deviation-basis sigma (log EBITDA growth minus the peer-year median) used in hde_simulate.py.
    HDE's own 2017 to 2021 bust and the ABB 2008 to 2012 analogue (hde_series.csv) are listed alongside.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_drivers.py
Outputs (tables/): hde_backlog_conversion.csv, hde_ppi_margin.csv, hde_ebitda_base_rates.csv, hde_fx_points.csv
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from hde_common import TABLES, DATA, PEERS, HDE, NAME, usdkrw, fred, quarterly

# ---------------- FX points [source: FRED DEXKOUS]
k = usdkrw()
fxp = {"avg 2024": k.loc["2024"].mean(), "avg 2025": k.loc["2025"].mean(), "avg 1H26": k.loc["2026-01":"2026-06"].mean(), "avg Q3'26": k.loc["2026-07":"2026-09"].mean(),
       "avg 2026 YTD": k.loc["2026"].mean(), "max 2026": k.loc["2026"].max(), "spot (last)": k.iloc[-1], "spot date": str(k.index[-1].date())}
# share of 12m windows since 2000 with a >=10% won appreciation / depreciation (log change of KRW per USD over 252 obs)
kk = k.loc["2000":]; ch = np.log(kk / kk.shift(250)).dropna()
fxp["P(won +10% in 12m), since 2000"] = float((ch <= np.log(1 / 1.10)).mean()); fxp["P(won -10% in 12m), since 2000"] = float((ch >= np.log(1.10)).mean())
fxp["sd 12m log change, since 2000"] = float(ch.std())
pd.Series(fxp, name="value").to_csv(TABLES / "hde_fx_points.csv")

# ---------------- (a) backlog conversion [company filing: quarterly results decks; public]
Q = pd.DataFrame({
    "quarter": ["Q1'25", "Q2'25", "Q3'25", "Q4'25", "Q1'26", "Q2'26"], "end": pd.to_datetime(["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31", "2026-06-30"]),
    "sales_krw": [1014.7, 906.2, 995.4, 1163.2, 1036.5, 1141.8], "op": [218.2, 209.1, 247.1, 320.9, 258.3, 287.0],
    "orders_usd": [1335, 996, 1212, 730, 1797, 1440], "backlog_usd": [6155, 6550, 6983, 6731, 7888, 8490],
    "na_orders": [745, 415, 763, 254, 1315, 853], "na_sales_krw": [388.9, 317.8, 353.7, 554.5, 492.3, 541.9]})
Q["usdkrw_avg"] = [k.loc[e - pd.offsets.QuarterBegin(startingMonth=1):e].mean() for e in Q.end]
Q["sales_usd"] = Q.sales_krw / Q.usdkrw_avg * 1000; Q["book_to_bill"] = Q.orders_usd / Q.sales_usd
Q["opening_backlog"] = [np.nan, 6155, 6550, 6983, 6731, 7888]; Q.loc[0, "opening_backlog"] = 6731 - 0  # FY24 end backlog 5,541 is the Q1'25 opening
Q.loc[0, "opening_backlog"] = 5541
Q["conversion_q"] = Q.sales_usd / Q.opening_backlog
Q["backlog_identity_gap"] = Q.opening_backlog + Q.orders_usd - Q.sales_usd - Q.backlog_usd   # FX revaluation and cancellations [inference]
Q["opm"] = Q.op / Q.sales_krw; Q["na_sales_usd"] = Q.na_sales_krw / Q.usdkrw_avg * 1000; Q["na_book_to_bill"] = Q.na_orders / Q.na_sales_usd
A = pd.DataFrame({"fy": [2023, 2024, 2025], "sales_krw": [2702.8, 3322.3, 4079.5], "orders_usd": [3564, 3816, 4274], "end_backlog": [4302, 5541, 6731], "open_backlog": [np.nan, 4302, 5541]})
A["usdkrw"] = [k.loc[str(y)].mean() for y in A.fy]; A["sales_usd"] = A.sales_krw / A.usdkrw * 1000; A["conversion"] = A.sales_usd / A.open_backlog
A["orders_growth"] = A.orders_usd.pct_change(); A["sales_usd_growth"] = A.sales_usd.pct_change(); A["backlog_years"] = A.end_backlog / A.sales_usd
# 2026 and 2027 [inference]: H2'26 orders = guide 5,185 less 1H 3,237; H2'26 sales = guide 4,350 less 1H 2,178.3 at Q3 average FX (guidance and 1H actuals [company filing])
h2_orders = 5185 - 3237; h2_sales_usd = (4350 - (1036.5 + 1141.8)) / fxp["avg Q3'26"] * 1000
bl_end26 = 8490 + h2_orders - h2_sales_usd
sales26_usd = (1036.5 + 1141.8) / fxp["avg 1H26"] * 1000 + h2_sales_usd
conv_lo, conv_hi = 0.40, float(A.conversion.dropna().iloc[-1])      # low end [inference, illustrative]; high = latest full-year conversion
proj = []
for conv in (conv_lo, sales26_usd / 6731, conv_hi):
    for fxr in (fxp["spot (last)"], 1450.0):   # 1450 = alternative FX case [inference, illustrative]
        s27 = conv * bl_end26
        proj.append(dict(item="2027 sales from backlog", conversion=conv, usdkrw=fxr, end26_backlog_usd=bl_end26, sales27_usd=s27, sales27_krw=s27 * fxr / 1000,
                         growth_vs_2026_guide=s27 * fxr / 1000 / 4350 - 1, vs_valueup_target_4740=s27 * fxr / 1000 / 4740 - 1))
proj = pd.DataFrame(proj)
out_a = pd.concat([Q.assign(table="quarterly"), A.assign(table="annual"), proj.assign(table="2027 projection"),
                   pd.DataFrame([dict(table="2026 identity", item="sales26_usd", sales_usd=sales26_usd), dict(table="2026 identity", item="conversion implied by 2026 guide", conversion=sales26_usd / 6731),
                                 dict(table="2026 identity", item="end-2026 backlog USD m", end26_backlog_usd=bl_end26)])])
out_a.to_csv(TABLES / "hde_backlog_conversion.csv", index=False)

# ---------------- (b) PPI vs margins
ppi = fred("PCU335311335311", "PCU335311335311"); ppq = ppi.resample("QE").mean(); ppy = np.log(ppq).diff(4)
q = quarterly(); q = q.loc["2017-12-31":]
q["gm"] = 1 - q.cogsq / q.saleq; q["opm"] = q.oiadpq / q.saleq; q["d_gm_yoy"] = q.gm.diff(4); q["d_opm_yoy"] = q.opm.diff(4)
rows = []
for dep in ["gm", "opm", "d_opm_yoy"]:
    for lag in range(0, 7):
        dfx = pd.DataFrame({"y": q[dep], "x": ppy.shift(lag).reindex(q.index)}).dropna()
        if len(dfx) < 12: continue
        m = sm.OLS(dfx.y, sm.add_constant(dfx.x)).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        rows.append(dict(test="HDE quarterly", dependent=dep, regressor=f"PPI log y/y, lag {lag}q", beta=m.params["x"], t_hac4=m.tvalues["x"], r2=m.rsquared, n=int(m.nobs),
                         sample=f"{dfx.index.min().date()} to {dfx.index.max().date()}"))
# annual peer panel
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False); a["gvkey"] = a.gvkey.str.zfill(6)
a = a[(a.indfmt == "INDL") & a.gvkey.isin(PEERS) & (a.fyear >= 2000)].sort_values(["gvkey", "fyear"]).drop_duplicates(["gvkey", "fyear"], keep="last")
a["m"] = a.oibdp / a.sale; a["dm"] = a.groupby("gvkey").m.diff(); a["eb_g"] = np.log(a.oibdp / a.groupby("gvkey").oibdp.shift(1))
a["m_l3"] = a.groupby("gvkey").m.shift(3); a["dm3"] = a.m - a.m_l3
ppa = np.log(ppi.resample("YE").mean()).diff(); ppa.index = ppa.index.year
a["ppi"] = a.fyear.map(ppa); a["ppi_l1"] = a.fyear.map(ppa.shift(1))
for lab, s in [("19 grid names", a), ("Korean 5 incl. HDE", a[a.gvkey.isin([g for g, v in PEERS.items() if v[1] in ("korea", "case")])])]:
    s = s.dropna(subset=["dm", "ppi", "ppi_l1"]); s = s[s.dm.abs() < 0.3]
    X = sm.add_constant(pd.concat([s[["ppi", "ppi_l1"]], pd.get_dummies(s.gvkey, drop_first=True, dtype=float)], axis=1))
    my = sm.OLS(s.dm, X).fit(cov_type="cluster", cov_kwds={"groups": s.fyear})
    for x in ["ppi", "ppi_l1"]:
        rows.append(dict(test="annual panel, EBITDA margin change, firm FE", dependent="d EBITDA margin", regressor=x, beta=my.params[x], t_year_cl=my.tvalues[x], r2=my.rsquared, n=int(my.nobs), sample=lab))
ppi_tab = pd.DataFrame(rows)
recent = ppi.loc["2024-09":]; ppi_tab = pd.concat([ppi_tab, pd.DataFrame([dict(test="PPI level", dependent="PCU335311335311", regressor=str(d.date()), beta=v) for d, v in recent.items()]),
                                                  pd.DataFrame([dict(test="PPI y/y", dependent="latest", regressor=str(ppi.index[-1].date()), beta=ppi.iloc[-1] / ppi.iloc[-13] - 1),
                                                                dict(test="PPI y/y", dependent="peak 2022 to 2026", regressor=str((ppi / ppi.shift(12) - 1).loc["2021":].idxmax().date()), beta=(ppi / ppi.shift(12) - 1).loc["2021":].max())])])
ppi_tab.to_csv(TABLES / "hde_ppi_margin.csv", index=False)

# ---------------- (c) base rates
a["grp"] = a.gvkey.map(lambda g: PEERS[g][1]); a["yr_med"] = a.groupby("fyear").eb_g.transform("median"); a["dev"] = a.eb_g - a.yr_med
g = a.dropna(subset=["eb_g"]); g = g[np.isfinite(g.eb_g) & (g.oibdp > 0) & (g.groupby("gvkey").oibdp.shift(1) > 0)]
br = []
for lab, s in [("19 grid names FY2015-25", g), ("ex HDE", g[g.gvkey != HDE]), ("Korean 4 peers + HDE", g[g.grp.isin(["korea", "case"])]),
               ("after 3y margin expansion >= 5 pts", g[g.groupby("gvkey").dm3.shift(1).reindex(g.index) >= 0.05]),
               ("after 3y margin expansion >= 10 pts", g[g.groupby("gvkey").dm3.shift(1).reindex(g.index) >= 0.10])]:
    e = np.exp(s.eb_g) - 1; dv = s.dev.dropna()
    br.append(dict(sample=lab, firm_years=len(s), share_down=float((e < 0).mean()), down_gt10=float((e < -0.10).mean()), down_gt20=float((e < -0.20).mean()), down_gt30=float((e < -0.30).mean()),
                   p10=float(e.quantile(0.10)), median=float(e.median()), dev_sd=float(dv.std()), dev_iqr_sd=float((dv.quantile(0.75) - dv.quantile(0.25)) / 1.349), dev_p10=float(dv.quantile(0.10))))
# margin falls within 3 years after a >= 10 pt 3y expansion: max relative margin fall over the next 3 years
mrows = []
for gv, s in a.groupby("gvkey"):
    s = s.assign(fyear=s.fyear.astype(int)).set_index("fyear")
    for y in s.index:
        if y + 3 > 2025 or pd.isna(s.loc[y, "dm3"]) or s.loc[y, "dm3"] < 0.05: continue
        fut = s.m.reindex(range(y + 1, y + 4)).dropna()
        if len(fut) < 3 or s.loc[y, "m"] <= 0: continue
        mrows.append(dict(name=NAME[gv], peak_year=y, margin=s.loc[y, "m"], dm3=s.loc[y, "dm3"], worst_rel_fall_3y=fut.min() / s.loc[y, "m"] - 1))
mr = pd.DataFrame(mrows)
if len(mr):
    br.append(dict(sample="relative margin fall within 3y after >= 5 pt 3y expansion (episodes)", firm_years=len(mr), share_down=float((mr.worst_rel_fall_3y < 0).mean()),
                   down_gt10=float((mr.worst_rel_fall_3y < -0.10).mean()), down_gt20=float((mr.worst_rel_fall_3y < -0.20).mean()), down_gt30=float((mr.worst_rel_fall_3y < -0.30).mean()),
                   p10=float(mr.worst_rel_fall_3y.quantile(0.10)), median=float(mr.worst_rel_fall_3y.median())))
hde = a[a.gvkey == HDE][["fyear", "sale", "oibdp", "m"]].rename(columns={"m": "ebitda_margin"})
br = pd.DataFrame(br)
out_c = pd.concat([br.assign(table="base rates"), mr.assign(table="margin episodes"), hde.assign(table="HDE own history (KRW m)")])
out_c.to_csv(TABLES / "hde_ebitda_base_rates.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 60)
print(pd.Series(fxp).to_string()); print(Q.round(3).to_string()); print(A.round(3).to_string()); print(proj.round(3).to_string())
print("h2 orders", h2_orders, "h2 sales usd", round(h2_sales_usd), "end26 backlog", round(bl_end26), "sales26 usd", round(sales26_usd))
print(ppi_tab.round(3).to_string()); print(br.round(3).to_string()); print(mr.round(3).to_string()); print(hde.to_string())
