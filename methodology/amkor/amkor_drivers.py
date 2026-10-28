"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Amkor analysis 3: driver sensitivities and cycle base rates.
(a) OSAT panel (17 names, FY2014 to FY2025, local currency): log revenue growth on WSTS world billings growth (t0, t-1),
    firm fixed effects, firm- and year-clustered t, sub-period stability; Amkor alone on 2008 to 2025 (filings + WRDS sales).
(b) Smartphone units: the original run used annual unit figures recalled from IDC press releases [inference, unverified].
    This public copy ships an ILLUSTRATIVE placeholder series instead: replace it with verified annual units from a public
    or licensed source before running.
(c) EBITDA drop-through in down years (Amkor own, pooled OSAT), EBITDA-fall base rates (OSAT, broad GICS 4530),
    Amkor's own 12-month return distribution (for the simulation cross-check), and Amkor's historical multiple vs peers.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_drivers.py
Outputs: tables/amkr_driver_panel.csv, amkr_driver_amkor_own.csv, amkr_dropthrough.csv, amkr_ebitda_fall_baserates.csv,
         amkr_returns12m_hist.csv, amkr_multiple_history.csv. [WRDS data] unless labelled.
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from amkor_common import osat_set, tri_osat, prices_osat, TABLES, AMKR, DATA
from reg_common import semis_series
core = osat_set().set_index("gvkey")
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False); a["gvkey"] = a.gvkey.str.zfill(6)
uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = a[a.indfmt == "INDL"].sort_values(["gvkey", "fyear"]).drop_duplicates(["gvkey", "fyear"], keep="last").copy(); a["datadate"] = pd.to_datetime(a.datadate)
g = a.groupby("gvkey")
for c in ["sale", "oibdp", "curcd", "fyear"]: a[f"{c}_l1"] = g[c].shift(1)
a = a[(a.curcd == a.curcd_l1) & (a.fyear - a.fyear_l1 == 1)].copy()
a["rev_g"] = np.log(a.sale / a.sale_l1).where((a.sale > 0) & (a.sale_l1 > 0))
a["ebitda_g"] = np.log(a.oibdp / a.oibdp_l1).where((a.oibdp > 0) & (a.oibdp_l1 > 0)); a["ebitda_chg"] = a.oibdp / a.oibdp_l1 - 1
a["margin"] = a.oibdp / a.sale; a["dmargin"] = a.margin - a.oibdp_l1 / a.sale_l1
# WSTS trailing-12m billings growth at each FYE (handles June FYEs), lags 0 and 1 [source: WSTS via semis_series.csv]
wsts = semis_series("WSTS_world_monthly_billings"); wsts.index = wsts.index + pd.offsets.MonthEnd(0)
def t12(s, end): w = s.loc[end - pd.DateOffset(months=12) + pd.Timedelta(days=1):end]; return w.sum() if len(w) >= 10 else np.nan
def wg(end, lag):
    e = (end + pd.offsets.MonthEnd(0)) - pd.DateOffset(years=lag); c, p = t12(wsts, e), t12(wsts, e - pd.DateOffset(years=1))
    return np.log(c / p) if c > 0 and p > 0 else np.nan
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or a verified public source.
# Smartphone units, million, by calendar year [placeholder: annual global smartphone shipments; values below are made up]
PHONES_RECALLED = {2012: 800, 2013: 950, 2014: 1100, 2015: 1200, 2016: 1250, 2017: 1250, 2018: 1200, 2019: 1180, 2020: 1100, 2021: 1150, 2022: 1050, 2023: 1020, 2024: 1080, 2025: 1100}
# ===== END PLACEHOLDER INPUTS =====
ph = pd.Series(PHONES_RECALLED); phg = np.log(ph / ph.shift(1))
def pg(end, lag): y = (end - pd.DateOffset(months=6)).year - lag; return float(phg.get(y, np.nan))   # June FYE maps to the prior calendar year
p = a[a.gvkey.isin(core.index)].copy()
for lag in (0, 1):
    p[f"wsts_l{lag}"] = [wg(d, lag) for d in p.datadate]; p[f"phone_l{lag}"] = [pg(d, lag) for d in p.datadate]
