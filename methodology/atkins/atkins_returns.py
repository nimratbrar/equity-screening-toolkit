"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

AtkinsRéalis analysis 1: weekly factor regressions, event dummies (HAC t, permutation p) and a daily event study
without the peer basket. ATRL has no daily history on disk (see atkins_common.py), so the dependent variables are
(i) Stantec (nearest Canadian consultancy with a daily series, NYSE USD line) as the ATRL proxy, (ii) the equal-weight
consultancy basket and (iii) the equal-weight nuclear basket. Market = US cap-weighted proxy; FX = log USD/CAD;
rates = weekly change in the US 10y (pp). All market data [WRDS data]; FRED series [source: FRED]; events from atkins_common.EVENTS [public sources].
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_returns.py
Outputs (methodology/atkins/tables/): atrl_factor_betas.csv, atrl_event_dummies_weekly.csv, atrl_event_pooled_perm.csv,
atrl_event_study_daily.csv, atrl_event_study_by_class.csv, atrl_basket_corr.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import norm
from atkins_common import tri_wide, us_market, usdcad, us10y, EVENTS, TABLES, CONSULT, NUCLEAR, PEERS, ASOF

tri = tri_wide(); usm = us_market(); cad = usdcad(); y10 = us10y()
START = ASOF - pd.DateOffset(years=5)
lr = lambda s: np.log(s).diff()
wk = lambda s: s.resample("W-FRI").last()
STN = "029985"
consult_ex_stn = [g for g in CONSULT if g in tri.columns and g != STN]
nuc = [g for g in NUCLEAR if g in tri.columns]
W = pd.DataFrame({
    "stantec": lr(wk(tri[STN])),
    "consult": lr(wk(tri[[g for g in CONSULT if g in tri.columns]])).mean(axis=1, skipna=True),
    "consult_ex_stn": lr(wk(tri[consult_ex_stn])).mean(axis=1, skipna=True),
    "nuclear": lr(wk(tri[nuc])).mean(axis=1, skipna=True),
    "mkt": usm.resample("W-FRI").sum(min_count=1),
    "dcad": lr(wk(cad)),                      # + = CAD weaker
    "d10y": wk(y10).diff(),                   # pp change in US 10y
}).loc[START:].dropna()

ev = pd.DataFrame(EVENTS, columns=["date", "label", "sign_atrl", "sign_peers", "cls"]); ev["date"] = pd.to_datetime(ev.date)
ev["week"] = [d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4) for d in ev.date]
ev = ev[ev.week.isin(W.index)].groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join),
    sign_atrl=("sign_atrl", lambda s: "/".join(dict.fromkeys(s))), sign_peers=("sign_peers", lambda s: "/".join(dict.fromkeys(s))), cls=("cls", lambda s: "/".join(dict.fromkeys(s))))
D = pd.DataFrame(0.0, index=W.index, columns=[f"ev_{i}" for i in ev.index])
for i, w in ev.week.items(): D.loc[w, f"ev_{i}"] = 1.0

