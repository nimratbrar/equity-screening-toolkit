"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Analysis 2: cross-section regression of log trailing EV/EBITDA on fundamentals, country and group dummies.
Core sample = the case-and-peer names; robustness = every company in the price file with matching fundamentals.
Forward EBITDA is not in the data layer (no I/B/E/S pull), so the multiple is trailing (latest FY, [WRDS data]).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/reg_multiples.py
Outputs: tables/multiples_inputs_core.csv, tables/multiples_coefs.csv, tables/multiples_case_residuals.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from reg_common import universe_core, fx, to_usd_rate, DATA, CACHE, TABLES, CASES

core = universe_core(); fxw = fx()
uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False)
a = a[(a.indfmt == "INDL")].copy(); a["gvkey"] = a.gvkey.str.zfill(6)
a = a.sort_values(["gvkey", "fyear"])
a["sale_l3"] = a.groupby("gvkey").sale.shift(3); a["fyear_l3"] = a.groupby("gvkey").fyear.shift(3)
last = a[a.fyear >= 2024].groupby("gvkey").tail(1).set_index("gvkey")
lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}).set_index("gvkey")
fy = pd.read_csv(CACHE / "price_at_fye.csv", dtype={"gvkey": str}).set_index("gvkey")
d = last.join(lp[["price", "ajexdi", "curcdd", "datadate"]].rename(columns={"datadate": "price_date"}), how="inner").join(fy, how="inner")
d = d[d.curcd == d.curcdd]   # price and accounts in the same currency
d["usd"] = [to_usd_rate(c, fxw) for c in d.curcd]
d["shares_now"] = d.csho * d.ajexdi_fye / d.ajexdi   # carries FYE shares through later splits (Organo 5-for-1 on 2026-10-01)
d["mcap_loc"] = d.price * d.shares_now
d["mcap_usd_mm"] = d.mcap_loc * d.usd
d["net_debt"] = d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0)
d["ev"] = d.mcap_loc + d.net_debt + d.pstk.fillna(0) + d.mib.fillna(0)
d["ev_ebitda"] = d.ev / d.oibdp
d["ebitda_margin"] = d.oibdp / d.sale
d["nd_ebitda"] = d.net_debt / d.oibdp
d["rev_cagr3"] = (d.sale / d.sale_l3) ** (1 / 3) - 1
tax = (d.txt / d.pi).where((d.pi > 0) & (d.txt >= 0)).clip(0, 0.35).fillna(0.25)
ic = d.seq.fillna(d.ceq) + d.mib.fillna(0) + d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0)
d["roic"] = d.oiadp * (1 - tax) / ic.where(ic > 0)
d["log_mcap_usd"] = np.log(d.mcap_usd_mm)
d["log_ev_ebitda"] = np.log(d.ev_ebitda)
d = d.join(uni.set_index("gvkey")[["loc", "gsubind"]], rsuffix="_u")
d["loc"] = d["loc"] if "loc" in d.columns else d["loc_u"]
EURO = {"FRA", "ITA", "DNK", "FIN", "DEU", "NLD", "ESP", "BEL", "AUT", "IRL", "PRT", "SWE", "NOR", "CHE"}
def ctry(l): return "JPN" if l == "JPN" else "KOR" if l == "KOR" else "USA" if l in ("USA", "GBR") else "EUR" if l in EURO else "TWN" if l == "TWN" else "CHN" if l in ("CHN", "HKG") else "OTH"
d["ctry"] = d["loc"].map(ctry)   # Pentair (GBR domicile, NYSE, USD accounts) is grouped with USA [inference]
d["ind2"] = d.gsubind.astype(str).str[:2]; d["ind4"] = d.gsubind.astype(str).str[:4]

def clean(x):
    x = x.replace([np.inf, -np.inf], np.nan)
    x = x[(x.oibdp > 0) & (x.ev > 0) & (x.ev_ebitda > 1) & (x.ev_ebitda < 100) & (x.sale > 0)]
    return x.dropna(subset=["log_ev_ebitda", "roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"])

