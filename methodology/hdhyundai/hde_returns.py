"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

HDE analysis 1: price check, drawdown decomposition, weekly factor regressions (HAC), event dummies with permutation p,
daily event study, multiple-testing correction (Bonferroni and Holm).
Factors: Korean market = cap-weighted Korean universe ex HDE (KRW) [WRDS data, inference: no KOSPI on disk]; grid basket ex Korea =
equal-weight weekly USD log return of the non-Korean grid peers; Korean transformer pair = Hyosung HI + LS Electric (KRW);
dKRW = weekly log change in KRW per USD (fx_daily, + = won weaker) [WRDS data]. Events: hde_common.EVENTS (public news and policy dates).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_returns.py
Outputs (methodology/hdhyundai/tables/): hde_price_check.csv, hde_window_returns.csv, hde_drawdown_decomp.csv, hde_valuation_bridge.csv,
hde_factor_betas.csv, hde_event_dummies_weekly.csv, hde_event_pooled.csv, hde_event_study_daily.csv, hde_top_days.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import norm
from hde_common import (HDE, PEERS, PEER_LIST, KOREA, TRANSFORMER, NAME, EVENTS, TABLES, HDE_IN, tri_wide, tri_usd, kr_market,
                        usd_per_local, quarterly, prices)

rng = np.random.default_rng(20261020)
tri = tri_wide(); tus = tri_usd(); mk = kr_market(); mk_ew = kr_market("kr_ew_logret")
krw = 1.0 / usd_per_local()["KRW"]                                   # KRW per USD
lr = lambda s: np.log(s).diff()
wk = lambda s: s.resample("W-FRI").last()
END = pd.Timestamp("2026-10-16"); PEAK = tri[HDE].loc["2025-10-16":END].idxmax()
NONKR = [g for g in PEER_LIST if PEERS[g][1] != "korea"]; PAIR = ["327718", "207909"]

# ---------------- 1. price check [WRDS data]
px = prices().query("gvkey == @HDE").set_index("datadate").sort_index()
y1 = px.loc["2025-10-17":END]
last = px.price.loc[:END].iloc[-1]
c12 = px.price.loc[:"2025-10-16"].iloc[-1]; t12 = px.tri.loc[:"2025-10-16"].iloc[-1]
r252 = px.price.iloc[-253] if len(px) > 253 else np.nan
chk = pd.DataFrame([
    dict(item="last close on disk", date=str(END.date()), value=last),
    dict(item="52-week high close", date=str(y1.price.idxmax().date()), value=y1.price.max()),
    dict(item="52-week low close", date=str(y1.price.idxmin().date()), value=y1.price.min()),
    dict(item="close 2025-10-16 (calendar 12m start)", date="2025-10-16", value=c12),
    dict(item="12m price return, calendar (16 Oct to 16 Oct)", date="", value=last / c12 - 1),
    dict(item="12m total return, calendar", date="", value=px.tri.loc[:END].iloc[-1] / t12 - 1),
    dict(item="252-row return (deep dive method; rows include holidays, starts " + str(px.index[-253].date()) + ")", date=str(px.index[-253].date()), value=last / r252 - 1),
    dict(item="from 52-week high close", date="", value=last / y1.price.max() - 1),
    dict(item="external quote to reconcile against (unverified)", date="", value=np.nan),   # [placeholder: a third-party quote, if any]
    dict(item="scenarios file 52-week range (intraday, unverified)", date="", value=np.nan),
])
chk.to_csv(TABLES / "hde_price_check.csv", index=False)

# ---------------- 2. window returns (local TRI and USD), peers and factors
WIN = [("calendar 12m", "2025-10-16", END), ("run-up: 12m start to HDE peak", "2025-10-16", PEAK), ("peak to now", PEAK, END),
       ("peak to pre-Q2 (24 Jul)", PEAK, "2026-07-24"), ("Q2 results week (27-31 Jul)", "2026-07-24", "2026-07-31"), ("post-Q2 to now", "2026-07-31", END),
       ("deep dive 252 rows", px.index[-253], END)]
def wret(s, a, b):
    s = s.dropna(); a, b = pd.Timestamp(a), pd.Timestamp(b)
    return s.loc[:b].iloc[-1] / s.loc[:a].iloc[-1] - 1 if len(s.loc[:a]) else np.nan
