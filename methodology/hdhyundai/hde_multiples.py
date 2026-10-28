"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

HDE analysis 2: EV/EBITDA cross-section. (a) grid peers from the deep dive (I/B/E/S forward, Compustat latest-FY trailing),
leave-HDE-out fits with small specs (small n); HDE forward multiple restated on the same-date basis (latest-quarter Compustat net cash
and the matching share count, rather than the deep dive's fiscal-year-end net cash). (b) the broad house model of methodology/scenario/reg_multiples.py
(m4: trailing, latest FY accounts, latest price, winsorised, country and GICS industry-group dummies, peer industries) with HDE's
residual, robust variants, and HDE minus the grid-peer median residual (the residual that matches the -0.25 a year reversion slope).
(c) HDE's own EV / LTM EBITDA at each quarter end since 2022.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_multiples.py
Outputs: tables/hde_multiples_peer_inputs.csv, hde_multiples_peer_specs.csv, hde_multiples_broad.csv, hde_multiples_summary.csv,
hde_multiple_history.csv. [WRDS data]; fits and residuals [inference].
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from hde_common import deep, PEERS, HDE, HDE_IN, TABLES, DATA, CACHE, fx, NAME, quarterly, prices
import sys; from hde_common import ROOT; sys.path.insert(0, str(ROOT / "methodology/scenario"))
from reg_common import to_usd_rate
SLOPE = 0.25

# ---------------- (a) grid peer set
S = deep("Summary"); P = deep("Price performance"); E = deep("Estimates")
S = S.merge(P[["gvkey", "tic"]], on="tic", how="left").merge(E[["tic", "eps_growth_fy2", "fy1_period_end"]], on="tic", how="left", suffixes=("", "_e")).set_index("gvkey")
S["name"] = S.index.map(NAME); S["group"] = S.index.map(lambda g: PEERS[g][1])
S["korea"] = (S["loc"] == "KOR").astype(float); S["log_mcap"] = np.log(S.market_cap)
S["fwd"] = S.ev_to_ebitda_fwd; S.loc[HDE, "fwd"] = HDE_IN["fwd_mult"]                 # same-date basis [WRDS data, company filing]
S["fwd_ebitda_growth"] = S.ebitda_fy1_usd / S.ebitda - 1
S["log_fwd"] = np.log(S.fwd); S["log_trail"] = np.log(S.ev_to_ebitda)
keep = ["name", "group", "market_cap", "ev_to_ebitda", "ev_to_ebitda_fwd", "fwd", "eps_growth_fy2", "fwd_ebitda_growth", "est_sales_growth_fy1", "rev_cagr_3y", "ebitda_margin", "roic", "net_debt_to_ebitda", "ret_12m", "pct_from_52w_high", "revision_breadth"]
S[keep].to_csv(TABLES / "hde_multiples_peer_inputs.csv")
SPECS = {
 "fwd: FY2 EPS growth": ("log_fwd", ["eps_growth_fy2"]),
 "fwd: FY2 EPS growth + margin": ("log_fwd", ["eps_growth_fy2", "ebitda_margin"]),
 "fwd: FY2 EPS growth + margin + ROIC": ("log_fwd", ["eps_growth_fy2", "ebitda_margin", "roic"]),
 "fwd: FY1 EBITDA growth + margin": ("log_fwd", ["fwd_ebitda_growth", "ebitda_margin"]),
 "fwd: 3y CAGR + margin": ("log_fwd", ["rev_cagr_3y", "ebitda_margin"]),
 "fwd: FY2 EPS growth + margin + Korea": ("log_fwd", ["eps_growth_fy2", "ebitda_margin", "korea"]),
 "fwd: Korea dummy only": ("log_fwd", ["korea"]),
 "trail: 3y CAGR + margin": ("log_trail", ["rev_cagr_3y", "ebitda_margin"]),
 "trail: 3y CAGR + margin + ROIC": ("log_trail", ["rev_cagr_3y", "ebitda_margin", "roic"]),
}
rows = []
for lab, (dep, cols) in SPECS.items():
    d = S.dropna(subset=[dep] + cols); peers = d.drop(index=HDE)
    m = sm.OLS(peers[dep], sm.add_constant(peers[cols])).fit(cov_type="HC1")
    fit_h = float(m.predict(sm.add_constant(d[cols], has_constant="add").loc[[HDE]]).iloc[0]); act = float(d.loc[HDE, dep])
    rows.append(dict(spec=lab, n_peers=int(m.nobs), hde_actual=np.exp(act), fitted_loo=np.exp(fit_h), resid_log=act - fit_h, pct_vs_fitted=np.exp(act - fit_h) - 1,
                     resid_sd=float(np.sqrt(m.scale)), z=(act - fit_h) / np.sqrt(m.scale), adj_r2=m.rsquared_adj,
                     coefs="; ".join(f"{c} {m.params[c]:.2f} (t {m.tvalues[c]:.1f})" for c in cols), peer_median=float(np.exp(peers[dep].median()))))
peer = pd.DataFrame(rows); peer.to_csv(TABLES / "hde_multiples_peer_specs.csv", index=False)

# ---------------- (b) broad house model (same construction as amkor_multiples.py / reg_multiples.py m4)
fxw = fx()
uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False)
a = a[(a.indfmt == "INDL")].copy(); a["gvkey"] = a.gvkey.str.zfill(6); a = a.sort_values(["gvkey", "fyear"])
a["sale_l3"] = a.groupby("gvkey").sale.shift(3)
last = a[a.fyear >= 2024].groupby("gvkey").tail(1).set_index("gvkey")
lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}); lp["gvkey"] = lp.gvkey.str.zfill(6); lp = lp.set_index("gvkey")
fy = pd.read_csv(CACHE / "price_at_fye.csv", dtype={"gvkey": str}); fy["gvkey"] = fy.gvkey.str.zfill(6); fy = fy.set_index("gvkey")
d = last.join(lp[["price", "ajexdi", "curcdd", "datadate"]].rename(columns={"datadate": "price_date"}), how="inner").join(fy, how="inner")
d = d[d.curcd == d.curcdd]; d["usd"] = [to_usd_rate(c, fxw) for c in d.curcd]
d["shares_now"] = d.csho * d.ajexdi_fye / d.ajexdi; d["mcap_loc"] = d.price * d.shares_now; d["mcap_usd_mm"] = d.mcap_loc * d.usd
d["net_debt"] = d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0); d["ev"] = d.mcap_loc + d.net_debt + d.pstk.fillna(0) + d.mib.fillna(0)
d["ev_ebitda"] = d.ev / d.oibdp; d["ebitda_margin"] = d.oibdp / d.sale; d["nd_ebitda"] = d.net_debt / d.oibdp; d["rev_cagr3"] = (d.sale / d.sale_l3) ** (1 / 3) - 1
tax = (d.txt / d.pi).where((d.pi > 0) & (d.txt >= 0)).clip(0, 0.35).fillna(0.25); ic = d.seq.fillna(d.ceq) + d.mib.fillna(0) + d.dltt.fillna(0) + d.dlc.fillna(0) - d.che.fillna(0)
d["roic"] = d.oiadp * (1 - tax) / ic.where(ic > 0); d["log_mcap_usd"] = np.log(d.mcap_usd_mm); d["log_ev_ebitda"] = np.log(d.ev_ebitda)
d = d.join(uni.set_index("gvkey")[["loc", "gsubind"]], rsuffix="_u"); d["loc"] = d["loc"] if "loc" in d.columns else d["loc_u"]
EURO = {"FRA", "ITA", "DNK", "FIN", "DEU", "NLD", "ESP", "BEL", "AUT", "IRL", "PRT", "SWE", "NOR", "CHE"}
def ctry(l): return "JPN" if l == "JPN" else "KOR" if l == "KOR" else "USA" if l in ("USA", "GBR") else "EUR" if l in EURO else "TWN" if l == "TWN" else "CHN" if l in ("CHN", "HKG") else "OTH"
d["ctry"] = d["loc"].map(ctry); d["ind4"] = d.gsubind.astype(str).str[:4]; d["ind6"] = d.gsubind.astype(str).str[:6]
def clean(x):
    x = x.replace([np.inf, -np.inf], np.nan); x = x[(x.oibdp > 0) & (x.ev > 0) & (x.ev_ebitda > 1) & (x.ev_ebitda < 100) & (x.sale > 0)]
    return x.dropna(subset=["log_ev_ebitda", "roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"])
