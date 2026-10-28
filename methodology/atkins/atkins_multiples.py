"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

AtkinsRéalis analysis 2: EV/EBITDA cross-section (peer set of 19 and the broad universe model), residual range, and the
sum-of-the-parts framing. Peer inputs [WRDS data: deep dive Summary / Valuation inputs / Estimates sheets; forward multiples
from I/B/E/S where present, trailing for ATRL, WSP, Stantec and Cameco where the I/B/E/S link failed]. ATRL forward multiple
on guidance-built FY1 EBITDA [company filing, inference]. Broad model = same construction as methodology/scenario/reg_multiples.py
(trailing, latest FY accounts, latest price, winsorised 1/99, country and GICS industry-group dummies) with a CAN dummy added.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_multiples.py
Outputs (methodology/atkins/tables/): atrl_multiples_peer_inputs.csv, atrl_multiples_peer_specs.csv, atrl_multiples_broad_coefs.csv,
atrl_multiples_residuals.csv, atrl_multiples_peer_fitted.csv, atrl_sotp.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from atkins_common import deep, PEERS, ATRL, ATRL_IN, TABLES, DATA, CACHE, fx, to_usd_rate, CONSULT, NUCLEAR

# ---------------- peer set ----------------
S = deep("Summary"); V = deep("Valuation inputs"); P = deep("Price performance")
S = S.merge(P[["gvkey", "tic"]], on="tic", how="left").set_index("gvkey")
S["name"] = S.index.map(lambda g: PEERS[g][0]); S["group"] = S.index.map(lambda g: PEERS[g][1])
S["mult_trailing"] = S.ev_to_ebitda; S["mult_fwd"] = S.ev_to_ebitda_fwd
S.loc[ATRL, "mult_fwd"] = ATRL_IN["fwd_mult"]                                # EV / guidance-built FY1 EBITDA [inference]
S["mult_used"] = S.mult_fwd.fillna(S.mult_trailing); S["trailing_flag"] = S.mult_fwd.isna().astype(float)
S.loc[ATRL, "trailing_flag"] = 0.0
S["log_mcap"] = np.log(S.market_cap); S["nuclear"] = (S.group == "nuclear").astype(float)
cols = ["rev_cagr_3y", "ebitda_margin", "roic", "net_debt_to_ebitda", "log_mcap", "nuclear"]
pi = S[["name", "group", "mult_trailing", "mult_fwd", "mult_used", "trailing_flag"] + cols]; pi.to_csv(TABLES / "atrl_multiples_peer_inputs.csv")

def fit_peer(y, X, label, drop=None):
    idx = X.index.difference([drop]) if drop else X.index
    m = sm.OLS(np.log(y.loc[idx]), sm.add_constant(X.loc[idx])).fit(cov_type="HC1")
    xa = sm.add_constant(X, has_constant="add").loc[[ATRL]]
    fitted = float(np.exp(m.predict(xa)).iloc[0]); act = float(y.loc[ATRL])
    return m, dict(spec=label, n=int(m.nobs), adj_r2=m.rsquared_adj, atrl_actual=act, atrl_fitted=fitted, atrl_pct_vs_fitted=act / fitted - 1,
                   nuclear_coef=m.params.get("nuclear", np.nan), nuclear_t=m.tvalues.get("nuclear", np.nan), growth_coef=m.params.get("rev_cagr_3y", np.nan), growth_t=m.tvalues.get("rev_cagr_3y", np.nan),
                   resid_sd=float(np.sqrt(m.scale)), leave_atrl_out=bool(drop))