names = [HDE] + PEER_LIST
rows = []
mk_idx = np.exp(mk.cumsum()); mk_ew_idx = np.exp(mk_ew.cumsum())
grid_xkr_usd = np.exp(lr(tus[NONKR]).mean(axis=1, skipna=True).fillna(0).cumsum())
for lab, a, b in WIN:
    r = dict(window=lab, start=str(pd.Timestamp(a).date()), end=str(pd.Timestamp(b).date()))
    for g in names: r[NAME[g]] = wret(tri[g], a, b)
    r["KR market (cap-wt)"] = wret(mk_idx, a, b); r["KR market (EW)"] = wret(mk_ew_idx, a, b)
    r["grid ex-Korea EW (USD)"] = wret(grid_xkr_usd, a, b); r["KRW per USD"] = wret(krw.dropna(), a, b)
    for g in names: r[NAME[g] + " (USD)"] = wret(tus[g], a, b)
    rows.append(r)
wr = pd.DataFrame(rows); wr.to_csv(TABLES / "hde_window_returns.csv", index=False)
# peaks of each name inside the last 12m
pk = pd.DataFrame([dict(name=NAME[g], peak_date=tri[g].loc["2025-10-17":END].idxmax().date(), from_peak=tri[g].loc[:END].iloc[-1] / tri[g].loc["2025-10-17":END].max() - 1,
                        ret_12m=wret(tri[g], "2025-10-16", END)) for g in names]).sort_values("from_peak")

# ---------------- 3. weekly regressions
W = pd.DataFrame({"hde": lr(wk(tri[HDE])), "kr_mkt": mk.resample("W-FRI").sum(min_count=1), "kr_ew": mk_ew.resample("W-FRI").sum(min_count=1),
                  "grid_xkr": lr(wk(tus[NONKR])).mean(axis=1, skipna=True), "kr_pair": lr(wk(tri[PAIR])).mean(axis=1), "dkrw": lr(wk(krw))}).dropna()
