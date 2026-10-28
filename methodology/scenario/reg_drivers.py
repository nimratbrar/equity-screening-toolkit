"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Analysis 3: driver sensitivities from fundamentals (annual; Compustat quarterly items are empty for the Japanese names).
Per case: log revenue growth and EBITDA-margin change on the relevant external driver (contemporaneous and one-year lag).
Pooled: group panel with firm fixed effects (within transformation), firm-clustered SE.
Also: weekly stock returns of the three Japanese cases on changes in the Polymarket Taiwan-invasion price (Mar to Oct 2026).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/reg_drivers.py
Outputs: tables/driver_sensitivities.csv, tables/driver_panel_pooled.csv, tables/taiwan_market_weekly.csv
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from reg_common import universe_core, tri_wide, indices, copper_monthly, ecb_rate_daily, semis_series, DATA, TABLES, CASES, ASOF

core = universe_core()
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False)
a = a[(a.indfmt == "INDL") & a.gvkey.isin(core.gvkey)].copy(); a["datadate"] = pd.to_datetime(a.datadate)
a = a.sort_values(["gvkey", "fyear"]).drop_duplicates(["gvkey", "fyear"], keep="last")
g = a.groupby("gvkey")
a["sale_l1"], a["oibdp_l1"], a["curcd_l1"], a["fy_l1"] = g.sale.shift(1), g.oibdp.shift(1), g.curcd.shift(1), g.fyear.shift(1)
a = a[(a.curcd == a.curcd_l1) & (a.fyear - a.fy_l1 == 1) & (a.sale > 0) & (a.sale_l1 > 0)].copy()
a["rev_growth"] = np.log(a.sale / a.sale_l1)
a["margin"] = a.oibdp / a.sale; a["margin_l1"] = a.oibdp_l1 / a.sale_l1; a["dmargin"] = a.margin - a.margin_l1
a = a.merge(core[["gvkey", "group", "conm"]], on="gvkey")

# drivers as 12-month windows ending at each fiscal year end [source: WSTS, FRED copper PCOPPUSDM, FRED ECBDFR]
wsts = semis_series("WSTS_world_monthly_billings"); wsts.index = wsts.index + pd.offsets.MonthEnd(0)
wmem = semis_series("WSTS_memory_annual_billings")  # calendar years to 2025
cu = copper_monthly(); cu.index = cu.index + pd.offsets.MonthEnd(0)
ecb = ecb_rate_daily().resample("ME").mean()
def t12(s, end, how="sum"):
    w = s.loc[end - pd.DateOffset(months=12) + pd.Timedelta(days=1):end]
    return (w.sum() if how == "sum" else w.mean()) if len(w) >= 10 else np.nan
def driver_growth(s, end, how="sum", lag=0):
    e = (end + pd.offsets.MonthEnd(0)) - pd.DateOffset(years=lag)
    cur, prev = t12(s, e, how), t12(s, e - pd.DateOffset(years=1), how)
    return np.log(cur / prev) if cur > 0 and prev > 0 else np.nan
def ecb_change(end, lag=0):
    e = (end + pd.offsets.MonthEnd(0)) - pd.DateOffset(years=lag)
    return t12(ecb, e, "mean") - t12(ecb, e - pd.DateOffset(years=1), "mean")
def mem_growth(end, lag=0):  # calendar-year memory billings growth for the calendar year that ends closest before the FYE
    y = (end - pd.DateOffset(months=3)).year - lag   # March FYE -> prior calendar year
    try: return np.log(wmem[f"{y}-12-31"] / wmem[f"{y-1}-12-31"])
    except KeyError: return np.nan
for lag in (0, 1):
    a[f"wsts_g_l{lag}"] = [driver_growth(wsts, d, "sum", lag) for d in a.datadate]
    a[f"mem_g_l{lag}"] = [mem_growth(d, lag) for d in a.datadate]
    a[f"copper_g_l{lag}"] = [driver_growth(cu, d, "mean", lag) for d in a.datadate]
    a[f"ecb_d_l{lag}"] = [ecb_change(d, lag) for d in a.datadate]
DRIVERS = {"cable_grid": ["copper_g", "ecb_d"], "fab_water_facility": ["wsts_g", "mem_g"], "chip_materials_and_chem": ["wsts_g", "mem_g"]}
MEAN = {"wsts_g": "log change in trailing-12m WSTS world semiconductor billings", "mem_g": "log change in WSTS memory billings (calendar year before the FYE)",
        "copper_g": "log change in the trailing-12m average copper price (USD)", "ecb_d": "change in the trailing-12m average ECB deposit rate (pp)"}

def ols(y, X, cov="HC1", groups=None):
    X = sm.add_constant(X); 
    if groups is not None: return sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": groups})
    return sm.OLS(y, X).fit(cov_type=cov)

rows, prow = [], []
for gv, nm in CASES.items():
    grp = core.set_index("gvkey").loc[gv, "group"]
    for drv in DRIVERS[grp]:
        for dep in ["rev_growth", "dmargin"]:
            for spec in ["l0", "l0+l1"]:
                cols = [f"{drv}_l0"] if spec == "l0" else [f"{drv}_l0", f"{drv}_l1"]
                d = a[a.gvkey == gv].dropna(subset=cols + [dep])
                if len(d) < 6: continue
                m = ols(d[dep], d[cols])
                rows.append(dict(case=nm, dependent=dep, driver=drv, spec=spec, n_years=int(m.nobs), sample=f"FY{int(d.fyear.min())} to FY{int(d.fyear.max())}",
                                 beta_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], beta_l1=m.params[cols[1]] if len(cols) > 1 else np.nan, t_l1=m.tvalues[cols[1]] if len(cols) > 1 else np.nan,
                                 r2=m.rsquared, adj_r2=m.rsquared_adj, meaning=f"{dep} per unit {MEAN[drv]}", caveat="n about 10; HC1 t-stats; treat as indicative only"))
