"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-stats audit part 2: multiple-model robustness, Nexans on company EBITDA, historical reversion of residuals, driver-panel inference.
Run after audit_prep.py: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/audit_regs2.py   Writes tables/audit_*.csv only.
"""
import sys, runpy, io, contextlib, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
import statsmodels.formula.api as smf
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import reg_common as rc
SCR = HERE / "__pycache__" / "audit_tmp"; SCR.mkdir(parents=True, exist_ok=True); rc.TABLES = SCR   # re-used scripts write to scratch
OUT = HERE / "tables"
with contextlib.redirect_stdout(io.StringIO()):
    M = runpy.run_path(str(HERE / "reg_multiples.py"))
    G = runpy.run_path(str(HERE / "reg_drivers.py"))
d, b2, fit, CASES = M["d"], M["b2"], M["fit"], rc.CASES
REG = ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"]

def design(x, ref=None):
    X = x[REG].copy()
    q = ref if ref is not None else x
    for c in ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]: X[c] = X[c].clip(q[c].quantile(0.01), q[c].quantile(0.99))
    for col, base in (("ctry", "OTH"), ("ind4", "2010")):
        X = pd.concat([X, pd.get_dummies(x[col], prefix=col, dtype=float).drop(columns=[f"{col}_{base}"], errors="ignore")], axis=1)
    return sm.add_constant(X)
X = design(b2); y = b2.log_ev_ebitda
base = sm.OLS(y, X).fit(cov_type="HC1")
infl = sm.OLS(y, X).fit().get_influence()
stud = pd.Series(infl.resid_studentized_external, index=X.index); cook = pd.Series(infl.cooks_distance[0], index=X.index)
cases = [g for g in CASES if g in X.index]
rows = []
def record(label, m, Xm, n, over=None):
    for g in cases:
        xr = Xm.loc[[g]] if g in Xm.index else X.loc[[g]].reindex(columns=Xm.columns, fill_value=0.0)
        if over and g in over: xr = over[g][0].reindex(columns=Xm.columns, fill_value=0.0)
        act = over[g][1] if over and g in over else float(np.exp(y.loc[g]))
        fitted = float(np.exp(np.asarray(m.predict(xr))[0]))
        rows.append(dict(spec=label, case=CASES[g], actual=act, fitted=fitted, pct_vs_fitted=act / fitted - 1, resid_log=np.log(act / fitted), n=n,
                         jpn_coef=m.params.get("ctry_JPN", np.nan), resid_sd=float(np.sqrt(m.scale)) if hasattr(m, "scale") else np.nan,
                         resid_pctile=float((base.resid < np.log(act / fitted)).mean())))
record("reported: OLS broad peer industries", base, X, len(y))
keep = (stud.abs() <= 2.5) | X.index.isin(cases)
m = sm.OLS(y[keep], X[keep]).fit(); record("drop |studentised resid| > 2.5 (cases kept)", m, X[keep], int(keep.sum()))
keep2 = (cook <= 4 / len(y)) | X.index.isin(cases)
m = sm.OLS(y[keep2], X[keep2]).fit(); record("drop Cook's D > 4/n (cases kept)", m, X[keep2], int(keep2.sum()))
m = sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit(); record("Huber robust regression", m, X, len(y))
m = sm.QuantReg(y, X).fit(q=0.5, max_iter=5000); record("median (LAD) regression", m, X, len(y))
tr = (b2.ev_ebitda.between(4, 40)) | b2.index.isin(cases)
m = sm.OLS(y[tr], X[tr]).fit(); record("EV/EBITDA trimmed to 4x-40x", m, X[tr], int(tr.sum()))
# Nexans on company-defined EBITDA: FY2025 adj. EBITDA 728 and sales 6,098 at standard metal prices [company filing: Nexans Universal Registration Document 2025]
g = "246217"; nx = d.loc[g]
ev = float(nx.ev); act_adj = ev / 728.0
xr = X.loc[[g]].copy(); xr["ebitda_margin"] = 728.0 / 6098.0; xr["nd_ebitda"] = float(nx.net_debt) / 728.0
record("Nexans on adj. EBITDA 728 and std-metal sales 6,098", base, X, len(y), over={g: (xr, act_adj)})
xr2 = X.loc[[g]].copy(); xr2["nd_ebitda"] = (1038 + 153) / 728.0
ev_pf = float(nx.mcap_loc) + 1038 + 153     # June 2026 net debt incl. leases plus pensions [company filing: Nexans H1 2026 results]
record("Nexans pro forma: EV with Jun-2026 net debt 1,038 + pensions 153, adj. EBITDA 728 + Republic Wire 27.5", base, X, len(y), over={g: (xr2, ev_pf / (728 + 27.5))})
R = pd.DataFrame(rows); R.to_csv(OUT / "audit_multiples_robust.csv", index=False)
print(f"Nexans Compustat: EV {float(nx.ev):.0f}, oibdp {float(nx.oibdp):.0f}, sale {float(nx.sale):.0f}, mcap {float(nx.mcap_loc):.0f}, net debt {float(nx.net_debt):.0f}")
print(R.round(3).to_string())

# ---------- historical test of the mean-reversion rule: does the 2025-10-16 residual predict the 12m change in log EV/EBITDA? ----------
a = M["a"]; uni = M["uni"]
p25 = pd.read_csv(rc.CACHE / "audit_price_20251016.csv", dtype={"gvkey": str}).set_index("gvkey")
last24 = a[(a.fyear == 2024)].groupby("gvkey").tail(1).set_index("gvkey")
d0 = last24.join(p25.rename(columns={"datadate": "pdate"}), how="inner")
d0 = d0[d0.curcd == d0.curcdd]
d0 = d0.join(d[["csho", "ajexdi_fye"]].rename(columns={"csho": "csho25", "ajexdi_fye": "aj25"}), how="inner")
d0["shares"] = d0.csho25 * d0.aj25 / d0.ajexdi                   # FY2025 share count on the 2025-10-16 basis [inference: ignores buybacks within the year]
d0["mcap_loc"] = d0.price * d0.shares; d0["usd"] = [rc.to_usd_rate(c, rc.fx(), pd.Timestamp("2025-10-16")) for c in d0.curcd]
d0["mcap_usd_mm"] = d0.mcap_loc * d0.usd
d0["net_debt"] = d0.dltt.fillna(0) + d0.dlc.fillna(0) - d0.che.fillna(0)
d0["ev"] = d0.mcap_loc + d0.net_debt + d0.pstk.fillna(0) + d0.mib.fillna(0); d0["ev_ebitda"] = d0.ev / d0.oibdp
d0["ebitda_margin"] = d0.oibdp / d0.sale; d0["nd_ebitda"] = d0.net_debt / d0.oibdp; d0["rev_cagr3"] = (d0.sale / d0.sale_l3) ** (1 / 3) - 1
tax = (d0.txt / d0.pi).where((d0.pi > 0) & (d0.txt >= 0)).clip(0, 0.35).fillna(0.25)
ic = d0.seq.fillna(d0.ceq) + d0.mib.fillna(0) + d0.dltt.fillna(0) + d0.dlc.fillna(0) - d0.che.fillna(0)
d0["roic"] = d0.oiadp * (1 - tax) / ic.where(ic > 0); d0["log_mcap_usd"] = np.log(d0.mcap_usd_mm); d0["log_ev_ebitda"] = np.log(d0.ev_ebitda)
d0 = d0.join(d[["ctry", "ind4"]], how="inner")
d0 = M["clean"](d0[d0.mcap_usd_mm >= 1000]); d0 = d0[d0.ind4.isin(b2.ind4.unique())]
X0 = design(d0); m0 = sm.OLS(d0.log_ev_ebitda, X0).fit(); res0 = m0.resid
both = res0.index.intersection(b2.index)
dl = (b2.log_ev_ebitda - d0.log_ev_ebitda).loc[both]
rv = []
for lab, mask in (("all", np.ones(len(both), bool)), ("|resid| < 1", res0.loc[both].abs().values < 1)):
    r = sm.OLS(dl[mask], sm.add_constant(res0.loc[both][mask].rename("resid_t0"))).fit(cov_type="HC1")
    rv.append(dict(sample=lab, n=int(r.nobs), slope=r.params["resid_t0"], t=r.tvalues["resid_t0"], implied_f=-r.params["resid_t0"], r2=r.rsquared,
                   note="12m change in log trailing EV/EBITDA (FY2024 accounts at 2025-10-16 to FY2025 at 2026-10-16) on the 2025 residual; includes EBITDA noise, so an upper bound on price-driven reversion"))
pd.DataFrame(rv).to_csv(OUT / "audit_multiple_reversion.csv", index=False); print(pd.DataFrame(rv).round(3).to_string())
for g in cases: print(CASES[g], "resid 2025:", round(float(res0.get(g, np.nan)), 3), "resid 2026:", round(float(base.resid.get(g, np.nan)), 3))

# ---------- driver panels: clustering by year, time-aggregated, sub-periods, lag 2, leave-one-year-out ----------
A = G["a"]; DRIVERS = G["DRIVERS"]
for lag in (2,):
    A[f"wsts_g_l{lag}"] = [G["driver_growth"](G["wsts"], dd, "sum", lag) for dd in A.datadate]
    A[f"copper_g_l{lag}"] = [G["driver_growth"](G["cu"], dd, "mean", lag) for dd in A.datadate]
    A[f"mem_g_l{lag}"] = [G["mem_growth"](dd, lag) for dd in A.datadate]
    A[f"ecb_d_l{lag}"] = [G["ecb_change"](dd, lag) for dd in A.datadate]
out = []
def within(dd, cols, dep):
    dm = dd.copy()
    for c in cols + [dep]: dm[c] = dm[c] - dm.groupby("gvkey")[c].transform("mean")
    return dm
for grp, drv in (("cable_grid", "copper_g"), ("fab_water_facility", "wsts_g"), ("chip_materials_and_chem", "wsts_g"), ("chip_materials_and_chem", "mem_g")):
    cols = [f"{drv}_l0", f"{drv}_l1"]; dep = "rev_growth"
    dd = A[(A.group == grp)].dropna(subset=cols + [dep]); dd = dd[dd.rev_growth.abs() < 1.0]
    dm = within(dd, cols, dep)
    specs = {"reported: firm-clustered": dict(cov_type="cluster", cov_kwds={"groups": pd.factorize(dm.gvkey)[0]}),
             "year-clustered": dict(cov_type="cluster", cov_kwds={"groups": dm.fyear.astype(int).values}),
             "two-way firm and year": dict(cov_type="cluster", cov_kwds={"groups": np.column_stack([pd.factorize(dm.gvkey)[0], dm.fyear.astype(int).values])})}
    for lab, kw in specs.items():
        m = sm.OLS(dm[dep], dm[cols]).fit(**kw)
        out.append(dict(group=grp, driver=drv, spec=lab, n=int(m.nobs), b_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], b_l1=m.params[cols[1]], t_l1=m.tvalues[cols[1]]))
    ty = dm.groupby("fyear")[[dep] + cols].mean()            # one observation per fiscal year (driver is common to all firms in a year)
    m = sm.OLS(ty[dep], sm.add_constant(ty[cols])).fit(cov_type="HC1")
    out.append(dict(group=grp, driver=drv, spec="year means (n = years), HC1", n=int(m.nobs), b_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], b_l1=m.params[cols[1]], t_l1=m.tvalues[cols[1]]))
    for lab, sub in (("FY2015-2019", dd[dd.fyear <= 2019]), ("FY2020-2025", dd[dd.fyear >= 2020])):
        dms = within(sub, cols, dep)
        m = sm.OLS(dms[dep], dms[cols]).fit(cov_type="cluster", cov_kwds={"groups": dms.fyear.astype(int).values})
        out.append(dict(group=grp, driver=drv, spec=f"{lab}, year-clustered", n=int(m.nobs), b_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], b_l1=m.params[cols[1]], t_l1=m.tvalues[cols[1]]))
    c3 = cols + [f"{drv}_l2"]; d3 = dd.dropna(subset=c3); dm3 = within(d3, c3, dep)
    m = sm.OLS(dm3[dep], dm3[c3]).fit(cov_type="cluster", cov_kwds={"groups": dm3.fyear.astype(int).values})
    out.append(dict(group=grp, driver=drv, spec="adding lag 2, year-clustered", n=int(m.nobs), b_l0=m.params[c3[0]], t_l0=m.tvalues[c3[0]], b_l1=m.params[c3[1]], t_l1=m.tvalues[c3[1]], b_l2=m.params[c3[2]], t_l2=m.tvalues[c3[2]]))
    loo0, loo1 = [], []
    for yv in sorted(dd.fyear.unique()):
        dms = within(dd[dd.fyear != yv], cols, dep); m = sm.OLS(dms[dep], dms[cols]).fit(); loo0.append(m.params[cols[0]]); loo1.append(m.params[cols[1]])
    out.append(dict(group=grp, driver=drv, spec="leave-one-year-out range", n=len(loo0), b_l0=f"{min(loo0):.2f} to {max(loo0):.2f}", b_l1=f"{min(loo1):.2f} to {max(loo1):.2f}"))
    # cases removed from their own group (the elasticity used for a case should not include the case)
    cs = [g for g in rc.CASES if g in dd.gvkey.values]
    if cs:
        dms = within(dd[~dd.gvkey.isin(cs)], cols, dep); m = sm.OLS(dms[dep], dms[cols]).fit(cov_type="cluster", cov_kwds={"groups": dms.fyear.astype(int).values})
        out.append(dict(group=grp, driver=drv, spec="excluding the case firms, year-clustered", n=int(m.nobs), b_l0=m.params[cols[0]], t_l0=m.tvalues[cols[0]], b_l1=m.params[cols[1]], t_l1=m.tvalues[cols[1]]))
O = pd.DataFrame(out); O.to_csv(OUT / "audit_driver_panel.csv", index=False)
pd.set_option("display.width", 250); print(O.round(3).to_string())