W = W.loc[:END]
def hac(y, X, lags=4): return sm.OLS(y, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
def orth(a, X): return sm.OLS(a, sm.add_constant(X)).fit().resid
SAMPLES = {"2y": (END - pd.DateOffset(years=2), END), "5y": (END - pd.DateOffset(years=5), END), "3y (event sample)": (END - pd.DateOffset(years=3), END)}
brows = []; fits = {}
for sl, (a, b) in SAMPLES.items():
    S = W.loc[a:b]
    specs = {"M1 market + grid ex-KR + KRW": ["kr_mkt", "grid_xkr", "dkrw"],
             "M2 M1 + KR transformer pair": ["kr_mkt", "grid_xkr", "dkrw", "kr_pair"],
             "M3 EW Korean market + grid ex-KR + KRW": ["kr_ew", "grid_xkr", "dkrw"]}
    for sp, cols in specs.items():
        X = S[cols].copy()
        if "kr_pair" in cols: X["kr_pair"] = orth(S.kr_pair, S[["kr_mkt", "grid_xkr", "dkrw"]])   # pair beyond market, basket, FX
        m = hac(S.hde, X); m8 = hac(S.hde, X, 8); fits[(sl, sp)] = (m, X)
        Xo = X.copy(); mcol = cols[0]
        for c in [c for c in cols if c not in (mcol, "dkrw", "kr_pair")]: Xo[c] = orth(S[c], S[[mcol]])
        mo = hac(S.hde, Xo)
        h = S.index < S.index[len(S) // 2]
        m1 = sm.OLS(S.hde[h], sm.add_constant(X[h])).fit(); m2 = sm.OLS(S.hde[~h], sm.add_constant(X[~h])).fit()
        for c in cols:
            brows.append(dict(sample=sl, spec=sp, regressor=c, beta=m.params[c], t_hac4=m.tvalues[c], t_hac8=m8.tvalues[c], beta_first_half=m1.params[c], beta_second_half=m2.params[c],
                              total_beta_basket_orth=mo.params[c], r2=m.rsquared, n_weeks=int(m.nobs), alpha_weekly=m.params["const"], alpha_t=m.tvalues["const"]))
bet = pd.DataFrame(brows); bet.to_csv(TABLES / "hde_factor_betas.csv", index=False)
corr = W.loc[SAMPLES["2y"][0]:].corr()

# ---------------- 4. drawdown decomposition (2y M1 and M2 betas applied to cumulative weekly factor sums)
dec = []
evw = {}
for d_, lab_, s_, c_, k_ in EVENTS:
    d0 = pd.Timestamp(d_); w = d0 + pd.offsets.Week(weekday=4) if d0.weekday() != 4 else d0; evw.setdefault(w, []).append((lab_, k_))
RES_WEEKS = {w for w, v in evw.items() if any(k == "company" for _, k in v)}
for sp in ["M1 market + grid ex-KR + KRW", "M2 M1 + KR transformer pair"]:
    m, X = fits[("2y", sp)]
    for lab, a, b in WIN[:6]:
        a, b = pd.Timestamp(a), pd.Timestamp(b); ix = (W.index > a) & (W.index <= b + pd.Timedelta(days=6)) & (W.index <= END)
        ix = W.index[ix]; ix = ix[ix.isin(X.index)]
        if len(ix) == 0: continue
        act = W.hde.loc[ix].sum(); r = dict(spec=sp, window=lab, weeks=len(ix), actual_log=act, actual_pct=np.exp(act) - 1)
        tot = 0.0
        for c in X.columns:
            v = m.params[c] * X.loc[ix, c].sum(); r[f"contrib_{c}"] = v; tot += v
        r["contrib_alpha"] = m.params["const"] * len(ix); tot += r["contrib_alpha"]
        resid = W.hde.loc[ix] - m.predict(sm.add_constant(X.loc[ix], has_constant="add"))
        r["residual_results_weeks"] = resid[resid.index.isin(RES_WEEKS)].sum(); r["residual_other"] = resid[~resid.index.isin(RES_WEEKS)].sum()
        r["n_results_weeks"] = int(resid.index.isin(RES_WEEKS).sum()); dec.append(r)
dec = pd.DataFrame(dec); dec.to_csv(TABLES / "hde_drawdown_decomp.csv", index=False)

# ---------------- 5. valuation bridge: price = EV/LTM EBITDA x LTM EBITDA (+ net cash), LTM as reported by each date [WRDS data]
q = quarterly()
q["oibdp_ltm"] = q.oibdpq.rolling(4).sum() / 1000; q["netcash"] = (q.cheq - q.dlttq.fillna(0) - q.dlcq.fillna(0)) / 1000   # KRW bn
REPORT = {"2025-06-30": "2025-07-25", "2025-09-30": "2025-10-23", "2025-12-31": "2026-02-06", "2026-03-31": "2026-04-28", "2026-06-30": "2026-07-29",
          "2025-03-31": "2025-04-25", "2024-12-31": "2025-02-05", "2024-09-30": "2024-10-24", "2024-06-30": "2024-07-25"}   # results dates [company filing; inference for 2024-25 days]
def ltm_at(d):
    d = pd.Timestamp(d); ok = [pd.Timestamp(k) for k, v in REPORT.items() if pd.Timestamp(v) <= d]; k = max(ok)
    return k, q.loc[k, "oibdp_ltm"], q.loc[k, "netcash"]
sh = HDE_IN["shares_jun26"]; brg = []
for lab, d in [("12m start", "2025-10-16"), ("HDE peak", PEAK), ("pre-Q2 results", "2026-07-24"), ("now", END)]:
    k, e, nc = ltm_at(d); p = tri[HDE].index.asof(pd.Timestamp(d)); price = px.price.asof(pd.Timestamp(d))
    ev = price * sh / 1000 - nc
    brg.append(dict(point=lab, date=str(pd.Timestamp(d).date()), price=price, ltm_quarter=str(k.date()), ltm_ebitda=e, net_cash=nc, ev=ev, ev_ltm_ebitda=ev / e))
brg = pd.DataFrame(brg)
for i in range(1, len(brg)):
    a, b = brg.iloc[i - 1], brg.iloc[i]
    brg.loc[i, "dlog_price"] = np.log(b.price / a.price); brg.loc[i, "dlog_ltm_ebitda"] = np.log(b.ltm_ebitda / a.ltm_ebitda)
    brg.loc[i, "dlog_multiple"] = np.log(b.ev_ltm_ebitda / a.ev_ltm_ebitda)
    brg.loc[i, "net_cash_term"] = brg.loc[i, "dlog_price"] - brg.loc[i, "dlog_ltm_ebitda"] - brg.loc[i, "dlog_multiple"]
a, b = brg.iloc[0], brg.iloc[-1]
brg = pd.concat([brg, pd.DataFrame([dict(point="12m total", dlog_price=np.log(b.price / a.price), dlog_ltm_ebitda=np.log(b.ltm_ebitda / a.ltm_ebitda), dlog_multiple=np.log(b.ev_ltm_ebitda / a.ev_ltm_ebitda))])])
a = brg.iloc[1]; brg = pd.concat([brg, pd.DataFrame([dict(point="peak to now", dlog_price=np.log(b.price / a.price), dlog_ltm_ebitda=np.log(b.ltm_ebitda / a.ltm_ebitda), dlog_multiple=np.log(b.ev_ltm_ebitda / a.ev_ltm_ebitda))])])
brg.to_csv(TABLES / "hde_valuation_bridge.csv", index=False)

# ---------------- 6. event dummies, weekly, 3y sample, M1 factors (no pair: the pair absorbs sector-wide news)
a3 = SAMPLES["3y (event sample)"][0]; S = W.loc[a3:]
ev = pd.DataFrame(EVENTS, columns=["date", "label", "sign_hde", "sign_peers", "cls"]); ev["date"] = pd.to_datetime(ev.date)
ev["week"] = [d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4) for d in ev.date]
ev = ev[ev.week.isin(S.index)].groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join),
     sign_hde=("sign_hde", lambda s: "/".join(dict.fromkeys(s))), sign_peers=("sign_peers", lambda s: "/".join(dict.fromkeys(s))), cls=("cls", lambda s: "/".join(dict.fromkeys(s))))
