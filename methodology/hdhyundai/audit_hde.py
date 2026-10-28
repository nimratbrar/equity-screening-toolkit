"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-hde audit: (1) FY2026e / FY2027e EBITDA rebuilt with a currency-split model; (2) results-week test on ALL
results weeks; (3) drawdown attribution on the equal-weight Korean proxy; (4) results-day reactions.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/audit_hde.py   (about 10 s; reads only local caches, no WRDS)
Outputs: tables/hde_audit_ebitda.csv, hde_audit_ebitda_bridge.csv, hde_audit_results_weeks.csv, hde_audit_attrib_ew.csv

EBITDA MODEL [inference on company-filing inputs]
 Facts [company filing: half-year report, results deck, audit report]: half-year sales, OP and Korea sales (hde_common.H1);
 D&A is a placeholder (the original used Compustat oibdpq - oiadpq). Exports = sales less Korea sales, converted to a
 USD-equivalent at the half-year average KRW/USD. Currency forwards are classified as trading (no hedge accounting), so their
 gains and losses go to finance income, BELOW operating profit [company filing]. Backlog KRW is converted at the company's
 'expected' rate (backlog KRW / backlog USD) [company filing].
 => Contract prices are fixed in USD (or GBP/EUR); EBITDA takes the spot rate on delivery, unhedged. Stronger won hurts.
 Model: revenue R(F) = Korea KRW + export USD-eq x F. Costs C(F) = C_ref x [(1 - c) + c x F / F_ref], with C_ref set so the
 EBITDA margin at F_ref equals the half-year margin plus an underlying change (repricing, mix, copper, start-up cost).
 c = USD-linked share of costs (copper, GOES, US plant), unsourced: 0.30 / 0.40 / 0.50 [inference, illustrative].
 EUR and GBP sales assumed to move with USD.
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from hde_common import TABLES, HDE, PEERS, PEER_LIST, tri_wide, tri_usd, kr_market, usd_per_local, HDE_IN, FX, H1, FWD_USD_M, FWD_RATE

rng = np.random.default_rng(20261020); N = 200_000
F1H, FQ3, SPOT = FX["avg_1h26"], FX["avg_q3"], FX["spot"]   # [placeholders in hde_common.FX; real values: FRED DEXKOUS]
F26AVG = FX["avg_ytd"]                              # year-to-date average [placeholder]
S1H, OP1H, DA1H, KR1H = H1["sales"], H1["op"], H1["da"], H1["korea_sales"]
EX1H_USD = (S1H - KR1H) / F1H * 1000                # USD m
M1H = (OP1H + DA1H) / S1H
H2FX = (FQ3 + SPOT) / 2                             # Q3 actual average, Q4 at spot [inference]

def ebitda(kr, ex_usd, fx, m_ref, c):
    r_ref = kr + ex_usd * F1H / 1000; c_ref = (1 - m_ref) * r_ref
    r = kr + ex_usd * fx / 1000; cost = c_ref * ((1 - c) + c * fx / F1H)
    return r, r - cost

T = lambda lo, md, hi, n=N: rng.triangular(lo, md, hi, n)
def model(n=N, central=False, g27=None, d27=None, fx27=SPOT, fx_h2=H2FX):
    if central:
        h2g, krh2, d26, kr27, c = 0.09, 490.0, 0.003, 1000.0, 0.40   # analyst assumptions [inference, illustrative]
        g = 0.13 if g27 is None else g27; d = 0.008 if d27 is None else d27
    else:
        h2g, krh2, d26, kr27, c = T(0.04, 0.09, 0.14, n), T(450, 490, 530, n), T(-0.005, 0.003, 0.010, n), T(920, 1000, 1080, n), T(0.30, 0.40, 0.50, n)
        g = T(0.05, 0.13, 0.22, n) if g27 is None else g27; d = T(-0.010, 0.008, 0.020, n) if d27 is None else d27
    exh2 = EX1H_USD * (1 + h2g)
    r2h, e2h = ebitda(krh2, exh2, fx_h2, M1H + d26, c)
    ex26 = EX1H_USD + exh2; ex27 = ex26 * (1 + g)
    r27, e27 = ebitda(kr27, ex27, fx27, M1H + d, c)
    return dict(sales26=S1H + r2h, ebitda26=OP1H + DA1H + e2h, sales27=r27, ebitda27=e27, margin27=e27 / r27, ex26_usd=ex26, ex27_usd=ex27)