def fit(x, dummies, label, winsor=False):
    X = x[["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"]].copy()
    if winsor:
        for c in ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]: X[c] = X[c].clip(X[c].quantile(0.01), X[c].quantile(0.99))
    for dcol, base in dummies:
        D = pd.get_dummies(x[dcol], prefix=dcol, dtype=float).drop(columns=[f"{dcol}_{base}"], errors="ignore"); X = pd.concat([X, D], axis=1)
    X = sm.add_constant(X)
    m = sm.OLS(x.log_ev_ebitda, X).fit(cov_type="HC1")
    coefs = pd.DataFrame({"model": label, "regressor": m.params.index, "coef": m.params.values, "t_hc1": m.tvalues.values, "n": int(m.nobs), "r2": m.rsquared, "adj_r2": m.rsquared_adj})
    return m, X, coefs

# core (case and peer names)
c = d.loc[d.index.intersection(core.gvkey)].join(core.set_index("gvkey")[["group", "conm", "case"]], rsuffix="_c")
c = clean(c)
c[["conm", "group", "ctry", "curcd", "fyear", "price_date", "mcap_usd_mm", "ev_ebitda", "roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]].round(3).to_csv(TABLES / "multiples_inputs_core.csv")
m1, X1, k1 = fit(c, [("ctry", "TWN"), ("group", "cable_grid")], "core40_country_group")
m2, X2, k2 = fit(c, [("group", "cable_grid")], "core40_group_only")
# broad universe robustness
b = clean(d[d.mcap_usd_mm >= 1000].copy())
m3, X3, k3 = fit(b, [("ctry", "OTH"), ("ind4", "2010")], "broad_country_industrygroup", winsor=True)
# broad, same three industry groups as the peers only (2010 capital goods, 1510 materials, 4530 semis equipment, 2020 commercial services)
b2 = b[b.ind4.isin(sorted(core.gsubind.astype(str).str[:4].unique()))]
m4, X4, k4 = fit(b2, [("ctry", "OTH"), ("ind4", "2010")], "broad_peer_industries_only", winsor=True)
pd.concat([k1, k2, k3, k4]).to_csv(TABLES / "multiples_coefs.csv", index=False)

rows = []
for gv, nm in CASES.items():
    for lab, m, X in [("core40_country_group", m1, X1), ("core40_group_only", m2, X2), ("broad_country_industrygroup", m3, X3), ("broad_peer_industries_only", m4, X4)]:
        if gv in X.index:
            fitted = float(np.exp(m.predict(X.loc[[gv]])).iloc[0]); actual = float(d.loc[gv, "ev_ebitda"])
            rows.append(dict(case=nm, model=lab, actual_ev_ebitda=actual, fitted_ev_ebitda=fitted, residual_log=np.log(actual / fitted), pct_vs_fitted=actual / fitted - 1, resid_sd_model=float(np.sqrt(m.scale)), n=int(m.nobs)))
        else:
            rows.append(dict(case=nm, model=lab, actual_ev_ebitda=float(d.loc[gv, "ev_ebitda"]) if gv in d.index else np.nan, fitted_ev_ebitda=np.nan, residual_log=np.nan, pct_vs_fitted=np.nan, resid_sd_model=np.nan, n=int(m.nobs)))
res = pd.DataFrame(rows); res.to_csv(TABLES / "multiples_case_residuals.csv", index=False)
print(c[["conm", "group", "ctry", "fyear", "mcap_usd_mm", "ev_ebitda", "roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]].round(2).to_string())
print(pd.concat([k1, k2, k3, k4]).round(3).to_string()); print(res.round(3).to_string())
print("broad n", len(b), "peer-industry n", len(b2), b2.ind4.value_counts().to_dict())

# ======================= v2 (after the red-stats audit) =======================
# Nexans on company-defined EBITDA and pro forma balance sheet; robust-fit range for the Japan coefficient; reversion slope.
design_cols = list(X4.columns)
def pred(m, xrow): return float(np.exp(m.predict(xrow[design_cols])).iloc[0])
g = "246217"; nx = d.loc[g]; v2 = []
for lab, mdl, X in [("core40_country_group", m1, X1), ("broad_peer_industries_only", m4, X4)]:
    cols_ = list(X.columns)
    f = lambda xr: float(np.exp(mdl.predict(xr[cols_])).iloc[0])
    xr = X.loc[[g]].copy(); act = float(nx.ev_ebitda); v2.append(dict(case="Nexans", basis="Compustat oibdp (latest FY)", model=lab, actual=act, fitted=f(xr), pct_vs_fitted=act / f(xr) - 1))
    xr = X.loc[[g]].copy(); xr["ebitda_margin"] = 728 / 6098; xr["nd_ebitda"] = float(nx.net_debt) / 728; act = float(nx.ev) / 728   # [company filing: Nexans Universal Registration Document 2025, adj. EBITDA 728, sales at standard metal prices 6,098]
    v2.append(dict(case="Nexans", basis="company adj. EBITDA 728, std-metal sales 6,098", model=lab, actual=act, fitted=f(xr), pct_vs_fitted=act / f(xr) - 1))
    xr = X.loc[[g]].copy(); xr["ebitda_margin"] = 728 / 6098; xr["nd_ebitda"] = (1038 + 153) / 728; act = (float(nx.mcap_loc) + 1038 + 153) / (728 + 27.5)   # [company filing: Nexans H1 2026 results, net debt 1,038 incl. leases, pensions 153; acquisition press release, Republic Wire EBITDA 27.5]
    v2.append(dict(case="Nexans", basis="pro forma: Jun-26 net debt 1,038 + pensions 153; EBITDA 728 + 27.5 Republic Wire", model=lab, actual=act, fitted=f(xr), pct_vs_fitted=act / f(xr) - 1))
for gv, nm in CASES.items():
    if nm == "Nexans": continue
    for lab, mdl, X in [("core40_country_group", m1, X1), ("broad_peer_industries_only", m4, X4)]:
        cols_ = list(X.columns); act = float(d.loc[gv, "ev_ebitda"]); fit_ = float(np.exp(mdl.predict(X.loc[[gv], cols_])).iloc[0])
        v2.append(dict(case=nm, basis="Compustat oibdp (FY to Mar-2026)", model=lab, actual=act, fitted=fit_, pct_vs_fitted=act / fit_ - 1))
pd.DataFrame(v2).to_csv(TABLES / "multiples_case_residuals_v2.csv", index=False)
# robust variants on the broad peer-industry sample: Japan coefficient range and case residuals
rob = []
yb, Xb = b2.log_ev_ebitda, X4
fits = {"OLS": sm.OLS(yb, Xb).fit(), "Huber": sm.RLM(yb, Xb, M=sm.robust.norms.HuberT()).fit(), "median": sm.QuantReg(yb, Xb).fit(q=0.5, max_iter=5000)}
trim = b2[(b2.ev_ebitda >= 4) & (b2.ev_ebitda <= 40)]; fits["OLS 4x to 40x"] = sm.OLS(trim.log_ev_ebitda, Xb.loc[trim.index]).fit()
infl = fits["OLS"].get_influence(); keep = (pd.Series(infl.cooks_distance[0], index=Xb.index) <= 4 / len(yb)) | Xb.index.isin(CASES)
fits["OLS drop Cook's D > 4/n"] = sm.OLS(yb[keep], Xb[keep]).fit()
for lab, mdl in fits.items():
    row = dict(spec=lab, n=int(mdl.nobs), jpn_coef=mdl.params["ctry_JPN"], jpn_discount_pct=1 - np.exp(mdl.params["ctry_JPN"]))
    for gv, nm in CASES.items():
        act = float(d.loc[gv, "ev_ebitda"]); row[f"{nm}_pct_vs_fitted"] = act / float(np.exp(mdl.predict(Xb.loc[[gv]])).iloc[0]) - 1
    rob.append(row)
pd.DataFrame(rob).to_csv(TABLES / "multiples_robust_v2.csv", index=False)
# reversion: does the FY2024 residual (price 2025-10-16) predict the 12m change in log EV/EBITDA? Uses the auditor's price cache if present.
pc = CACHE / "audit_price_20251016.csv"; rev = []
if pc.exists():
    p25 = pd.read_csv(pc, dtype={"gvkey": str}).set_index("gvkey").drop(columns=["datadate"])
    d0 = a[a.fyear == 2024].groupby("gvkey").tail(1).set_index("gvkey").join(p25, how="inner"); d0 = d0[d0.curcd == d0.curcdd]
    d0 = d0.join(d[["csho", "ajexdi_fye", "ctry", "ind4"]].rename(columns={"csho": "csho25", "ajexdi_fye": "aj25"}), how="inner")
    d0["mcap_loc"] = d0.price * d0.csho25 * d0.aj25 / d0.ajexdi; d0["usd"] = [to_usd_rate(c, fxw, pd.Timestamp("2025-10-16")) for c in d0.curcd]; d0["mcap_usd_mm"] = d0.mcap_loc * d0.usd
    d0["net_debt"] = d0.dltt.fillna(0) + d0.dlc.fillna(0) - d0.che.fillna(0); d0["ev"] = d0.mcap_loc + d0.net_debt + d0.pstk.fillna(0) + d0.mib.fillna(0); d0["ev_ebitda"] = d0.ev / d0.oibdp
    d0["ebitda_margin"] = d0.oibdp / d0.sale; d0["nd_ebitda"] = d0.net_debt / d0.oibdp; d0["rev_cagr3"] = (d0.sale / d0.sale_l3) ** (1 / 3) - 1
    tx = (d0.txt / d0.pi).where((d0.pi > 0) & (d0.txt >= 0)).clip(0, 0.35).fillna(0.25); ic0 = d0.seq.fillna(d0.ceq) + d0.mib.fillna(0) + d0.dltt.fillna(0) + d0.dlc.fillna(0) - d0.che.fillna(0)
    d0["roic"] = d0.oiadp * (1 - tx) / ic0.where(ic0 > 0); d0["log_mcap_usd"] = np.log(d0.mcap_usd_mm); d0["log_ev_ebitda"] = np.log(d0.ev_ebitda)
    d0 = clean(d0[d0.mcap_usd_mm >= 1000]); d0 = d0[d0.ind4.isin(b2.ind4.unique())]
    m0, X0, _ = fit(d0, [("ctry", "OTH"), ("ind4", "2010")], "fy2024", winsor=True)
    both = m0.resid.index.intersection(b2.index)
    dy = (b2.loc[both, "log_ev_ebitda"] - d0.loc[both, "log_ev_ebitda"]); r0 = m0.resid.loc[both]
    rr = sm.OLS(dy, sm.add_constant(r0.rename("resid_t0"))).fit(cov_type="HC1")
    rev.append(dict(n=int(rr.nobs), slope=rr.params.resid_t0, t_hc1=rr.tvalues.resid_t0, r2=rr.rsquared, note="12m change in log trailing EV/EBITDA (FY2024 accounts at 2025-10-16 to FY2025 at 2026-10-16) on the FY2024 residual; includes EBITDA noise so an upper bound on price-driven reversion"))
pd.DataFrame(rev).to_csv(TABLES / "multiples_reversion_v2.csv", index=False)
print("== v2"); print(pd.DataFrame(v2).round(3).to_string()); print(pd.DataFrame(rob).round(3).to_string()); print(pd.DataFrame(rev).round(3).to_string())