D = pd.DataFrame(0.0, index=S.index, columns=[f"ev_{i}" for i in ev.index])
for i, w in ev.week.items(): D.loc[w, f"ev_{i}"] = 1.0
dums, resid = [], {}
for dep, cols in [("hde", ["kr_mkt", "grid_xkr", "dkrw"]), ("kr_pair", ["kr_mkt", "grid_xkr", "dkrw"])]:
    r0 = sm.OLS(S[dep], sm.add_constant(S[cols])).fit().resid; resid[dep] = r0
    md = sm.OLS(S[dep], sm.add_constant(pd.concat([S[cols], D], axis=1))).fit()
    for i, e in ev.iterrows():
        k = f"ev_{i}"; ab = md.params[k]
        pp = float((np.abs(r0.values) >= abs(ab)).mean())                        # empirical p from factor-only residual weeks
        dums.append(dict(dependent=dep, date=e.date.date(), week_ending=e.week.date(), event=e.label, cls=e.cls, sign_hde=e.sign_hde, sign_peers=e.sign_peers,
                         raw_weekly_return=S[dep][e.week], abnormal_weekly=ab, t_classical=md.tvalues[k], perm_p=pp))
dums = pd.DataFrame(dums)
for dep in dums.dependent.unique():
    m_ = dums.dependent == dep; n = m_.sum(); p = dums.loc[m_, "perm_p"].values; o = np.argsort(p)
    holm = np.empty(n); run = 0
    for j, ix in enumerate(o): run = max(run, min(1.0, (n - j) * p[ix])); holm[ix] = run
    dums.loc[m_, "bonferroni_p"] = np.minimum(1, p * n); dums.loc[m_, "holm_p"] = holm; dums.loc[m_, "n_tests"] = n
dums.to_csv(TABLES / "hde_event_dummies_weekly.csv", index=False)

pooled = []
def pool(dep, label, weeks, signs=None):
    r = resid[dep]; k = len(weeks)
    x = r.loc[weeks].values * (np.array(signs) if signs is not None else 1.0); stat = x.mean(); sd = float(r.std())
    perm = np.array([r.sample(k, random_state=int(rng.integers(1e9))).values.mean() for _ in range(5000)])
    if signs is not None:
        perm = np.array([(r.sample(k, random_state=int(rng.integers(1e9))).values * np.array(signs)).mean() for _ in range(5000)])
    pooled.append(dict(dependent=dep, pool=label, n_weeks=k, mean_abnormal_weekly=stat, t_classical=stat / (sd / np.sqrt(k)),
                       perm_p_two_sided=float((np.abs(perm) >= abs(stat)).mean()), share_positive=float((x > 0).mean())))