rows = []
cen = model(central=True); sim = model()
for k in ["sales26", "ebitda26", "sales27", "ebitda27", "margin27", "ex26_usd", "ex27_usd"]:
    v = sim[k]; rows.append(dict(item=k, central=float(cen[k]), p05=np.quantile(v, .05), p10=np.quantile(v, .10), p50=np.median(v), p90=np.quantile(v, .90), p95=np.quantile(v, .95)))
# Q3'26 check for the scorecard: quarter = half of H2 export volume at Q3 FX, Korea 245, margin path as H2 [inference, illustrative]
q3 = {}
for lab, cc in (("Q3 at full FX pass-through (c 0.40)", 0.40), ("Q3 at c 0.50", 0.50)):
    r, e = ebitda(245.0, EX1H_USD * 1.09 / 2, FQ3, M1H + 0.003, cc); q3[lab] = (r, e, e - DA1H / 2)
    rows.append(dict(item=lab + ": sales / EBITDA / OP (D&A = half of the half-year D&A)", central=float(r), p50=float(e), p90=float(e - DA1H / 2)))
for lab, fx in (("FY2027 EBITDA central at 1,450 (backlog rate)", 1450.0), ("FY2027 EBITDA central at the YTD average", F26AVG), ("FY2027 EBITDA central at 1,250", 1250.0)):
    rows.append(dict(item=lab, central=float(model(central=True, fx27=fx)["ebitda27"])))
rows.append(dict(item="EBITDA elasticity to KRW/USD (central FY27, % per 1%)", central=float(np.log(model(central=True, fx27=SPOT * 1.01)["ebitda27"] / cen["ebitda27"]) / np.log(1.01))))
rows.append(dict(item="backlog KRW bn at spot vs company rate", central=HDE_IN["backlog_usd_m"] * SPOT / 1000))
rows.append(dict(item="forward book MTM at spot, KRW bn (USD forwards x (forward rate - spot)), non-operating", central=FWD_USD_M * (FWD_RATE - SPOT) / 1000))
rows.append(dict(item="EV / own FY2026e EBITDA (x)", central=HDE_IN["ev"] / float(cen["ebitda26"])))
rows.append(dict(item="EV / own FY2026e EBITDA, p50 of sim (x)", central=HDE_IN["ev"] / float(np.median(sim["ebitda26"]))))
E = pd.DataFrame(rows); E.to_csv(TABLES / "hde_audit_ebitda.csv", index=False)

# bridge consensus path -> quant -> audit [inference]
quant = 3.60 * SPOT * 0.262
br = [dict(step="consensus path (I/B/E/S FY1 EBITDA x FY2/FY1 EPS)", fy2027=HDE_IN["ebitda_fy1_cons"] * HDE_IN["eps_fy2"] / HDE_IN["eps_fy1"]),
      dict(step="audit model, consensus-like ops (export USD +20%, margin +2.0 pts) at the YTD average", fy2027=float(model(central=True, g27=0.20, d27=0.020, fx27=F26AVG)["ebitda27"])),
      dict(step="audit model, audit ops (export USD +13%, margin +0.8 pts) at the YTD average", fy2027=float(model(central=True, fx27=F26AVG)["ebitda27"])),
      dict(step="audit model, audit ops at spot (AUDIT CENTRAL)", fy2027=float(cen["ebitda27"])),
      dict(step="quant bottom-up: USD 3.60bn x spot x 26.2%", fy2027=quant),
      dict(step="quant ops (total USD +20%, margin +1.0) in audit model at spot", fy2027=float(model(central=True, g27=0.20, d27=0.010)["ebitda27"]))]
B = pd.DataFrame(br); B.to_csv(TABLES / "hde_audit_ebitda_bridge.csv", index=False)