def hac(yv, X, lags=4): return sm.OLS(yv, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
def orth(a, b): return sm.OLS(a, sm.add_constant(b)).fit().resid

rows = []
def add(dep, lab, m, k, extra=None):
    h1 = W.index < W.index[len(W) // 2]
    Xc = m.model.exog[:, 1:]; names = list(m.params.index[1:])
    mh1 = sm.OLS(W[dep][h1], sm.add_constant(pd.DataFrame(Xc, index=W.index, columns=names)[h1])).fit()
    mh2 = sm.OLS(W[dep][~h1], sm.add_constant(pd.DataFrame(Xc, index=W.index, columns=names)[~h1])).fit()
    rows.append(dict(dependent=dep, regressor=lab, beta=m.params[k], t_hac4=m.tvalues[k], t_hac8=hac(W[dep], pd.DataFrame(Xc, index=W.index, columns=names), 8).tvalues[k],
                     r2=m.rsquared, n_weeks=int(m.nobs), beta_first_half=mh1.params[k], beta_second_half=mh2.params[k], note=extra or ""))

for dep, basket in [("stantec", "consult_ex_stn"), ("consult", None), ("nuclear", None)]:
    X = W[["mkt", "dcad", "d10y"]].copy()
    if basket: X[basket] = W[basket]; X["nuclear"] = W["nuclear"]
    elif dep == "consult": X["nuclear"] = W["nuclear"]
    else: X["consult"] = W["consult"]
    m = hac(W[dep], X)
    for k in X.columns: add(dep, f"partial: {k}", m, k)
    # total market beta: baskets orthogonalised to the market
    Xo = X.copy()
    for k in [c for c in X.columns if c not in ("mkt", "dcad", "d10y")]: Xo[k] = orth(W[k], W["mkt"])
    mo = hac(W[dep], Xo); add(dep, "total market beta (baskets orthogonalised)", mo, "mkt")
    for k in [c for c in X.columns if c not in ("mkt", "dcad", "d10y")]: add(dep, f"{k} beta, orthogonalised", mo, k)
    md = hac(W[dep], pd.concat([X, D], axis=1)); add(dep, f"partial mkt with {D.shape[1]} event dummies", md, "mkt")
    if dep == "stantec":
        resid_s, m_dc, m_d = sm.OLS(W[dep], sm.add_constant(X)).fit().resid, sm.OLS(W[dep], sm.add_constant(pd.concat([X, D], axis=1))).fit(), md
bet = pd.DataFrame(rows); bet.to_csv(TABLES / "atrl_factor_betas.csv", index=False)
pd.DataFrame({"corr": W[["stantec", "consult", "nuclear", "mkt", "dcad", "d10y"]].corr().stack()}).to_csv(TABLES / "atrl_basket_corr.csv")

# single-week dummies on three dependents: classical t = abnormal / resid sd; factor-only residuals (market, FX, rates, other basket)
rng = np.random.default_rng(7); dums = []; resid = {}
for dep, X in [("stantec", W[["mkt", "dcad", "d10y", "consult_ex_stn", "nuclear"]]), ("consult", W[["mkt", "dcad", "d10y"]]), ("nuclear", W[["mkt", "dcad", "d10y"]])]:
    r = sm.OLS(W[dep], sm.add_constant(X)).fit().resid; resid[dep] = r; sd = float(r.std())
    mdc = sm.OLS(W[dep], sm.add_constant(pd.concat([X, D], axis=1))).fit()
    for i, e in ev.iterrows():
        k = f"ev_{i}"; ab = mdc.params[k]; t = mdc.tvalues[k]
        pp = float((np.abs(rng.choice(r.values, 5000)) >= abs(ab)).mean()) if abs(t) > 2 else np.nan
        dums.append(dict(dependent=dep, date=e.date.date(), week_ending=e.week.date(), event=e.label, cls=e.cls, sign_atrl=e.sign_atrl, sign_peers=e.sign_peers,
                         raw_weekly_return=W[dep][e.week], abnormal_weekly_return=ab, t_classical=t, permutation_p=pp, resid_sd_weekly=sd))
dums = pd.DataFrame(dums); dums.to_csv(TABLES / "atrl_event_dummies_weekly.csv", index=False)

pooled = []
def pool(dep, label, weeks):
    r = resid[dep]; k = len(weeks); stat = r.loc[weeks].mean(); sd = float(r.std())
    perm = np.array([r.sample(k, random_state=int(rng.integers(1e9))).mean() for _ in range(5000)])
    pooled.append(dict(dependent=dep, pool=label, n_event_weeks=k, mean_abnormal_weekly_return=stat, t_classical=stat / (sd / np.sqrt(k)),
                       permutation_p_two_sided=float((np.abs(perm) >= abs(stat)).mean()), share_positive=float((r.loc[weeks] > 0).mean())))
for dep, col in [("stantec", "sign_atrl"), ("consult", "sign_peers"), ("nuclear", "sign_peers")]:
    for s in ["+", "-"]:
        w = [e.week for e in ev.itertuples() if set(getattr(e, col).split("/")) - {"0", "co"} == {s}]
        if w: pool(dep, f"expected sign {s} ({col})", w)
    for c in ["nuclear_co", "ontario", "nuclear_macro", "infra", "mideast", "macro"]:
        w = [e.week for e in ev.itertuples() if c in e.cls.split("/")]
        if w: pool(dep, f"class {c}", w)
pooled = pd.DataFrame(pooled); pooled.to_csv(TABLES / "atrl_event_pooled_perm.csv", index=False)

# daily event study, market only (no basket), CAR(-1,+5), estimation [-260,-11], for Stantec and the two EW portfolios
dly = pd.DataFrame({"stantec": lr(tri[STN]), "consult": lr(tri[[g for g in CONSULT if g in tri.columns]]).mean(axis=1, skipna=True),
                    "nuclear": lr(tri[nuc]).mean(axis=1, skipna=True), "mkt": usm}).dropna()
es = []
for dep in ["stantec", "consult", "nuclear"]:
    for _, e in ev.iterrows():
        pos = dly.index.searchsorted(e.date); est = dly.iloc[max(0, pos - 260):pos - 10]; win = dly.iloc[pos - 1:pos + 6]
        if len(est) < 120 or len(win) < 7: continue
        mm = sm.OLS(est[dep], sm.add_constant(est[["mkt"]])).fit(); ar = win[dep] - mm.predict(sm.add_constant(win[["mkt"]], has_constant="add")); s = np.sqrt(mm.scale)
        es.append(dict(dependent=dep, date=e.date.date(), event=e.label, cls=e.cls, sign_atrl=e.sign_atrl, sign_peers=e.sign_peers, event_day_ar=ar.iloc[1], car_m1_p5=ar.sum(), t_car=ar.sum() / (s * np.sqrt(len(ar))), sd_car=s * np.sqrt(len(ar))))
es = pd.DataFrame(es); es.to_csv(TABLES / "atrl_event_study_daily.csv", index=False)
byc = []
for dep in ["stantec", "consult", "nuclear"]:
    e = es[es.dependent == dep]; col = "sign_atrl" if dep == "stantec" else "sign_peers"
    sets = [("expected +", e[e[col] == "+"]), ("expected -", e[e[col] == "-"])] + [(f"class {c}", e[e.cls.apply(lambda s: c in s.split("/"))]) for c in ["nuclear_co", "ontario", "nuclear_macro", "infra", "mideast", "macro"]]
    for lab, sel in sets:
        if len(sel) == 0: continue
        z = sel.car_m1_p5.sum() / np.sqrt((sel.sd_car ** 2).sum())
        byc.append(dict(dependent=dep, pool=lab, n_events=len(sel), mean_car_m1_p5=sel.car_m1_p5.mean(), share_positive=float((sel.car_m1_p5 > 0).mean()), z=z, p_two_sided=float(2 * (1 - norm.cdf(abs(z)))), bonferroni_threshold=0.05 / 24))
byc = pd.DataFrame(byc); byc.to_csv(TABLES / "atrl_event_study_by_class.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 45)
print(f"sample {W.index[0].date()} to {W.index[-1].date()}, n = {len(W)} weeks; events in sample {len(ev)}")
print(bet.round(3).to_string()); print(W[["stantec", "consult", "nuclear", "mkt", "dcad", "d10y"]].corr().round(2).to_string())
print(dums[dums.t_classical.abs() > 2].round(3).to_string()); print(pooled.round(3).to_string()); print(byc.round(3).to_string())
