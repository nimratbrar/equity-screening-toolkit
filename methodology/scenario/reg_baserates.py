"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Analysis 4: historical downside base rates for the simulation agent.
(a) 12-month total-return distribution (local currency, overlapping daily windows) and max drawdown, per case and per group [WRDS data].
(b) Frequency of EBITDA (oibdp) falling more than 10/20/30% year on year: firm-years in the 40-name groups (FY2015 to FY2025) and,
    as a wider base, every company in the price file inside the same GICS industry groups [WRDS data].
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/reg_baserates.py
Outputs: tables/baserates_returns12m.csv, tables/baserates_ebitda_falls.csv, tables/baserates_returns12m_by_firm.csv
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from reg_common import universe_core, tri_wide, DATA, TABLES, CASES

core = universe_core().set_index("gvkey"); tri = tri_wide()
def ret12(s):
    s = s.dropna(); out = {}
    for t in s.index[s.index >= s.index[0] + pd.Timedelta(days=365)]:
        base = s.loc[:t - pd.Timedelta(days=365)]
        if len(base): out[t] = np.log(s[t] / base.iloc[-1])
    return pd.Series(out)
def maxdd(s):
    s = s.dropna(); return float((s / s.cummax() - 1).min())
def dist(r, label, n_firms, sample):
    q = r.quantile([0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95])
    return dict(label=label, n_firms=n_firms, n_obs=len(r), sample=sample, mean=r.mean(), sd=r.std(), p05=q[0.05], p10=q[0.10], p25=q[0.25], p50=q[0.50], p75=q[0.75], p90=q[0.90], p95=q[0.95],
                share_negative=(r < 0).mean(), share_below_m20=(r < np.log(0.8)).mean(), share_below_m30=(r < np.log(0.7)).mean(), share_above_p50=(r > np.log(1.5)).mean(), note="log 12m total returns, overlapping daily windows, local currency")
rows, firm = [], []
R = {gv: ret12(tri[gv]) for gv in tri.columns}
for gv, r in R.items():
    firm.append(dict(gvkey=gv, conm=core.loc[gv, "conm"], group=core.loc[gv, "group"], case=core.loc[gv, "case"], n_obs=len(r), sample=f"{r.index[0].date()} to {r.index[-1].date()}" if len(r) else "",
                     p05=r.quantile(0.05), p50=r.median(), p95=r.quantile(0.95), worst_12m=r.min(), best_12m=r.max(), share_negative=(r < 0).mean(), max_drawdown=maxdd(tri[gv]), current_vs_peak=float(tri[gv].dropna().iloc[-1] / tri[gv].dropna().max() - 1)))
for gv, nm in CASES.items():
    r = R[gv]; rows.append(dist(r, nm, 1, f"{r.index[0].date()} to {r.index[-1].date()}"))
for grp in core.group.unique():
    gvs = core[core.group == grp].index; r = pd.concat([R[g] for g in gvs]); rows.append(dist(r, f"group: {grp} (pooled firm-days)", len(gvs), f"{r.index.min().date()} to {r.index.max().date()}"))
r = pd.concat(R.values()); rows.append(dist(r, "all core names (pooled firm-days)", len(R), f"{r.index.min().date()} to {r.index.max().date()}"))
pd.DataFrame(rows).to_csv(TABLES / "baserates_returns12m.csv", index=False)
pd.DataFrame(firm).to_csv(TABLES / "baserates_returns12m_by_firm.csv", index=False)

# EBITDA falls
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False)
a = a[a.indfmt == "INDL"].sort_values(["gvkey", "fyear"]).drop_duplicates(["gvkey", "fyear"], keep="last")
g = a.groupby("gvkey"); a["oibdp_l1"], a["curcd_l1"], a["fy_l1"] = g.oibdp.shift(1), g.curcd.shift(1), g.fyear.shift(1)
a = a[(a.curcd == a.curcd_l1) & (a.fyear - a.fy_l1 == 1) & (a.oibdp_l1 > 0) & a.oibdp.notna()].copy()
a["chg"] = a.oibdp / a.oibdp_l1 - 1
uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = a.merge(uni[["gvkey", "gsubind"]], on="gvkey", how="left"); a["ind4"] = a.gsubind.astype(str).str[:4]
def falls(x, label):
    return dict(label=label, n_firm_years=len(x), n_firms=x.gvkey.nunique(), sample=f"FY{int(x.fyear.min())} to FY{int(x.fyear.max())}", share_down=(x.chg < 0).mean(), share_down_gt10=(x.chg < -0.10).mean(),
                share_down_gt20=(x.chg < -0.20).mean(), share_down_gt30=(x.chg < -0.30).mean(), share_to_negative=(x.oibdp <= 0).mean(), count_down_gt10=int((x.chg < -0.10).sum()), count_down_gt20=int((x.chg < -0.20).sum()),
                median_chg=x.chg.median(), p10_chg=x.chg.quantile(0.10), p90_chg=x.chg.quantile(0.90))
erows = []
for gv, nm in CASES.items():
    x = a[a.gvkey == gv]; erows.append(falls(x, f"{nm} (own history)"))
for grp in core.group.unique():
    x = a[a.gvkey.isin(core[core.group == grp].index)]; erows.append(falls(x, f"group: {grp} (40-name peers)"))
    inds = sorted(core[core.group == grp].gsubind.astype(str).str[:4].unique())
    x = a[a.ind4.isin(inds)]; erows.append(falls(x, f"broad: GICS industry groups {inds} of {grp}"))
erows.append(falls(a[a.gvkey.isin(core.index)], "all core names")); erows.append(falls(a, "broad: all companies in the price file"))
pd.DataFrame(erows).to_csv(TABLES / "baserates_ebitda_falls.csv", index=False)
print(pd.DataFrame(rows).round(3).to_string()); print(pd.DataFrame(firm).round(3).to_string()); print(pd.DataFrame(erows).round(3).to_string())