# ---------------- results weeks: all nine on record vs the quant's four
tri = tri_wide(); tus = tri_usd(); krw = 1.0 / usd_per_local()["KRW"]
lr = lambda s: np.log(s).diff(); wk = lambda s: s.resample("W-FRI").last()
END = pd.Timestamp("2026-10-16"); NONKR = [g for g in PEER_LIST if PEERS[g][1] != "korea"]
W = pd.DataFrame({"hde": lr(wk(tri[HDE])), "kr_mkt": kr_market().resample("W-FRI").sum(min_count=1), "kr_ew": kr_market("kr_ew_logret").resample("W-FRI").sum(min_count=1),
                  "grid_xkr": lr(wk(tus[NONKR])).mean(axis=1, skipna=True), "dkrw": lr(wk(krw))}).dropna().loc[:END]
S = W.loc[END - pd.DateOffset(years=3):]
REPORT = ["2024-07-25", "2024-10-24", "2025-02-05", "2025-04-25", "2025-07-25", "2025-10-23", "2026-02-06", "2026-04-28", "2026-07-28"]  # results dates [company filing; public]
QUANT4 = ["2025-04-25", "2026-02-06", "2026-04-28", "2026-07-28"]
wkof = lambda d: (pd.Timestamp(d) + pd.offsets.Week(weekday=4)) if pd.Timestamp(d).weekday() != 4 else pd.Timestamp(d)
out = []
for fac, cols in (("M1 cap-weighted", ["kr_mkt", "grid_xkr", "dkrw"]), ("M1 equal-weight", ["kr_ew", "grid_xkr", "dkrw"])):
    res = sm.OLS(S.hde, sm.add_constant(S[cols])).fit().resid
    for lab, dates in (("quant's 4 weeks", QUANT4), ("all 9 results weeks", REPORT)):
        w = [wkof(d) for d in dates]; x = res.loc[w]; k = len(w)
        perm = np.array([res.sample(k, random_state=int(rng.integers(1e9))).mean() for _ in range(20000)])
        out.append(dict(factors=fac, pool=lab, n=k, mean_abnormal=x.mean(), t=x.mean() / (res.std() / np.sqrt(k)), perm_p=float((np.abs(perm) >= abs(x.mean())).mean()),
                        share_negative=float((x < 0).mean()), weeks="; ".join(f"{d.date()} {v:+.3f}" for d, v in x.items())))
d = tri[HDE].dropna(); dr = np.log(d).diff()
for dt in REPORT:
    t0 = d.index[d.index >= pd.Timestamp(dt)][0]; i = d.index.get_loc(t0)
    out.append(dict(factors="daily", pool="results day t and t+1 log return", weeks=f"{dt}: {dr.iloc[i]:+.3f} / {dr.iloc[i + 1]:+.3f}", mean_abnormal=dr.iloc[i] + dr.iloc[i + 1]))
R = pd.DataFrame(out); R.to_csv(TABLES / "hde_audit_results_weeks.csv", index=False)

# ---------------- 12m and peak-to-now attribution on the equal-weight proxy (2y betas)
two = W.loc[END - pd.DateOffset(years=2):]; att = []
for fac, cols in (("cap-weighted", ["kr_mkt", "grid_xkr", "dkrw"]), ("equal-weight", ["kr_ew", "grid_xkr", "dkrw"])):
    m = sm.OLS(two.hde, sm.add_constant(two[cols])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    for lab, a, b in (("calendar 12m", "2025-10-17", END), ("peak to now", tri[HDE].loc["2025-10-17":END].idxmax(), END)):
        ww = W.loc[a:b]; r = dict(proxy=fac, window=lab, actual=ww.hde.sum(), beta_mkt=m.params[cols[0]], t_mkt=m.tvalues[cols[0]], mkt_factor_sum=ww[cols[0]].sum())
        for c_ in cols: r["contrib_" + c_.replace("kr_ew", "kr_mkt")] = m.params[c_] * ww[c_].sum()
        r["residual"] = r["actual"] - sum(r[k] for k in r if k.startswith("contrib_")); att.append(r)
A = pd.DataFrame(att); A.to_csv(TABLES / "hde_audit_attrib_ew.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 140)
print(E.round(3).to_string()); print(B.round(1).to_string()); print(R.round(4).to_string()); print(A.round(3).to_string())
