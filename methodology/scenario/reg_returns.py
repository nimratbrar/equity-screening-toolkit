"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Analysis 1: factor and event-dummy regressions of weekly log returns (5 years) for the 4 cases,
plus a daily event study (CAR -1 to +5 trading days) as a robustness check.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/reg_returns.py
Outputs: tables/factor_betas.csv, tables/event_dummies_weekly.csv, tables/event_signed_pooled.csv,
         tables/event_study_daily.csv, tables/copper_monthly_cable.csv. All market data [WRDS data].
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from reg_common import (universe_core, tri_wide, indices, fx, copper_monthly, CASES, EVENTS_GRID, EVENTS_SEMIS, TABLES, ASOF)

core = universe_core(); tri = tri_wide(); idx = indices(); fxw = fx()
START = ASOF - pd.DateOffset(years=5)
lr = lambda s: np.log(s).diff()

def weekly(s): return lr(s.resample("W-FRI").last())
def basket(gv, group, freq="W-FRI"):
    peers = core[(core.group == group) & (core.gvkey != gv)].gvkey.tolist()
    r = lr(tri[peers].resample(freq).last()) if freq else lr(tri[peers])
    return r.mean(axis=1, skipna=True)

SPEC = {  # case -> (group, market indices [primary, alt], fx column, event list, sign column index)
 "246217": ("cable_grid", ["STOXX50", "CAC40"], "EURUSD", [(d, l, s) for d, l, s in EVENTS_GRID]),
 "220629": ("fab_water_facility", ["TOPIX", "NIKKEI"], "USDJPY", [(d, l, s[0]) for d, l, *s in EVENTS_SEMIS]),
 "311307": ("fab_water_facility", ["TOPIX", "NIKKEI"], "USDJPY", [(d, l, s[1]) for d, l, *s in EVENTS_SEMIS]),
 "100697": ("chip_materials_and_chem", ["TOPIX", "NIKKEI"], "USDJPY", [(d, l, s[2]) for d, l, *s in EVENTS_SEMIS]),
}
MEANING = {"mkt": "pct move in the stock per 1 pct move in the local market index (market beta)",
           "sector": "pct move per 1 pct move in the equal-weight peer basket, after the market (sector beta)",
           "fx": "pct move per 1 pct rise in USD/JPY (yen weakens) or EUR/USD (euro strengthens)",
           "copper": "pct move per 1 pct rise in the monthly copper price"}