p = p[p.rev_g.abs() < 1.0]
def within(x, cols):
    x = x.copy()
    for c in cols: x[c] = x[c] - x.groupby("gvkey")[c].transform("mean")
    return x
rows = []
for drv, lab in [("wsts", "WSTS world billings, trailing-12m growth [source: WSTS]"), ("phone", "Smartphone units growth [placeholder series: replace with verified data]")]:
    for dep in ["rev_g", "dmargin"]:
        cols = [f"{drv}_l0", f"{drv}_l1"]; d = p.dropna(subset=cols + [dep]); dm = within(d, cols + [dep])
        mf = sm.OLS(dm[dep], dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": pd.factorize(dm.gvkey)[0]})
        my = sm.OLS(dm[dep], dm[cols]).fit(cov_type="cluster", cov_kwds={"groups": dm.fyear.astype(int).values})
        subs = {}
        for sl, s in (("FY15_19", d[d.fyear <= 2019]), ("FY20_25", d[d.fyear >= 2020])):
            sd_ = within(s, cols + [dep]); ms = sm.OLS(sd_[dep], sd_[cols]).fit(); subs[sl] = (ms.params[cols[0]], ms.params[cols[1]])
        # pooled excluding Amkor (so Amkor's own fit below is independent)
        rows.append(dict(driver=lab, dependent=dep, n_firm_years=int(mf.nobs), n_firms=d.gvkey.nunique(), n_years=d.fyear.nunique(), sample=f"FY{int(d.fyear.min())} to FY{int(d.fyear.max())}",
                         beta_l0=mf.params[cols[0]], t_firm_cl_l0=mf.tvalues[cols[0]], t_year_cl_l0=my.tvalues[cols[0]], beta_l1=mf.params[cols[1]], t_firm_cl_l1=mf.tvalues[cols[1]], t_year_cl_l1=my.tvalues[cols[1]],
                         b_l0_FY15_19=subs["FY15_19"][0], b_l0_FY20_25=subs["FY20_25"][0], b_l1_FY15_19=subs["FY15_19"][1], b_l1_FY20_25=subs["FY20_25"][1], within_r2=mf.rsquared,
                         note="firm fixed effects; year-clustered t is the honest one (about 11 independent years)"))
panel = pd.DataFrame(rows); panel.to_csv(TABLES / "amkr_driver_panel.csv", index=False)
# Amkor alone, 2008 to 2025: sales from 10-K (2007 to 2013) and WRDS (2014 on) via data/external/osat_series.csv, which you build yourself [company filing; WRDS data]
os_ = pd.read_csv(DATA / "external/osat_series.csv"); am = os_[os_.series == "Amkor_annual_net_sales"].copy(); am["year"] = pd.to_datetime(am.date).dt.year
am = am.set_index("year").value.astype(float).sort_index(); amg = np.log(am / am.shift(1)).dropna()
wa = semis_series("WSTS_world_annual_billings"); wa.index = wa.index.year; wag = np.log(wa / wa.shift(1))
own = []
for drv, ser, lab in [("wsts", wag, "WSTS world annual billings growth [source: WSTS]"), ("phone", phg, "Smartphone units growth [placeholder series: replace with verified data]")]:
    d = pd.DataFrame({"rev_g": amg, "l0": ser.reindex(amg.index), "l1": ser.shift(1).reindex(amg.index)}).dropna()
    m0 = sm.OLS(d.rev_g, sm.add_constant(d[["l0"]])).fit(cov_type="HC1"); m1 = sm.OLS(d.rev_g, sm.add_constant(d[["l0", "l1"]])).fit(cov_type="HC1")
    own.append(dict(driver=lab, n_years=int(m1.nobs), sample=f"{int(d.index.min())} to {int(d.index.max())}", beta_l0_only=m0.params.l0, t_l0_only=m0.tvalues.l0, r2_l0_only=m0.rsquared,
                    beta_l0=m1.params.l0, t_l0=m1.tvalues.l0, beta_l1=m1.params.l1, t_l1=m1.tvalues.l1, r2=m1.rsquared, caveat="n about 17; HC1; indicative"))
own = pd.DataFrame(own); own.to_csv(TABLES / "amkr_driver_amkor_own.csv", index=False)

# (c) drop-through: EBITDA % change / sales % change in down years
dt = []
x = a[(a.gvkey == AMKR) & (a.sale < a.sale_l1)]
for r in x.itertuples(): dt.append(dict(sample="Amkor own [WRDS data]", fyear=int(r.fyear), sales_chg=r.sale / r.sale_l1 - 1, ebitda_chg=r.ebitda_chg, drop_through=r.ebitda_chg / (r.sale / r.sale_l1 - 1)))
pp = a[a.gvkey.isin(core.index) & (a.gvkey != AMKR) & (a.sale < a.sale_l1) & (a.oibdp_l1 > 0)].copy(); pp["dt"] = pp.ebitda_chg / (pp.sale / pp.sale_l1 - 1)
pp = pp[(pp.sale / pp.sale_l1 - 1) < -0.02]  # down years of more than 2% so the ratio is not dominated by tiny denominators
md = sm.OLS(pp.ebitda_g, sm.add_constant(pp.rev_g)).fit(cov_type="cluster", cov_kwds={"groups": pp.fyear.astype(int).values})
dt.append(dict(sample=f"OSAT peers ex Amkor, down years > 2% (n = {len(pp)} firm-years, {pp.gvkey.nunique()} firms)", fyear=np.nan, sales_chg=pp.eval("sale/sale_l1-1").median(), ebitda_chg=pp.ebitda_chg.median(),
               drop_through=pp.dt.median(), drop_through_p25=pp.dt.quantile(0.25), drop_through_p75=pp.dt.quantile(0.75), slope_log_ebitda_on_log_sales=md.params.rev_g, t_year_cl=md.tvalues.rev_g))
# all OSAT firm-years regression (up and down) for comparison
pa = a[a.gvkey.isin(core.index) & (a.oibdp_l1 > 0) & a.ebitda_g.notna() & (a.rev_g.abs() < 1)]; ma = sm.OLS(pa.ebitda_g, sm.add_constant(pa.rev_g)).fit(cov_type="cluster", cov_kwds={"groups": pa.fyear.astype(int).values})
dt.append(dict(sample=f"OSAT 17 names, all firm-years (n = {len(pa)})", fyear=np.nan, slope_log_ebitda_on_log_sales=ma.params.rev_g, t_year_cl=ma.tvalues.rev_g))
dt = pd.DataFrame(dt); dt.to_csv(TABLES / "amkr_dropthrough.csv", index=False)
# EBITDA-fall base rates
def falls(x, label):
    c = x.ebitda_chg
    return dict(label=label, n_firm_years=len(x), n_firms=x.gvkey.nunique(), sample=f"FY{int(x.fyear.min())} to FY{int(x.fyear.max())}", share_down=(c < 0).mean(), share_down_gt10=(c < -0.1).mean(), share_down_gt20=(c < -0.2).mean(),
                share_down_gt30=(c < -0.3).mean(), median_chg=c.median(), p10_chg=c.quantile(0.1), p25_chg=c.quantile(0.25), p10_vs_median=c.quantile(0.1) - c.median())
ff = a[(a.oibdp_l1 > 0) & a.ebitda_chg.notna()].merge(uni[["gvkey", "gsubind"]], on="gvkey", how="left"); ff["ind4"] = ff.gsubind.astype(str).str[:4]
br = [falls(ff[ff.gvkey == AMKR], "Amkor own"), falls(ff[ff.gvkey.isin(core.index)], "OSAT 17 names"), falls(ff[ff.gvkey.isin(core.index) & (ff.gvkey != AMKR)], "OSAT 16 peers ex Amkor"), falls(ff[ff.ind4 == "4530"], "broad GICS 4530 semis (price file)")]
br = pd.DataFrame(br); br.to_csv(TABLES / "amkr_ebitda_fall_baserates.csv", index=False)
# Amkor 12m log total returns, overlapping daily windows
tri = tri_osat(); s = tri[AMKR].dropna(); out = {}
for t in s.index[s.index >= s.index[0] + pd.Timedelta(days=365)]:
    base = s.loc[:t - pd.Timedelta(days=365)]; out[t] = np.log(s[t] / base.iloc[-1])
r = pd.Series(out); q = r.quantile([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
peers_r = []
for gk in core.index:
    if gk == AMKR: continue
    sp = tri[gk].dropna(); peers_r.append(pd.Series({t: np.log(sp[t] / sp.loc[:t - pd.Timedelta(days=365)].iloc[-1]) for t in sp.index[sp.index >= sp.index[0] + pd.Timedelta(days=365)]}))
pr = pd.concat(peers_r); qp = pr.quantile([0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95])
h = pd.DataFrame([dict(label="Amkor 12m log total return", n_obs=len(r), sample=f"{r.index[0].date()} to {r.index[-1].date()}", mean=r.mean(), sd=r.std(), p05=q[0.05], p10=q[0.1], p25=q[0.25], p50=q[0.5], p75=q[0.75], p90=q[0.9], p95=q[0.95], share_negative=(r < 0).mean(), share_below_m20=(r < np.log(0.8)).mean(), worst=r.min(), max_drawdown=float((s / s.cummax() - 1).min())),
                  dict(label="OSAT 16 peers pooled 12m log total return (local ccy)", n_obs=len(pr), sample="2021-10 to 2026-10", mean=pr.mean(), sd=pr.std(), p05=qp[0.05], p10=qp[0.1], p25=qp[0.25], p50=qp[0.5], p75=qp[0.75], p90=qp[0.9], p95=qp[0.95], share_negative=(pr < 0).mean(), share_below_m20=(pr < np.log(0.8)).mean(), worst=pr.min(), max_drawdown=np.nan)])
h.to_csv(TABLES / "amkr_returns12m_hist.csv", index=False)
# Amkor trailing EV/EBITDA at each FYE vs OSAT peer median, FY2020 to FY2025 (FYE close from the daily price cache, which starts 2020-10;
# Compustat Global has no prcc_f for the intl names). EV = FYE price x csho + debt - cash (local currency, so the ratio is currency-free).
px = prices_osat(); hm = a[a.gvkey.isin(core.index) & (a.oibdp > 0) & (a.fyear >= 2020)].copy()
def fye_px(gk, dte):
    s_ = px[(px.gvkey == gk) & (px.datadate <= dte) & (px.datadate >= dte - pd.Timedelta(days=10))]
    return float(s_.sort_values("datadate").price.iloc[-1]) if len(s_) else np.nan
hm["p_fye"] = [fye_px(gk, dte) for gk, dte in zip(hm.gvkey, hm.datadate)]
hm["ev"] = hm.p_fye * hm.csho + hm.dltt.fillna(0) + hm.dlc.fillna(0) - hm.che.fillna(0) + hm.pstk.fillna(0) + hm.mib.fillna(0); hm["evx"] = hm.ev / hm.oibdp
hm = hm[(hm.evx > 1) & (hm.evx < 100)]
mh = []
for y, grp in hm.groupby("fyear"):
    ak = grp[grp.gvkey == AMKR].evx; pm_ = grp[grp.gvkey != AMKR].evx
    if len(ak) and len(pm_): mh.append(dict(fyear=int(y), amkor_ev_ebitda=float(ak.iloc[0]), peer_median=pm_.median(), ase_ev_ebitda=float(grp[grp.gvkey == "213412"].evx.iloc[0]) if (grp.gvkey == "213412").any() else np.nan, n_peers=len(pm_), amkor_vs_peer_median_log=np.log(float(ak.iloc[0]) / pm_.median())))
mh = pd.DataFrame(mh); mh.to_csv(TABLES / "amkr_multiple_history.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 60)
print(panel.round(3).to_string()); print(own.round(3).to_string()); print(dt.round(3).to_string()); print(br.round(3).to_string()); print(h.round(3).to_string()); print(mh.round(2).to_string())