# pooled panels with firm fixed effects
for grp, drvs in DRIVERS.items():
    for drv in drvs:
        for dep in ["rev_growth", "dmargin"]:
            cols = [f"{drv}_l0", f"{drv}_l1"]
            d = a[a.group == grp].dropna(subset=cols + [dep]).copy()
            d = d[d.rev_growth.abs() < 1.0]  # drop firm-years with >2.7x or <0.37x revenue moves (restructurings)
            dm = d.copy()
            for c in cols + [dep]: dm[c] = dm[c] - dm.groupby("gvkey")[c].transform("mean")
            m = sm.OLS(dm[dep], dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dm.gvkey)[0]})
            prow.append(dict(group=grp, dependent=dep, driver=drv, n_firm_years=int(m.nobs), n_firms=d.gvkey.nunique(), sample=f"FY{int(d.fyear.min())} to FY{int(d.fyear.max())}",
                             beta_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], beta_l1=m.params[cols[1]], t_l1=m.tvalues[cols[1]], within_r2=m.rsquared, meaning=f"{dep} per unit {MEAN[drv]}, firm fixed effects, firm-clustered SE"))
pd.DataFrame(rows).to_csv(TABLES / "driver_sensitivities.csv", index=False)
pd.DataFrame(prow).to_csv(TABLES / "driver_panel_pooled.csv", index=False)

# Taiwan prediction market (weekly change in the Yes price, pp) vs weekly stock returns, TOPIX controlled
tri = tri_wide(); idx = indices()
pm = semis_series("Polymarket_China_invades_Taiwan_by_2027-12-31").resample("W-FRI").last()
trow = []
for gv, nm in CASES.items():
    if nm == "Nexans": continue
    d = pd.concat([np.log(tri[gv].resample("W-FRI").last()).diff().rename("ret"), np.log(idx["TOPIX"].resample("W-FRI").last()).diff().rename("mkt"), pm.diff().rename("d_taiwan_pp")], axis=1).dropna()
    m = ols(d.ret, d[["mkt", "d_taiwan_pp"]], cov="HAC") if False else sm.OLS(d.ret, sm.add_constant(d[["mkt", "d_taiwan_pp"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    trow.append(dict(case=nm, n_weeks=int(m.nobs), sample=f"{d.index[0].date()} to {d.index[-1].date()}", beta_per_pp=m.params["d_taiwan_pp"], t_hac=m.tvalues["d_taiwan_pp"], beta_mkt=m.params["mkt"], r2=m.rsquared,
                     meaning="weekly stock return per 1pp rise in the Polymarket invade-by-2027 Yes price, after TOPIX [source: Polymarket via semis_series.csv; WRDS data]"))
pd.DataFrame(trow).to_csv(TABLES / "taiwan_market_weekly.csv", index=False)
print(pd.DataFrame(rows).round(3).to_string()); print(pd.DataFrame(prow).round(3).to_string()); print(pd.DataFrame(trow).round(4).to_string())

# ======================= v2 (after the red-stats audit): year-clustered SE and sub-period stability =======================
v2 = []
for grp, drvs in DRIVERS.items():
    for drv in drvs:
        cols = [f"{drv}_l0", f"{drv}_l1"]
        d = a[a.group == grp].dropna(subset=cols + ["rev_growth"]).copy(); d = d[d.rev_growth.abs() < 1.0]
        def within(x):
            x = x.copy()
            for c in cols + ["rev_growth"]: x[c] = x[c] - x.groupby("gvkey")[c].transform("mean")
            return x
        dm = within(d)
        mf = sm.OLS(dm.rev_growth, dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dm.gvkey)[0]})
        my = sm.OLS(dm.rev_growth, dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": dm.fyear.astype(int).values})
        subs = {}
        for lab, s in (("FY15_19", d[d.fyear <= 2019]), ("FY20_25", d[d.fyear >= 2020])):
            ms = sm.OLS(within(s).rev_growth, within(s)[cols]).fit(); subs[lab] = (ms.params[cols[0]], ms.params[cols[1]])
        v2.append(dict(group=grp, driver=drv, n_firm_years=int(mf.nobs), n_years=d.fyear.nunique(), beta_l0=mf.params[cols[0]], t_firm_cl_l0=mf.tvalues[cols[0]], t_year_cl_l0=my.tvalues[cols[0]],
                       beta_l1=mf.params[cols[1]], t_firm_cl_l1=mf.tvalues[cols[1]], t_year_cl_l1=my.tvalues[cols[1]], b_l0_FY15_19=subs["FY15_19"][0], b_l0_FY20_25=subs["FY20_25"][0], b_l1_FY15_19=subs["FY15_19"][1], b_l1_FY20_25=subs["FY20_25"][1],
                       verdict="year-clustered t is the honest one: the driver is common to all firms in a year, so there are only about 11 independent observations"))
pd.DataFrame(v2).to_csv(TABLES / "driver_panel_pooled_v2.csv", index=False); print("== v2"); print(pd.DataFrame(v2).round(2).to_string())
