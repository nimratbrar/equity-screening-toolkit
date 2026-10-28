"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-team audit 1: multiples, event study, betas, correlation with Japan Material.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/audit_amkor_stats.py  [--betas to rebuild the alternative market proxies, about 2 min]
Outputs: tables/amkr_audit_multiples.csv, amkr_audit_events.csv, amkr_audit_betas.csv. Inputs [WRDS data]; every test result [inference].
"""
import sys, numpy as np, pandas as pd, statsmodels.api as sm
from amkor_common import osat_set, XLSX, TABLES, AMKR, DATA, CACHE, tri_osat, us_market, ASOF
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
core = osat_set().set_index("gvkey")
x = pd.ExcelFile(XLSX); s = x.parse("Summary"); v = x.parse("Valuation inputs"); e = x.parse("Estimates")
o = s.merge(v[["tic", "forward_pe", "ev_to_ebitda_fwd"]], on="tic", suffixes=("", "_v")).merge(e[["tic", "eps_growth_fy2"]].rename(columns={"eps_growth_fy2": "eg2"}), on="tic", how="left"); o["eps_growth_fy2"] = o["eg2"]
o["is_amkr"] = o.tic == "AMKR"; o["log_fwd"] = np.log(o.ev_to_ebitda_fwd); o["log_pe"] = np.log(o.forward_pe)
rows = []
def add(test, value, note=""): rows.append(dict(test=test, value=value, note=note))
pe = o[~o.is_amkr].forward_pe.dropna(); a = o[o.is_amkr].iloc[0]
add("Amkor forward P/E", a.forward_pe); add("peer forward P/E median (n)", pe.median(), f"n={len(pe)}")
add("Amkor P/E vs peer median, log", np.log(a.forward_pe / pe.median()))
add("Amkor FY2 EPS growth (I/B/E/S)", a.eps_growth_fy2, "lowest of the covered set" if a.eps_growth_fy2 <= o.eps_growth_fy2.min() else "")
add("peer FY2 EPS growth median", o[~o.is_amkr].eps_growth_fy2.median())
# (1) leave-Amkor-out fits with FY2 EPS growth as the control
for dep in ["log_fwd", "log_pe"]:
    for cols in (["eps_growth_fy2"], ["eps_growth_fy2", "est_sales_growth_fy1"] if "est_sales_growth_fy1" in o else ["eps_growth_fy2"]):
        d = o.dropna(subset=[dep] + cols); p = d[~d.is_amkr]
        m = sm.OLS(p[dep], sm.add_constant(p[cols])).fit(cov_type="HC1")
        fit = float(m.predict(sm.add_constant(d[d.is_amkr][cols], has_constant="add")).iloc[0]); res = float(d[d.is_amkr][dep].iloc[0]) - fit
        add(f"{dep} ~ {'+'.join(cols)}: Amkor residual log (n peers)", res, f"n={int(m.nobs)}, coef {'; '.join(f'{c} {m.params[c]:.2f} t {m.tvalues[c]:.1f}' for c in cols)}, R2 {m.rsquared:.2f}, resid sd {np.sqrt(m.scale):.2f}")
# (2) jackknife: every name's leave-one-out residual in the sales-growth spec; where does Amkor rank?
inp = pd.read_csv(TABLES / "amkr_multiples_osat_inputs.csv", dtype={"gvkey": str}).dropna(subset=["ev_to_ebitda_fwd", "est_sales_growth_fy1"])
inp["y"] = np.log(inp.ev_to_ebitda_fwd); loo = []
for i in inp.index:
    p = inp.drop(index=i); m = sm.OLS(p.y, sm.add_constant(p[["est_sales_growth_fy1"]])).fit()
    loo.append(inp.y[i] - float(m.predict(sm.add_constant(inp.loc[[i], ["est_sales_growth_fy1"]], has_constant="add")).iloc[0]))
inp["loo"] = loo; sd_peers = inp[inp.gvkey != AMKR].loo.std()
add("jackknife: Amkor LOO residual / sd of peers' LOO residuals", inp[inp.gvkey == AMKR].loo.iloc[0] / sd_peers, f"peers' LOO sd {sd_peers:.2f}; most negative peer {inp[inp.gvkey != AMKR].loo.min():.2f} ({inp.loc[inp[inp.gvkey != AMKR].loo.idxmin(), 'conm']})")
add("jackknife: two-sided t-dist p for Amkor (df 14), no multiple-testing", float(2 * (1 - __import__('scipy').stats.t.cdf(abs(inp[inp.gvkey == AMKR].loo.iloc[0] / sd_peers), 14))))
# Case-company and peer multiples read from the deep-dive workbook (no hard-coded values) [WRDS data]
AMKR_FWD = float(a.ev_to_ebitda_fwd); AMKR_TRAIL = float(a.ev_to_ebitda); PEER_TRAIL_MED = float(o[~o.is_amkr].ev_to_ebitda.median()); PEER_FWD_MED = float(o[~o.is_amkr].ev_to_ebitda_fwd.median())
# (3) peer subsets: if Taiwan names are the mispriced ones
for lab, sel in [("non-Taiwan peers", inp["loc"] != "TWN"), ("non-Taiwan non-China peers", ~inp["loc"].isin(["TWN", "CHN"])), ("Taiwan peers", inp["loc"] == "TWN")]:
    p = inp[sel & (inp.gvkey != AMKR)]
    add(f"{lab}: median fwd EV/EBITDA (n)", float(np.exp(p.y.median())), f"n={len(p)}; Amkor vs median log {np.log(AMKR_FWD) - p.y.median():.2f}")
# (4) history: peers today vs their own FY2020-25 trailing range; Amkor vs its own
h = pd.read_csv(TABLES / "amkr_multiple_history.csv")
add("peer median trailing EV/EBITDA FY2020-25 range", f"{h.peer_median.min():.1f} to {h.peer_median.max():.1f}", f"today {PEER_TRAIL_MED:.1f}x trailing / {PEER_FWD_MED:.1f}x fwd")
add("peer median today vs FY2020-25 mean, log", np.log(PEER_TRAIL_MED / np.exp(np.log(h.peer_median).mean())))
add("Amkor trailing today vs own FY2020-25 mean, log", np.log(AMKR_TRAIL / np.exp(np.log(h.amkor_ev_ebitda).mean())), f"own range {h.amkor_ev_ebitda.min():.1f} to {h.amkor_ev_ebitda.max():.1f}; today {AMKR_TRAIL:.2f}x")
add("Amkor vs peer median FY2020-25, mean log gap", h.amkor_vs_peer_median_log.mean())
b = pd.read_csv(TABLES / "amkr_multiples_broad.csv")
for r in b.itertuples():
    if r.model.startswith(("broad: peer industries", "broad m4, EV/EBITDA trimmed", "semis only (GICS 4530), country")):
        add(f"broad model, Amkor minus OSAT-peer median residual: {r.model}", r.resid_log - r.osat_peer_median_resid)
pd.DataFrame(rows).to_csv(TABLES / "amkr_audit_multiples.csv", index=False); print(pd.DataFrame(rows).to_string())
print(inp[["conm", "loc", "ev_to_ebitda_fwd", "est_sales_growth_fy1", "loo"]].round(2).sort_values("loo").to_string())

# ---------------- event study: signed AI pool, leave-one-out, multiple testing
dm = pd.read_csv(TABLES / "amkr_event_dummies_weekly.csv"); pooled = pd.read_csv(TABLES / "amkr_event_pooled_perm.csv")
ai = dm[dm.cls.str.contains("ai")].copy(); sd = float(dm.resid_sd_weekly.iloc[0])
def sgn(s): return {"+": 1, "-": -1}.get(s, 0)
ai["sign_num"] = ai.expected_sign.map(sgn); ev_rows = []
ev_rows.append(dict(test="AI pool unsigned (as reported)", n=len(ai), mean=ai.abnormal_weekly_return.mean(), t=ai.abnormal_weekly_return.mean() / (sd / np.sqrt(len(ai)))))
sg = ai[ai.sign_num != 0]; sv = sg.abnormal_weekly_return * sg.sign_num
ev_rows.append(dict(test="AI pool signed by expected sign (mixed -/+ week dropped)", n=len(sg), mean=sv.mean(), t=sv.mean() / (sd / np.sqrt(len(sg))), share_right_sign=float((sv > 0).mean())))
for drop in ai.event:
    k = ai[ai.event != drop].abnormal_weekly_return
    ev_rows.append(dict(test=f"AI pool unsigned, drop '{drop[:40]}'", n=len(k), mean=k.mean(), t=k.mean() / (sd / np.sqrt(len(k)))))
npools = len(pooled); p_ai = float(pooled.loc[pooled["pool"] == "class ai", "permutation_p_two_sided"].iloc[0])   # read from amkor_returns.py output
ev_rows.append(dict(test=f"Bonferroni-adjusted p of AI pool over {npools} pools", n=npools, mean=np.nan, t=np.nan, p_adj=min(1, p_ai * npools)))
ev_rows.append(dict(test="Expected-sign hit rate, all signed weeks", n=int((dm.expected_sign.isin(['+', '-'])).sum()), mean=float(((dm.abnormal_weekly_return * dm.expected_sign.map(sgn)) > 0)[dm.expected_sign.isin(['+', '-'])].mean()), t=np.nan))
ev = pd.DataFrame(ev_rows); ev.to_csv(TABLES / "amkr_audit_events.csv", index=False); print(ev.round(4).to_string())

# ---------------- correlation with Japan Material (weekly, USD-agnostic local returns, 2 years)
pc = pd.read_csv(CACHE / "prices_core.csv", dtype={"gvkey": str}); pc["datadate"] = pd.to_datetime(pc.datadate)
pc["tri"] = pc.price / pc.ajexdi.fillna(1) * pc.trfd.fillna(1); jm = pc[pc.gvkey == "311307"]   # Compustat gvkey of a comparison case (identifier only).set_index("datadate").tri
am = tri_osat()[AMKR]; w = pd.concat([np.log(am.resample("W-FRI").last()).diff(), np.log(jm.resample("W-FRI").last()).diff()], axis=1, keys=["amkr", "jm"]).dropna()
for yrs in (2, 5):
    ww = w.loc[ASOF - pd.DateOffset(years=yrs):]; print(f"corr AMKR vs Japan Material weekly, {yrs}y: {ww.corr().iloc[0,1]:.2f} (n {len(ww)})")

# ---------------- betas against alternative US proxies (optional, slow)
if "--betas" in sys.argv:
    u = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); u["gvkey"] = u.gvkey.str.zfill(6)
    lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}); lp["gvkey"] = lp.gvkey.str.zfill(6)
    fa = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, usecols=["gvkey", "fyear", "indfmt", "csho"], low_memory=False); fa["gvkey"] = fa.gvkey.str.zfill(6)
    fa = fa[(fa.indfmt == "INDL") & (fa.fyear >= 2024)].sort_values("fyear").groupby("gvkey").tail(1)
    us = u[(u.region == "na") & (u["loc"] == "USA") & (u.curcd == "USD")].merge(fa[["gvkey", "csho"]], on="gvkey").merge(lp[["gvkey", "price"]], on="gvkey")
    us["cap"] = us.csho * us.price; us = us[us.gvkey != AMKR].sort_values("cap", ascending=False).head(300); us["sec"] = us.gsubind.astype(str).str[:2]
    keep = set(us.gvkey); parts = []
    for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "price", "ajexdi", "trfd"], chunksize=3_000_000):
        ch["gvkey"] = ch.gvkey.str.zfill(6); parts.append(ch[ch.gvkey.isin(keep)])
    m = pd.concat(parts).dropna(subset=["price"]); m["tri"] = m.price / m.ajexdi.fillna(1) * m.trfd.fillna(1); m["datadate"] = pd.to_datetime(m.datadate)
    wide = m.pivot_table(index="datadate", columns="gvkey", values="tri").sort_index(); wk = np.log(wide.resample("W-FRI").last()).diff()
    def proxy(gv, cw=True):
        W = us.set_index("gvkey").cap.reindex(gv) if cw else pd.Series(1.0, index=gv); r = wk[gv]; ok = r.notna()
        return (r.fillna(0) * W).sum(axis=1) / (ok * W).sum(axis=1)
    allg = list(us.gvkey); notech = list(us[~us.sec.isin(["45", "50"])].gvkey)
    prox = {"cap-weighted top 300 (rebuilt, as reported)": proxy(allg), "equal-weight top 300": proxy(allg, False), "cap-weighted ex IT and comms (GICS 45, 50)": proxy(notech), "equal-weight ex IT and comms": proxy(notech, False)}
    y = np.log(am.resample("W-FRI").last()).diff(); brow = []
    for k, px in prox.items():
        d = pd.concat([y, px], axis=1, keys=["y", "x"]).loc[ASOF - pd.DateOffset(years=5):].dropna(); f = sm.OLS(d.y, sm.add_constant(d.x)).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        brow.append(dict(proxy=k, beta=f.params["x"], t_hac4=f.tvalues["x"], r2=f.rsquared, n_weeks=int(f.nobs), tech_weight=float(us[us.sec.isin(["45", "50"])].cap.sum() / us.cap.sum()) if "ex" not in k else 0.0))
    bt = pd.DataFrame(brow); bt.to_csv(TABLES / "amkr_audit_betas.csv", index=False); print(bt.round(3).to_string())
