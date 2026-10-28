"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Amkor analysis 2: is Amkor's EV/EBITDA a discount after controls? (a) OSAT peer cross-section, forward (I/B/E/S FY1,
Valuation inputs sheet) and trailing (Compustat FY2025), leave-Amkor-out fits, small specs because n = 16 to 17;
(b) the broad-universe model of methodology/scenario/reg_multiples.py rebuilt here (same code path) with Amkor's residual and
robust variants; (c) the reversion implication at an assumed slope per year (SLOPE below; estimate your own from a multiples panel).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_multiples.py
Outputs: tables/amkr_multiples_osat_inputs.csv, amkr_multiples_osat_specs.csv, amkr_multiples_broad.csv, amkr_multiples_summary.csv. [WRDS data]
"""
import warnings; warnings.filterwarnings("ignore")
import numpy as np, pandas as pd, statsmodels.api as sm
from amkor_common import osat_set, XLSX, TABLES, AMKR, DATA, CACHE, fx, to_usd_rate
SLOPE = 0.25   # [placeholder: illustrative mean-reversion slope of the log multiple residual per year; estimate your own]
core = osat_set().set_index("gvkey")
# ---------------- (a) OSAT set from the deep dive [WRDS data: Compustat FY2025 accounts, I/B/E/S FY1, prices 2026-10-16]
x = pd.ExcelFile(XLSX); s = x.parse("Summary"); v = x.parse("Valuation inputs")
o = s.merge(v[["tic", "shares_mm", "price_local", "net_debt_local", "ebitda_fy1_local"]], on="tic")
o["gvkey"] = o.tic.map({r.tic: g for g, r in core.iterrows()} | {r["isin"]: g for g, r in core.iterrows()})
o = o.set_index("gvkey")
o["twn_chn"] = o["loc"].isin(["TWN", "CHN"]).astype(float); o["twn"] = (o["loc"] == "TWN").astype(float); o["chn"] = (o["loc"] == "CHN").astype(float)
o["log_mcap"] = np.log(o.market_cap); o["log_fwd"] = np.log(o.ev_to_ebitda_fwd); o["log_trail"] = np.log(o.ev_to_ebitda)
o["fwd_ebitda_growth"] = o.ebitda_fy1_usd / o.ebitda - 1
keep = ["conm", "loc", "market_cap", "ev_to_ebitda", "ev_to_ebitda_fwd", "est_sales_growth_fy1", "fwd_ebitda_growth", "rev_growth_1y", "rev_cagr_3y", "ebitda_margin", "roic", "net_debt_to_ebitda", "twn_chn"]
o[keep].round(3).to_csv(TABLES / "amkr_multiples_osat_inputs.csv")
SPECS = {
 "fwd: sales growth FY1": ("log_fwd", ["est_sales_growth_fy1"]),
 "fwd: EBITDA growth FY1": ("log_fwd", ["fwd_ebitda_growth"]),
 "fwd: growth + margin": ("log_fwd", ["est_sales_growth_fy1", "ebitda_margin"]),
 "fwd: growth + margin + ROIC": ("log_fwd", ["est_sales_growth_fy1", "ebitda_margin", "roic"]),
 "fwd: growth + margin + ROIC + leverage + size": ("log_fwd", ["est_sales_growth_fy1", "ebitda_margin", "roic", "net_debt_to_ebitda", "log_mcap"]),
 "fwd: growth + margin + TWN/CHN dummy": ("log_fwd", ["est_sales_growth_fy1", "ebitda_margin", "twn_chn"]),
 "fwd: growth + margin + ROIC + TWN/CHN": ("log_fwd", ["est_sales_growth_fy1", "ebitda_margin", "roic", "twn_chn"]),
 "fwd: TWN/CHN dummy only": ("log_fwd", ["twn_chn"]),
 "trail: 3y CAGR + margin": ("log_trail", ["rev_cagr_3y", "ebitda_margin"]),
 "trail: 1y growth + margin + ROIC": ("log_trail", ["rev_growth_1y", "ebitda_margin", "roic"]),
 "trail: growth + margin + ROIC + leverage + size": ("log_trail", ["rev_growth_1y", "ebitda_margin", "roic", "net_debt_to_ebitda", "log_mcap"]),
 "trail: growth + margin + TWN/CHN": ("log_trail", ["rev_growth_1y", "ebitda_margin", "twn_chn"]),
}
rows = []
for lab, (dep, cols) in SPECS.items():
    d = o.dropna(subset=[dep] + cols); peers = d.drop(index=AMKR)
    m = sm.OLS(peers[dep], sm.add_constant(peers[cols])).fit(cov_type="HC1")                      # leave-Amkor-out
    fit_a = float(m.predict(sm.add_constant(d.loc[[AMKR], cols], has_constant="add")).iloc[0])
    mi = sm.OLS(d[dep], sm.add_constant(d[cols])).fit(cov_type="HC1"); fit_in = float(mi.predict(sm.add_constant(d.loc[[AMKR], cols], has_constant="add")).iloc[0])
    act = float(d.loc[AMKR, dep])
    # peer median for reference
    rows.append(dict(spec=lab, n=int(mi.nobs), actual=np.exp(act), fitted_loo=np.exp(fit_a), resid_log_loo=act - fit_a, pct_vs_fitted_loo=np.exp(act - fit_a) - 1,
                     resid_log_in=act - fit_in, pct_vs_fitted_in=np.exp(act - fit_in) - 1, resid_sd=float(np.sqrt(m.scale)), r2=m.rsquared, adj_r2=m.rsquared_adj,
                     coefs="; ".join(f"{c} {m.params[c]:.2f} (t {m.tvalues[c]:.1f})" for c in cols), peer_median=float(np.exp(peers[dep].median()))))
osat = pd.DataFrame(rows); osat.to_csv(TABLES / "amkr_multiples_osat_specs.csv", index=False)

# ---------------- (b) broad-universe model, same construction as methodology/scenario/reg_multiples.py (trailing, price 2026-10-16, FY2024/25 accounts)
fxw = fx()
uni = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); uni["gvkey"] = uni.gvkey.str.zfill(6)
a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, low_memory=False)
a = a[(a.indfmt == "INDL")].copy(); a["gvkey"] = a.gvkey.str.zfill(6); a = a.sort_values(["gvkey", "fyear"])
a["sale_l3"] = a.groupby("gvkey").sale.shift(3)
last = a[a.fyear >= 2024].groupby("gvkey").tail(1).set_index("gvkey")
lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}).set_index("gvkey"); fy = pd.read_csv(CACHE / "price_at_fye.csv", dtype={"gvkey": str}).set_index("gvkey")
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
def design(x, dummies, winsor=True, ref=None):
    X = x[["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda", "log_mcap_usd"]].copy()
    if winsor:
        r = ref if ref is not None else X
        for c in ["roic", "rev_cagr3", "ebitda_margin", "nd_ebitda"]: X[c] = X[c].clip(r[c].quantile(0.01), r[c].quantile(0.99))
    for dcol, base in dummies:
        D = pd.get_dummies(x[dcol], prefix=dcol, dtype=float).drop(columns=[f"{dcol}_{base}"], errors="ignore"); X = pd.concat([X, D], axis=1)
    return sm.add_constant(X)
b = clean(d[d.mcap_usd_mm >= 1000].copy())
PEER_IND = ["2010", "1510", "4530", "2020"]  # the three scenario peer groups' industry groups (reg_multiples b2)
b2 = b[b.ind4.isin(PEER_IND)]; b3 = b[b.ind4 == "4530"]; b4 = b[b.ind6 == "453010"]
brows = []
def rec(label, sample, dummies, robust=None):
    X = design(sample, dummies); y = sample.log_ev_ebitda
    if robust == "huber": m = sm.RLM(y, X, M=sm.robust.norms.HuberT()).fit()
    elif robust == "median": m = sm.QuantReg(y, X).fit(q=0.5, max_iter=5000)
    else: m = sm.OLS(y, X).fit(cov_type="HC1")
    act = float(d.loc[AMKR, "log_ev_ebitda"]); fit_ = float(m.predict(X.loc[[AMKR]]).iloc[0]) if AMKR in X.index else np.nan
    osat_res = {g: float(m.resid.loc[g]) if hasattr(m, "resid") and g in m.resid.index else np.nan for g in core.index}
    brows.append(dict(model=label, n=int(m.nobs), amkr_actual=np.exp(act), amkr_fitted=np.exp(fit_), resid_log=act - fit_, pct_vs_fitted=np.exp(act - fit_) - 1,
                      resid_sd=float(np.sqrt(m.scale)) if hasattr(m, "scale") and m.scale is not None else np.nan, usa_coef=m.params.get("ctry_USA", np.nan), twn_coef=m.params.get("ctry_TWN", np.nan), chn_coef=m.params.get("ctry_CHN", np.nan),
                      osat_peer_median_resid=float(np.nanmedian([osat_res[g] for g in core.index if g != AMKR])), amkr_percentile_of_resid=float((m.resid < m.resid.loc[AMKR]).mean()) if hasattr(m, "resid") and AMKR in m.resid.index else np.nan))
rec("broad: all industries, country + ind4 dummies (reg_multiples m3)", b, [("ctry", "OTH"), ("ind4", "2010")])
rec("broad: peer industries 2010/1510/4530/2020 (reg_multiples m4)", b2, [("ctry", "OTH"), ("ind4", "2010")])
rec("broad m4, Huber", b2, [("ctry", "OTH"), ("ind4", "2010")], "huber"); rec("broad m4, median regression", b2, [("ctry", "OTH"), ("ind4", "2010")], "median")
rec("semis only (GICS 4530), country dummies", b3, [("ctry", "OTH"), ("ind6", "453010")])
rec("semis only (GICS 4530), no country dummies", b3, [("ind6", "453010")])
rec("semiconductors 453010 only, country dummies", b4, [("ctry", "OTH")])
trim = b2[(b2.ev_ebitda >= 4) & (b2.ev_ebitda <= 40)]; rec("broad m4, EV/EBITDA trimmed 4x to 40x", trim, [("ctry", "OTH"), ("ind4", "2010")])
broad = pd.DataFrame(brows); broad.to_csv(TABLES / "amkr_multiples_broad.csv", index=False)
# Amkor Compustat inputs for the record
ai = d.loc[AMKR, ["price", "shares_now", "mcap_usd_mm", "net_debt", "ev", "oibdp", "ev_ebitda", "ebitda_margin", "roic", "rev_cagr3", "nd_ebitda", "ctry", "ind4"]]

# ---------------- summary and reversion implication
summ = []
for lab, r in [("OSAT forward, median across specs (leave-Amkor-out)", osat[osat.spec.str.startswith("fwd")].resid_log_loo.median()),
               ("OSAT forward, min", osat[osat.spec.str.startswith("fwd")].resid_log_loo.min()), ("OSAT forward, max", osat[osat.spec.str.startswith("fwd")].resid_log_loo.max()),
               ("OSAT trailing, median across specs", osat[osat.spec.str.startswith("trail")].resid_log_loo.median()),
               ("broad m4 (peer industries)", broad.iloc[1].resid_log), ("broad robust range min", broad.resid_log.min()), ("broad robust range max", broad.resid_log.max()),
               ("semis-only 4530 with country", broad[broad.model.str.startswith("semis only (GICS 4530), country")].resid_log.iloc[0])]:
    summ.append(dict(basis=lab, resid_log=r, pct_vs_fitted=np.exp(r) - 1, multiple_change_12m_at_slope=np.exp(-SLOPE * r) - 1, multiple_change_24m_at_slope=np.exp(-2 * SLOPE * r) - 1))
summ = pd.DataFrame(summ); summ.to_csv(TABLES / "amkr_multiples_summary.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 70)
print(o[keep].round(3).to_string()); print(osat.round(3).to_string()); print(broad.round(3).to_string()); print(ai.to_string()); print(summ.round(3).to_string())
print("broad n", len(b), "peer-ind n", len(b2), "4530 n", len(b3), "453010 n", len(b4))