specs = []; peer_fit = {}
X_full = S[cols]; X_small = S[["rev_cagr_3y", "ebitda_margin", "nuclear"]]
for lab, y, X in [("trailing, 6 regressors", S.mult_trailing, X_full), ("trailing, growth+margin+nuclear", S.mult_trailing, X_small),
                  ("fwd where available, 6 regressors + trailing flag", S.mult_used, pd.concat([X_full, S.trailing_flag], axis=1)),
                  ("fwd where available, growth+margin+nuclear+flag", S.mult_used, pd.concat([X_small, S.trailing_flag], axis=1)),
                  ("fwd, consultancies + nuclear only (ex EPC)", S.mult_used[S.group != "epc"], pd.concat([X_small, S.trailing_flag], axis=1)[S.group != "epc"])]:
    m, row = fit_peer(y, X, lab); specs.append(row); peer_fit[lab] = (m, X)
    m2, row2 = fit_peer(y, X, lab + " (ATRL left out)", drop=ATRL); specs.append(row2)
specs = pd.DataFrame(specs); specs.to_csv(TABLES / "atrl_multiples_peer_specs.csv", index=False)
m, X = peer_fit["fwd where available, 6 regressors + trailing flag"]
pf = pd.DataFrame({"name": S.name, "group": S.group, "actual": S.mult_used, "fitted": np.exp(m.predict(sm.add_constant(X)))}); pf["pct_vs_fitted"] = pf.actual / pf.fitted - 1
pf.to_csv(TABLES / "atrl_multiples_peer_fitted.csv")

# ---------------- broad universe model (reg_multiples construction, CAN dummy added) ----------------
fxw = fx(); uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False); a = a[a.indfmt == "INDL"].copy(); a["gvkey"] = a.gvkey.str.zfill(6)
a = a.sort_values(["gvkey", "fyear"]); a["sale_l3"] = a.groupby("gvkey").sale.shift(3)
last = a[a.fyear >= 2024].groupby("gvkey").tail(1).set_index("gvkey")
lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}).set_index("gvkey"); fy = pd.read_csv(CACHE / "price_at_fye.csv", dtype={"gvkey": str}).set_index("gvkey")
d = last.join(lp[["price", "ajexdi", "curcdd"]], how="inner").join(fy, how="inner"); d = d[d.curcd == d.curcdd]
d["usd"] = [to_usd_rate(c, fxw) for c in d.curcd]; d.loc[d.curcd == "CAD", "usd"] = 1 / 1.4157   # fx_daily has no CAD; FRED DEXCAUS 2026-10-16 [source: FRED, https://fred.stlouisfed.org/series/DEXCAUS]
d["mcap_loc"] = d.price * d.csho * d.ajexdi_fye / d.ajexdi; d["mcap_usd_mm"] = d.mcap_loc * d.usd
d["net_debt"] = d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0); d["ev"] = d.mcap_loc + d.net_debt + d.pstk.fillna(0) + d.mib.fillna(0)
d["ev_ebitda"] = d.ev / d.oibdp; d["ebitda_margin"] = d.oibdp / d.sale; d["nd_ebitda"] = d.net_debt / d.oibdp; d["rev_cagr3"] = (d.sale / d.sale_l3) ** (1 / 3) - 1
tax = (d.txt / d.pi).where((d.pi > 0) & (d.txt >= 0)).clip(0, 0.35).fillna(0.25); ic = d.seq.fillna(d.ceq) + d.mib.fillna(0) + d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0)
d["roic"] = d.oiadp * (1 - tax) / ic.where(ic > 0); d["log_mcap_usd"] = np.log(d.mcap_usd_mm); d["log_ev_ebitda"] = np.log(d.ev_ebitda)
d = d.join(uni.set_index("gvkey")[["loc", "gsubind"]], rsuffix="_u")
EURO = {"FRA", "ITA", "DNK", "FIN", "DEU", "NLD", "ESP", "BEL", "AUT", "IRL", "PRT", "SWE", "NOR", "CHE"}
def ctry(l): return "JPN" if l == "JPN" else "KOR" if l == "KOR" else "USA" if l in ("USA", "GBR") else "CAN" if l == "CAN" else "EUR" if l in EURO else "TWN" if l == "TWN" else "CHN" if l in ("CHN", "HKG") else "OTH"
d["ctry"] = d["loc"].map(ctry); d["ind4"] = d.gsubind.astype(str).str[:4]
d = d.replace([np.inf, -np.inf], np.nan); d = d[(d.oibdp > 0) & (d.ev > 0) & (d.ev_ebitda > 1) & (d.ev_ebitda < 100) & (d.sale > 0) & (d.mcap_usd_mm >= 1000)]
d = d.dropna(subset=["log_ev_ebitda", "roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"])
REG = ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"]
def design(x, inds):
    X = x[REG].copy()
    for c in REG[:-1]: X[c] = X[c].clip(d[c].quantile(0.01), d[c].quantile(0.99))
    X = pd.concat([X, pd.get_dummies(x.ctry, prefix="ctry", dtype=float).drop(columns=["ctry_OTH"], errors="ignore"),
                   pd.get_dummies(x.ind4, prefix="ind4", dtype=float).reindex(columns=[f"ind4_{i}" for i in inds if i != "2010"], fill_value=0.0)], axis=1)
    return sm.add_constant(X, has_constant="add")