betas, dums, pooled, evstudy = [], [], [], []
for gv, (group, mkts, fxcol, events) in SPEC.items():
    name = CASES[gv]
    y = weekly(tri[gv]).rename("ret")
    X = pd.DataFrame({"mkt": weekly(idx[mkts[0]]), "sector": basket(gv, group), "fx": weekly(fxw[fxcol])})
    df = pd.concat([y, X], axis=1).loc[START:].dropna()
    # event-week dummies
    ev = pd.DataFrame(events, columns=["date", "label", "sign"]); ev["date"] = pd.to_datetime(ev.date)
    ev["week"] = ev.date + pd.offsets.Week(weekday=4) - pd.offsets.Week(weekday=4) * 0  # Friday on/after
    ev["week"] = [d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4) for d in ev.date]
    ev = ev[ev.week.isin(df.index)]
    # events that fall in the same trading week share one dummy (otherwise the design matrix is rank-deficient)
    ev = ev.groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join), sign=("sign", lambda s: "/".join(dict.fromkeys(s))))
    D = pd.DataFrame(0.0, index=df.index, columns=[f"ev_{i}" for i in ev.index])
    for i, w in ev.week.items(): D.loc[w, f"ev_{i}"] = 1.0
    XX = sm.add_constant(pd.concat([df[["mkt", "sector", "fx"]], D], axis=1))
    m = sm.OLS(df.ret, XX).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    m_cl = sm.OLS(df.ret, XX).fit()  # classical SE: for a one-week dummy the HAC SE is degenerate, so dummy t = abnormal / resid sd
    m0 = sm.OLS(df.ret, sm.add_constant(df[["mkt", "sector", "fx"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    for k in ["mkt", "sector", "fx"]:
        betas.append(dict(case=name, market_index=mkts[0], regressor=k, beta=m.params[k], t_hac=m.tvalues[k], beta_no_dummies=m0.params[k],
                          r2_with_dummies=m.rsquared, r2_factors_only=m0.rsquared, n_weeks=int(m.nobs), sample=f"{df.index[0].date()} to {df.index[-1].date()}", meaning=MEANING[k]))
    # alt market index
    Xa = X.copy(); Xa["mkt"] = weekly(idx[mkts[1]]); dfa = pd.concat([y, Xa], axis=1).loc[START:].dropna()
    ma = sm.OLS(dfa.ret, sm.add_constant(dfa[["mkt", "sector", "fx"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    betas.append(dict(case=name, market_index=mkts[1], regressor="mkt", beta=ma.params["mkt"], t_hac=ma.tvalues["mkt"], beta_no_dummies=ma.params["mkt"],
                      r2_with_dummies=np.nan, r2_factors_only=ma.rsquared, n_weeks=int(ma.nobs), sample=f"{dfa.index[0].date()} to {dfa.index[-1].date()}", meaning="alt index market beta (factors only)"))
    resid_sd = float(np.sqrt(m.scale))
    for i, r in ev.iterrows():
        k = f"ev_{i}"
        dums.append(dict(case=name, date=r.date.date(), week_ending=r.week.date(), event=r.label, expected_sign=r.sign,
                         abnormal_weekly_return=m.params[k], t_classical=m_cl.tvalues[k], raw_weekly_return=df.ret[r.week], resid_sd_weekly=resid_sd, n_obs_for_dummy=1))
    # pooled signed dummies (several weeks per dummy: the only version with any statistical weight)
    P = pd.DataFrame(0.0, index=df.index, columns=["ev_pos", "ev_neg", "ev_company", "ev_zero_or_mixed"])
    for i, r in ev.iterrows():
        signs = set(r.sign.split("/")) - {"0"}
        col = "ev_pos" if signs == {"+"} else "ev_neg" if signs == {"-"} else "ev_company" if signs == {"co"} else "ev_zero_or_mixed"
        P.loc[r.week, col] = 1.0
    P = P.loc[:, P.sum() > 0]
    Xp = sm.add_constant(pd.concat([df[["mkt", "sector", "fx"]], P], axis=1))
    mp = sm.OLS(df.ret, Xp).fit(cov_type="HC1"); mpc = sm.OLS(df.ret, Xp).fit()
    for c in P.columns:
        pooled.append(dict(case=name, dummy=c, n_event_weeks=int(P[c].sum()), mean_abnormal_weekly_return=mp.params[c], t_hc1=mp.tvalues[c], t_classical=mpc.tvalues[c], r2=mp.rsquared, n_weeks=int(mp.nobs)))
    # daily event study: market model with index + peer basket, estimation window [-260,-11], CAR[-1,+5]
    d = pd.concat([lr(tri[gv]).rename("ret"), lr(idx[mkts[0]]).rename("mkt"), basket(gv, group, freq=None).rename("sector")], axis=1).dropna()
    for _, r in ev.iterrows():
        pos = d.index.searchsorted(r.date)  # first trading day on/after the event
        if pos >= len(d): continue
        est = d.iloc[max(0, pos - 260):pos - 10]; win = d.iloc[pos - 1:pos + 6]
        if len(est) < 120 or len(win) < 7: continue
        mm = sm.OLS(est.ret, sm.add_constant(est[["mkt", "sector"]])).fit()
        ar = win.ret - mm.predict(sm.add_constant(win[["mkt", "sector"]], has_constant="add"))
        sd = float(np.sqrt(mm.scale))
        evstudy.append(dict(case=name, date=r.date.date(), event=r.label, expected_sign=r.sign, event_day_ar=ar.iloc[1], car_m1_p5=ar.sum(),
                            t_car=ar.sum() / (sd * np.sqrt(len(ar))), car_window_days=len(ar), est_window_days=len(est), est_r2=mm.rsquared))

pd.DataFrame(betas).to_csv(TABLES / "factor_betas.csv", index=False)
pd.DataFrame(dums).to_csv(TABLES / "event_dummies_weekly.csv", index=False)
pd.DataFrame(pooled).to_csv(TABLES / "event_signed_pooled.csv", index=False)
pd.DataFrame(evstudy).to_csv(TABLES / "event_study_daily.csv", index=False)

# Monthly copper variant for Nexans and the two European cable peers (Prysmian, NKT)
cu = lr(copper_monthly()); cu.index = cu.index + pd.offsets.MonthEnd(0)
rows = []
for gv, nm in [("246217", "Nexans"), ("284521", "Prysmian"), ("101156", "NKT")]:
    mo = pd.concat([lr(tri[gv].resample("ME").last()).rename("ret"), lr(idx["STOXX50"].resample("ME").last()).rename("mkt"),
                    lr(fxw["EURUSD"].resample("ME").last()).rename("fx"), cu.rename("copper"), cu.shift(1).rename("copper_lag1")], axis=1).loc[START:].dropna()
    mm = sm.OLS(mo.ret, sm.add_constant(mo[["mkt", "fx", "copper", "copper_lag1"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    for k in ["mkt", "fx", "copper", "copper_lag1"]:
        rows.append(dict(company=nm, regressor=k, beta=mm.params[k], t_hac=mm.tvalues[k], r2=mm.rsquared, n_months=int(mm.nobs), sample=f"{mo.index[0].date()} to {mo.index[-1].date()}"))
pd.DataFrame(rows).to_csv(TABLES / "copper_monthly_cable.csv", index=False)
print(pd.DataFrame(betas).round(3).to_string()); print(pd.DataFrame(pooled).round(4).to_string()); print(pd.DataFrame(rows).round(3).to_string())
print(pd.DataFrame(dums).round(4).to_string()); print(pd.DataFrame(evstudy).round(4).to_string())

# ======================= v2 (after the red-stats audit, 2026-10-20) =======================
# (a) total market betas with the peer basket orthogonalised to the market; (b) permutation p-values for the pooled signed
# dummies; (c) daily event study with the MARKET FACTOR ONLY (no peer basket), per case and pooled per group.
rng = np.random.default_rng(7)
v2b, v2p, v2e, v2g = [], [], [], []
for gv, (group, mkts, fxcol, events) in SPEC.items():
    name = CASES[gv]
    y = weekly(tri[gv]).rename("ret")
    X = pd.DataFrame({"mkt": weekly(idx[mkts[0]]), "sector": basket(gv, group), "fx": weekly(fxw[fxcol])})
    df = pd.concat([y, X], axis=1).loc[START:].dropna()
    aux = sm.OLS(df.sector, sm.add_constant(df.mkt)).fit(); df["sector_orth"] = aux.resid
    mp_ = sm.OLS(df.ret, sm.add_constant(df[["mkt", "sector", "fx"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    mt_ = sm.OLS(df.ret, sm.add_constant(df[["mkt", "sector_orth", "fx"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    v2b.append(dict(case=name, market_index=mkts[0], partial_beta_mkt=mp_.params.mkt, t_partial=mp_.tvalues.mkt, total_beta_mkt=mt_.params.mkt, t_total=mt_.tvalues.mkt,
                    beta_sector=mp_.params.sector, t_sector=mp_.tvalues.sector, beta_fx=mp_.params.fx, t_fx=mp_.tvalues.fx, corr_mkt_sector=float(df.mkt.corr(df.sector)), r2=mp_.rsquared, n_weeks=int(mp_.nobs),
                    meaning="total beta = response to a 1 pct market move including the part that comes through the peer basket; partial beta holds the basket fixed"))
    # pooled signed dummies: classical t and permutation p on factor-only residuals
    ev = pd.DataFrame(events, columns=["date", "label", "sign"]); ev["date"] = pd.to_datetime(ev.date)
    ev["week"] = [d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4) for d in ev.date]
    ev = ev[ev.week.isin(df.index)].groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join), sign=("sign", lambda s: "/".join(dict.fromkeys(s))))
    resid = sm.OLS(df.ret, sm.add_constant(df[["mkt", "sector", "fx"]])).fit().resid
    for cls in ["+", "-"]:
        wk = [r.week for r in ev.itertuples() if set(r.sign.split("/")) - {"0"} == {cls}]
        if not wk: continue
        stat = resid.loc[wk].mean(); k = len(wk)
        perm = np.array([resid.sample(k, random_state=int(rng.integers(1e9))).mean() for _ in range(5000)])
        v2p.append(dict(case=name, expected_sign=cls, n_event_weeks=k, mean_abnormal_weekly_return=stat, t_classical=stat / (resid.std() / np.sqrt(k)), permutation_p_two_sided=float((np.abs(perm) >= abs(stat)).mean()), n_perm=5000))
    # daily event study, market only, per case
    d = pd.concat([lr(tri[gv]).rename("ret"), lr(idx[mkts[0]]).rename("mkt")], axis=1).dropna()
    for _, r in ev.iterrows():
        pos = d.index.searchsorted(r.date)
        if pos >= len(d): continue
        est = d.iloc[max(0, pos - 260):pos - 10]; win = d.iloc[pos - 1:pos + 6]
        if len(est) < 120 or len(win) < 7: continue
        mm = sm.OLS(est.ret, sm.add_constant(est[["mkt"]])).fit(); ar = win.ret - mm.predict(sm.add_constant(win[["mkt"]], has_constant="add"))
        v2e.append(dict(case=name, date=r.date.date(), event=r.label, expected_sign=r.sign, event_day_ar=ar.iloc[1], car_m1_p5=ar.sum(), t_car=ar.sum() / (np.sqrt(mm.scale) * np.sqrt(len(ar))), model="market only"))
    # pooled per group: equal-weight portfolio of all group members (case included), market only
    members = core[core.group == group].gvkey.tolist()
    port = lr(tri[members]).mean(axis=1, skipna=True).rename("ret")
    dp = pd.concat([port, lr(idx[mkts[0]]).rename("mkt")], axis=1).dropna()
    cars = []
    for _, r in ev.iterrows():
        signs = set(r.sign.split("/")) - {"0"}
        if signs not in ({"+"}, {"-"}): continue
        pos = dp.index.searchsorted(r.date); est = dp.iloc[max(0, pos - 260):pos - 10]; win = dp.iloc[pos - 1:pos + 6]
        if len(est) < 120 or len(win) < 7: continue
        mm = sm.OLS(est.ret, sm.add_constant(est[["mkt"]])).fit(); ar = win.ret - mm.predict(sm.add_constant(win[["mkt"]], has_constant="add"))
        cars.append(dict(sign=list(signs)[0], car=ar.sum(), sd=np.sqrt(mm.scale) * np.sqrt(len(ar))))
    cars = pd.DataFrame(cars)
    for cls in ["+", "-"]:
        c = cars[cars.sign == cls]
        if len(c) == 0: continue
        z = c.car.mean() / np.sqrt((c.sd ** 2).sum()) * len(c) ** 0.5 / len(c) ** 0.5 if False else c.car.sum() / np.sqrt((c.sd ** 2).sum())
        from scipy.stats import norm
        v2g.append(dict(case_signs=name, group=group, expected_sign=cls, n_events=len(c), mean_car_m1_p5=c.car.mean(), share_with_expected_sign=float(((c.car > 0) == (cls == "+")).mean()), z=z, p_two_sided=float(2 * (1 - norm.cdf(abs(z)))),
                        bonferroni_threshold_24_tests=0.05 / 24, model="market only, equal-weight group portfolio"))
pd.DataFrame(v2b).to_csv(TABLES / "factor_betas_v2.csv", index=False)
pd.DataFrame(v2p).to_csv(TABLES / "event_signed_pooled_v2.csv", index=False)
pd.DataFrame(v2e).to_csv(TABLES / "event_study_daily_v2.csv", index=False)
pd.DataFrame(v2g).to_csv(TABLES / "event_study_group_v2.csv", index=False)
print("== v2"); print(pd.DataFrame(v2b).round(3).to_string()); print(pd.DataFrame(v2p).round(3).to_string()); print(pd.DataFrame(v2g).round(3).to_string())
e2 = pd.DataFrame(v2e); print(e2[e2.t_car.abs() > 1.9].round(3).to_string())