for dep, col in [("hde", "sign_hde"), ("kr_pair", "sign_peers")]:
    sg = [(e.week, 1.0 if set(getattr(e, col).split("/")) - {"0", "co"} == {"+"} else -1.0) for e in ev.itertuples() if set(getattr(e, col).split("/")) - {"0", "co"} in ({"+"}, {"-"})]
    pool(dep, "all signed macro events (sign-adjusted)", [w for w, _ in sg], [s for _, s in sg])
    for s in ["+", "-"]:
        w = [e.week for e in ev.itertuples() if set(getattr(e, col).split("/")) - {"0", "co"} == {s}]
        if w: pool(dep, f"expected {s}", w)
    for c in ["trade", "us_demand", "supply", "korea", "company"]:
        w = [e.week for e in ev.itertuples() if c in e.cls.split("/")]
        if w: pool(dep, f"class {c}", w)
pooled = pd.DataFrame(pooled); n = len(pooled); p = pooled.perm_p_two_sided.values; o = np.argsort(p); holm = np.empty(n); run = 0
for j, ix in enumerate(o): run = max(run, min(1.0, (n - j) * p[ix])); holm[ix] = run
pooled["bonferroni_p"] = np.minimum(1, p * n); pooled["holm_p"] = holm; pooled["n_tests"] = n
pooled.to_csv(TABLES / "hde_event_pooled.csv", index=False)

# ---------------- 7. daily event study, market-only model, CAR(-1,+5)
dly = pd.DataFrame({"hde": lr(tri[HDE]), "kr_pair": lr(tri[PAIR]).mean(axis=1), "mkt": mk}).dropna().loc[:END]
es = []
for dep in ["hde", "kr_pair"]:
    for _, e in ev.iterrows():
        pos = dly.index.searchsorted(e.date); est = dly.iloc[max(0, pos - 260):pos - 10]; win = dly.iloc[pos - 1:pos + 6]
        if len(est) < 120 or len(win) < 7: continue
        mm = sm.OLS(est[dep], sm.add_constant(est[["mkt"]])).fit(); ar = win[dep] - mm.predict(sm.add_constant(win[["mkt"]], has_constant="add")); s = np.sqrt(mm.scale)
        es.append(dict(dependent=dep, date=e.date.date(), event=e.label, cls=e.cls, sign_hde=e.sign_hde, car_m1_p5=ar.sum(), z=ar.sum() / (s * np.sqrt(len(ar))), sd_car=s * np.sqrt(len(ar))))
es = pd.DataFrame(es); es["p_two_sided"] = 2 * (1 - norm.cdf(es.z.abs()))
for dep in es.dependent.unique():
    m_ = es.dependent == dep; es.loc[m_, "bonferroni_p"] = np.minimum(1, es.loc[m_, "p_two_sided"] * m_.sum())
es.to_csv(TABLES / "hde_event_study_daily.csv", index=False)

# ---------------- 8. largest daily moves in the last 12m, with market and pair
dd = pd.DataFrame({"hde": lr(tri[HDE]), "kr_mkt": mk, "kr_pair": lr(tri[PAIR]).mean(axis=1), "dkrw": lr(krw)}).loc["2025-10-17":END].dropna()
top = dd.reindex(dd.hde.abs().sort_values(ascending=False).index).head(15).copy()
ev_d = {pd.Timestamp(d): l for d, l, *_ in EVENTS}
top["event_within_2d"] = [", ".join(l for d, l in ev_d.items() if 0 <= (t - d).days <= 2) for t in top.index]
top.to_csv(TABLES / "hde_top_days.csv")

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 50)
print(chk.to_string()); print("HDE peak", PEAK.date())
print(wr[["window", "start", "end", "HDE", "Hyosung HI", "LS Electric", "Hitachi", "Siemens Energy", "GE Vernova", "KR market (cap-wt)", "KR market (EW)", "grid ex-Korea EW (USD)", "KRW per USD"]].round(3).to_string())
print(pk.round(3).to_string())
print(bet[bet["sample"] == "2y"].round(3).to_string()); print(bet[bet["sample"] == "5y"][["spec", "regressor", "beta", "t_hac4", "r2"]].round(3).to_string())
print(corr.round(2).to_string())
print(dec.round(3).to_string()); print(brg.round(3).to_string())
print(dums[(dums.perm_p < 0.1)].round(3).to_string()); print(pooled.round(3).to_string())
print(es[es.dependent == "hde"].sort_values("p_two_sided").head(8).round(3).to_string()); print(top.round(3).to_string())