# ATRL row from the deep dive (Compustat latest FY, latest price); gsubind 20103010 Construction & Engineering like Stantec
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
atrl_row = pd.DataFrame([dict(roic=0.10, rev_cagr3=0.10, ebitda_margin=1000.0 / 10000.0, nd_ebitda=100.0 / 1000.0,   # [placeholder: Compustat ROIC, 3y sales CAGR, oibdp/sale, net debt/oibdp]
                              log_mcap_usd=np.log(10000.0), ctry="CAN", ind4="2010", ev_ebitda=15000.0 / 1000.0)], index=[ATRL])  # [placeholder: USD market cap, EV/oibdp]
# ===== END PLACEHOLDER INPUTS =====
PEER_IND = sorted(set(uni.set_index("gvkey").reindex(list(PEERS)).gsubind.dropna().astype(str).str[:4]) | {"2010", "2020", "1010"})
b_all = d; b_peer = d[d.ind4.isin(PEER_IND)]
coefs, resids = [], []
def predict_atrl(mdl, Xcols, inds):
    xa = design(atrl_row, inds).reindex(columns=Xcols, fill_value=0.0); return float(np.exp(mdl.predict(xa)).iloc[0])
for lab, b, inds in [("broad all industries", b_all, sorted(d.ind4.unique())), ("broad peer industries (2010, 2020, 1010 ...)", b_peer, PEER_IND)]:
    X = design(b, inds); y = b.log_ev_ebitda
    fits = {"OLS": sm.OLS(y, X).fit(cov_type="HC1"), "Huber": sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit(), "median": sm.QuantReg(y, X).fit(q=0.5, max_iter=5000)}
    trim = (b.ev_ebitda >= 4) & (b.ev_ebitda <= 40); fits["OLS 4x to 40x"] = sm.OLS(y[trim], X[trim]).fit()
    ols = sm.OLS(y, X).fit(); keep = pd.Series(ols.get_influence().cooks_distance[0], index=X.index) <= 4 / len(y); fits["OLS drop Cook's D"] = sm.OLS(y[keep], X[keep]).fit()
    for k, mdl in fits.items():
        fitted = predict_atrl(mdl, X.columns, inds); act = float(atrl_row.ev_ebitda.iloc[0])
        resids.append(dict(model=lab, estimator=k, n=int(mdl.nobs), atrl_actual_trailing=act, atrl_fitted=fitted, pct_vs_fitted=act / fitted - 1, log_resid=np.log(act / fitted),
                           can_coef=mdl.params.get("ctry_CAN", np.nan), resid_sd=float(np.sqrt(getattr(mdl, "scale", np.nan))) if k != "median" else np.nan))
        if k == "OLS":
            for r in REG + ["ctry_CAN", "ctry_JPN", "ctry_EUR", "ctry_USA"] + [c for c in X.columns if c in ("ind4_2020", "ind4_1010")]:
                if r in mdl.params: coefs.append(dict(model=lab, regressor=r, coef=mdl.params[r], t_hc1=mdl.tvalues[r], n=int(mdl.nobs), adj_r2=mdl.rsquared_adj))
            # peers' residuals from the broad model (those with Compustat rows), to show the nuclear premium
            pk = [g for g in PEERS if g in X.index]
            pr = pd.DataFrame({"name": [PEERS[g][0] for g in pk], "group": [PEERS[g][1] for g in pk], "actual_trailing": b.loc[pk, "ev_ebitda"].values,
                               "fitted": np.exp(mdl.predict(X.loc[pk])).values}); pr["pct_vs_fitted"] = pr.actual_trailing / pr.fitted - 1; pr["model"] = lab
            resids_peers = pr if lab.startswith("broad all") else pd.concat([resids_peers, pr])