def design(x, dummies):
    X = x[["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"]].copy()
    for c in ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]: X[c] = X[c].clip(X[c].quantile(0.01), X[c].quantile(0.99))
    for dcol, base in dummies:
        D = pd.get_dummies(x[dcol], prefix=dcol, dtype=float).drop(columns=[f"{dcol}_{base}"], errors="ignore"); X = pd.concat([X, D], axis=1)
    return sm.add_constant(X)
b = clean(d[d.mcap_usd_mm >= 1000].copy()); b2 = b[b.ind4.isin(["2010", "1510", "4530", "2020"])]; b201040 = b[b.ind6 == "201040"]
grid = [g for g in PEERS if g != HDE]
brows = []
def rec(label, sample, dummies, robust=None):
    X = design(sample, dummies); y = sample.log_ev_ebitda
    if robust == "huber": m = sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit()
    elif robust == "median": m = sm.QuantReg(y, X).fit(q=0.5, max_iter=5000)
    else: m = sm.OLS(y, X).fit(cov_type="HC1")
    res = y - m.predict(X); r_h = float(res.loc[HDE]) if HDE in res.index else np.nan
    pr = [float(res.loc[g]) for g in grid if g in res.index]
    brows.append(dict(model=label, n=int(len(y)), hde_actual=float(np.exp(y.loc[HDE])), hde_fitted=float(np.exp(y.loc[HDE] - r_h)), resid_log=r_h, pct_vs_fitted=np.exp(r_h) - 1,
                      grid_peer_median_resid=float(np.median(pr)), n_grid_peers_in=len(pr), hde_minus_grid_median=r_h - float(np.median(pr)),
                      resid_sd=float(res.std()), kor_coef=m.params.get("ctry_KOR", np.nan), hde_resid_percentile=float((res < r_h).mean())))