coefs = pd.DataFrame(coefs); coefs.to_csv(TABLES / "atrl_multiples_broad_coefs.csv", index=False)
res = pd.DataFrame(resids); res.to_csv(TABLES / "atrl_multiples_residuals.csv", index=False)
resids_peers.to_csv(TABLES / "atrl_multiples_peer_fitted_broad.csv", index=False)

# ---------------- sum of the parts on FY2026e [inference; segment split from filings, see atkins_common.ATRL_IN] ----------------
fwd = S.mult_fwd; cons_f = fwd.reindex(CONSULT).dropna(); cons_t = S.mult_trailing.reindex(["277846", "029985"])
nuc_f = fwd.reindex(["185229", "003662", "039935"])            # nuclear services and components (BWXT, CW, Mirion); Cameco and Centrus are fuel, excluded
seg = ATRL_IN["seg_fy1"]; nd = ATRL_IN["net_debt"]; sh = ATRL_IN["shares"]; lstk = ATRL_IN["lstk_cash_drag_2026"]
cases = {"low": dict(esr=cons_f.quantile(0.25), nuc=cons_f.median(), other=0.0, lstk=-lstk[1]),
         "mid": dict(esr=cons_f.median(), nuc=(cons_f.median() + nuc_f.median()) / 2, other=0.0, lstk=-np.mean(lstk)),
         "high": dict(esr=cons_f.quantile(0.75), nuc=nuc_f.median(), other=0.0, lstk=-lstk[0])}
sotp = []
for k, c in cases.items():
    ev_esr = seg["ESR"] * c["esr"]; ev_nuc = seg["Nuclear"] * c["nuc"]; ev_corp = seg["Corporate"] * c["esr"]; ev_oth = seg["Other"] * c["other"]
    eq = ev_esr + ev_nuc + ev_corp + ev_oth + c["lstk"] - nd
    sotp.append(dict(case=k, esr_mult=c["esr"], nuclear_mult=c["nuc"], ev_esr=ev_esr, ev_nuclear=ev_nuc, ev_corporate=ev_corp, ev_other=ev_oth, lstk_drag=c["lstk"], net_debt=-nd,
                     equity=eq, per_share=eq / sh, vs_price=eq / sh / ATRL_IN["price"] - 1, implied_group_mult=(eq + nd) / ATRL_IN["ebitda_fy1"][1]))
sotp = pd.DataFrame(sotp); sotp.to_csv(TABLES / "atrl_sotp.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(pi.round(3).to_string()); print(specs.round(3).to_string()); print(pf.round(2).to_string())
print(coefs.round(3).to_string()); print(res.round(3).to_string()); print(resids_peers.round(2).to_string())
print("consult fwd multiples:", cons_f.round(1).to_dict(), "WSP/STN trailing:", cons_t.round(1).to_dict(), "nuclear fwd:", nuc_f.round(1).to_dict())
print(sotp.round(2).to_string())