rec("broad m3: all industries, country + ind4", b, [("ctry", "OTH"), ("ind4", "2010")])
rec("broad m4: peer industries (house model)", b2, [("ctry", "OTH"), ("ind4", "2010")])
rec("broad m4, Huber", b2, [("ctry", "OTH"), ("ind4", "2010")], "huber"); rec("broad m4, median regression", b2, [("ctry", "OTH"), ("ind4", "2010")], "median")
rec("broad m4, EV/EBITDA trimmed 4x to 40x", b2[(b2.ev_ebitda >= 4) & (b2.ev_ebitda <= 40)], [("ctry", "OTH"), ("ind4", "2010")])
rec("electrical equipment 201040 only, country dummies", b201040, [("ctry", "OTH")])
broad = pd.DataFrame(brows); broad.to_csv(TABLES / "hde_multiples_broad.csv", index=False)
hde_row = d.loc[HDE, ["price", "shares_now", "mcap_usd_mm", "net_debt", "ev", "oibdp", "ev_ebitda", "ebitda_margin", "roic", "rev_cagr3", "nd_ebitda", "ctry", "ind4"]]

# ---------------- (c) own multiple history: EV / LTM EBITDA at quarter ends [WRDS data]
q = quarterly(); q["ltm"] = q.oibdpq.rolling(4).sum() / 1000; q["nc"] = (q.cheq - q.dlttq.fillna(0) - q.dlcq.fillna(0)) / 1000
px = prices().query("gvkey == @HDE").set_index("datadate").price
hist = []
for dt, r in q.loc["2021-12-31":].iterrows():
    if pd.isna(r.ltm) or r.ltm <= 0: continue
    p = px.asof(dt); ev = p * HDE_IN["shares_jun26"] / 1000 - r.nc
    hist.append(dict(quarter_end=dt.date(), price=p, ltm_ebitda=r.ltm, net_cash=r.nc, ev=ev, ev_ltm_ebitda=ev / r.ltm))
p = HDE_IN["price"]; hist.append(dict(quarter_end="now (latest-quarter LTM)", price=p, ltm_ebitda=q.ltm.iloc[-1], net_cash=q.nc.iloc[-1], ev=HDE_IN["ev"], ev_ltm_ebitda=HDE_IN["ev"] / q.ltm.iloc[-1]))
hist = pd.DataFrame(hist); hist.to_csv(TABLES / "hde_multiple_history.csv", index=False)

# ---------------- summary and reversion implication
fwd_specs = peer[peer.spec.str.startswith("fwd") & ~peer.spec.str.contains("only")]
m4 = broad.iloc[1]
summ = []
for lab, r in [("grid forward, median across specs (leave-HDE-out)", fwd_specs.resid_log.median()), ("grid forward, min", fwd_specs.resid_log.min()), ("grid forward, max", fwd_specs.resid_log.max()),
               ("broad m4 raw HDE residual", m4.resid_log), ("broad m4 HDE minus grid-peer median (reversion input)", m4.hde_minus_grid_median),
               ("broad robust range min (minus grid median)", (broad.resid_log - broad.grid_peer_median_resid).min()), ("broad robust range max (minus grid median)", (broad.resid_log - broad.grid_peer_median_resid).max()),
               ("HDE forward multiple vs grid forward median", np.log(HDE_IN["fwd_mult"] / S.drop(index=HDE).fwd.median()))]:
    summ.append(dict(basis=lab, resid_log=r, pct_vs_fitted=np.exp(r) - 1, multiple_change_12m_at_slope=np.exp(-SLOPE * r) - 1, multiple_change_24m_at_slope=np.exp(-2 * SLOPE * r) - 1))
summ = pd.DataFrame(summ); summ.to_csv(TABLES / "hde_multiples_summary.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 80)
print(S[keep].round(3).to_string()); print(peer.round(3).to_string()); print(broad.round(3).to_string()); print(hde_row.to_string())
print(hist.round(2).to_string()); print(summ.round(3).to_string())
print("broad n", len(b), "peer-ind n", len(b2), "201040 n", len(b201040), "grid peers in b2:", [NAME[g] for g in grid if g in b2.index])
