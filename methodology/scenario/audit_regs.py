"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-stats audit of regressions.md (2026-10-20). Re-uses the original loaders; writes only tables/audit_*.csv.
Run after audit_prep.py: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/audit_regs.py
All market and accounting data [WRDS data]; event dates from the macro agents' files; every test result [inference].
"""
import sys, runpy, warnings; warnings.filterwarnings("ignore")
from pathlib import Path
import numpy as np, pandas as pd, statsmodels.api as sm
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import reg_common as rc
from reg_common import universe_core, tri_wide, indices, fx, CASES, EVENTS_GRID, EVENTS_SEMIS, ASOF, CACHE
OUT = HERE / "tables"; SCR = HERE / "__pycache__" / "audit_tmp"; SCR.mkdir(parents=True, exist_ok=True)
rc.TABLES = SCR                      # the re-used scripts write their own tables to a scratch folder, not over the originals
rng = np.random.default_rng(20261020)
core = universe_core(); tri = tri_wide(); idx = indices(); fxw = fx()
START = ASOF - pd.DateOffset(years=5)
lr = lambda s: np.log(s).diff()
def weekly(s): return lr(s.resample("W-FRI").last())
def basket(gv, group, freq="W-FRI"):
    peers = core[(core.group == group) & (core.gvkey != gv)].gvkey.tolist()
    r = lr(tri[peers].resample(freq).last()) if freq else lr(tri[peers])
    return r.mean(axis=1, skipna=True)
SPEC = {"246217": ("cable_grid", "STOXX50", "EURUSD", [(d, l, s) for d, l, s in EVENTS_GRID]),
        "220629": ("fab_water_facility", "TOPIX", "USDJPY", [(d, l, s[0]) for d, l, *s in EVENTS_SEMIS]),
        "311307": ("fab_water_facility", "TOPIX", "USDJPY", [(d, l, s[1]) for d, l, *s in EVENTS_SEMIS]),
        "100697": ("chip_materials_and_chem", "TOPIX", "USDJPY", [(d, l, s[2]) for d, l, *s in EVENTS_SEMIS])}
def friday(d): return d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4)
def event_weeks(events, index, shift_fri=False):
    ev = pd.DataFrame(events, columns=["date", "label", "sign"]); ev["date"] = pd.to_datetime(ev.date)
    # shift_fri: events dated on a Friday (often after the European or Japanese close) move to the next week
    ev["week"] = [friday(d + pd.Timedelta(days=3)) if (shift_fri and d.weekday() == 4) else friday(d) for d in ev.date]
    ev = ev[ev.week.isin(index)]
    return ev.groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join), sign=("sign", lambda s: "/".join(dict.fromkeys(s))))
def cls(sign):
    s = set(sign.split("/")) - {"0"}
    return "pos" if s == {"+"} else "neg" if s == {"-"} else "company" if s == {"co"} else "zero_or_mixed"

# ---------- A. factor diagnostics: collinearity, dummies, HAC lags, sector factor on/off ----------
A, B = [], []
for gv, (group, mk, fxc, events) in SPEC.items():
    nm = CASES[gv]
    df = pd.concat([weekly(tri[gv]).rename("ret"), weekly(idx[mk]).rename("mkt"), basket(gv, group).rename("sector"), weekly(fxw[fxc]).rename("fx")], axis=1).loc[START:].dropna()
    X = df[["mkt", "sector", "fx"]]
    vif = {c: 1 / (1 - sm.OLS(X[c], sm.add_constant(X.drop(columns=c))).fit().rsquared) for c in X}
    sec_orth = sm.OLS(df.sector, sm.add_constant(df.mkt)).fit().resid
    for lags in (4, 8, 13):
        m = sm.OLS(df.ret, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
        A.append(dict(case=nm, spec=f"factors only, HAC {lags}", beta_mkt=m.params.mkt, t_mkt=m.tvalues.mkt, beta_sector=m.params.sector, t_sector=m.tvalues.sector, r2=m.rsquared,
                      corr_mkt_sector=df.mkt.corr(df.sector), vif_mkt=vif["mkt"], vif_sector=vif["sector"]))
    m = sm.OLS(df.ret, sm.add_constant(pd.concat([df[["mkt", "fx"]], sec_orth.rename("sector_orth")], axis=1))).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    A.append(dict(case=nm, spec="sector orthogonalised to market (total market beta)", beta_mkt=m.params.mkt, t_mkt=m.tvalues.mkt, beta_sector=m.params.sector_orth, t_sector=m.tvalues.sector_orth, r2=m.rsquared,
                  corr_mkt_sector=df.mkt.corr(df.sector), vif_mkt=vif["mkt"], vif_sector=vif["sector"]))
    h = len(df) // 2
    for lab, sub in (("first half", df.iloc[:h]), ("second half", df.iloc[h:])):
        m = sm.OLS(sub.ret, sm.add_constant(sub[["mkt", "sector", "fx"]])).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        A.append(dict(case=nm, spec=f"factors only, {lab} {sub.index[0].date()} to {sub.index[-1].date()}", beta_mkt=m.params.mkt, t_mkt=m.tvalues.mkt, beta_sector=m.params.sector, t_sector=m.tvalues.sector, r2=m.rsquared,
                      corr_mkt_sector=sub.mkt.corr(sub.sector), vif_mkt=np.nan, vif_sector=np.nan))
    # ---------- B. pooled signed event dummies: classical, HC1, HAC(4), permutation; with and without the sector factor; Friday shift ----------
    for fac_lab, facs in (("mkt+sector+fx (as reported)", ["mkt", "sector", "fx"]), ("mkt+fx, no sector basket", ["mkt", "fx"])):
        for shift in (False, True):
            ev = event_weeks(events, df.index, shift_fri=shift); ev["cls"] = ev.sign.map(cls)
            P = pd.DataFrame(0.0, index=df.index, columns=["pos", "neg", "company", "zero_or_mixed"])
            for _, r in ev.iterrows(): P.loc[r.week, r.cls] = 1.0
            P = P.loc[:, P.sum() > 0]
            S = (P.get("pos", 0) - P.get("neg", 0)).rename("signed")   # +1 in '+' weeks, -1 in '-' weeks: one test of 'the signs predict the move'
            XX = sm.add_constant(pd.concat([df[facs], P], axis=1))
            fits = {k: sm.OLS(df.ret, XX).fit(**kw) for k, kw in (("cl", {}), ("hc1", dict(cov_type="HC1")), ("hac", dict(cov_type="HAC", cov_kwds={"maxlags": 4})))}
            e = sm.OLS(df.ret, sm.add_constant(df[facs])).fit().resid           # factor-only residuals for the permutation test
            ev_weeks = set(ev.week)
            pool = np.array([w not in ev_weeks for w in df.index])
            for c in list(P.columns) + ["signed"]:
                if c == "signed":
                    if (S != 0).sum() == 0: continue
                    k = int((S != 0).sum()); stat = float((e * S).sum() / k)
                    ms = sm.OLS(df.ret, sm.add_constant(pd.concat([df[facs], S], axis=1)))
                    tc, th1, thac = ms.fit().tvalues["signed"], ms.fit(cov_type="HC1").tvalues["signed"], ms.fit(cov_type="HAC", cov_kwds={"maxlags": 4}).tvalues["signed"]
                    sgn = S[S != 0].values
                    sims = np.array([(e.values[pool][rng.choice(pool.sum(), k, replace=False)] * sgn).mean() for _ in range(5000)])
                else:
                    k = int(P[c].sum()); stat = float(e[P[c] == 1].mean())
                    tc, th1, thac = fits["cl"].tvalues[c], fits["hc1"].tvalues[c], fits["hac"].tvalues[c]
                    sims = np.array([e.values[pool][rng.choice(pool.sum(), k, replace=False)].mean() for _ in range(5000)])
                B.append(dict(case=nm, factors=fac_lab, friday_events_shifted=shift, dummy=c, n_weeks=k, mean_abnormal=stat, t_classical=tc, t_hc1=th1, t_hac4=thac,
                              perm_p_two_sided=float(np.mean(np.abs(sims) >= abs(stat)))))
pd.DataFrame(A).to_csv(OUT / "audit_factor_diag.csv", index=False)
pd.DataFrame(B).to_csv(OUT / "audit_event_pooled_weekly.csv", index=False)

# ---------- C. event dates on Fridays or weekends (timing check) ----------
C = []
for lab, evs in (("grid", EVENTS_GRID), ("semis", EVENTS_SEMIS)):
    for d, l, *s in evs:
        t = pd.Timestamp(d)
        if t.weekday() >= 4: C.append(dict(list=lab, date=d, weekday=t.day_name(), event=l))
pd.DataFrame(C).to_csv(OUT / "audit_event_timing.csv", index=False)

# ---------- D. pooled daily event study across the core names, market-only and market+sector models, portfolio method ----------
cew = pd.read_csv(CACHE / "audit_country_ew.csv", parse_dates=["datadate"]).set_index("datadate")
IDX = {"JPN": idx["TOPIX"], "FRA": idx["CAC40"], "DEU": idx["DAX"], "TWN": idx["TAIEX"], "ITA": idx["STOXX50"], "DNK": idx["STOXX50"], "FIN": idx["STOXX50"]}
def mret(loc):
    if loc in IDX: return lr(IDX[loc])
    return cew["KOR"] if loc == "KOR" else cew["USA"]          # USA and Pentair (GBR domicile, NYSE): US equal-weight index
TESTS = [("cable_grid (11) grid events, Nexans signs", "cable_grid", [(d, l, s) for d, l, s in EVENTS_GRID]),
         ("fab_water_facility (14) semis events, Organo signs", "fab_water_facility", [(d, l, s[0]) for d, l, *s in EVENTS_SEMIS]),
         ("fab_water_facility (14) semis events, Japan Material signs", "fab_water_facility", [(d, l, s[1]) for d, l, *s in EVENTS_SEMIS]),
         ("chip_materials_and_chem (15) semis events, Shin-Etsu signs", "chip_materials_and_chem", [(d, l, s[2]) for d, l, *s in EVENTS_SEMIS])]
D, Drow = [], []
for lab, group, events in TESTS:
    members = core[core.group == group]
    for model in ("market only", "market + peer basket"):
        ar_by_firm = {}
        evs = pd.DataFrame(events, columns=["date", "label", "sign"]); evs["date"] = pd.to_datetime(evs.date)
        evs["week"] = evs.date.map(friday)
        evs = evs.groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join), sign=("sign", lambda s: "/".join(dict.fromkeys(s))))
        for _, e in evs.iterrows():
            ars, ests = [], []
            for gv, loc in zip(members.gvkey, members["loc"]):
                cols = [lr(tri[gv]).rename("ret"), mret(loc).rename("mkt")]
                if model != "market only": cols.append(basket(gv, group, freq=None).rename("sector"))
                d = pd.concat(cols, axis=1).dropna(); d = d[d.ret != 0] if False else d
                pos = d.index.searchsorted(e.date)
                if pos >= len(d) or pos < 130: continue
                est = d.iloc[max(0, pos - 260):pos - 10]; win = d.iloc[pos - 1:pos + 6]
                if len(est) < 120 or len(win) < 7: continue
                Xc = [c for c in d.columns if c != "ret"]
                mm = sm.OLS(est.ret, sm.add_constant(est[Xc])).fit()
                ars.append(pd.Series((win.ret - mm.predict(sm.add_constant(win[Xc], has_constant="add"))).values))
                ests.append(pd.Series(mm.resid.values[-120:]))
            if len(ars) < 3: continue
            p_ar = pd.concat(ars, axis=1).mean(axis=1); p_est = pd.concat(ests, axis=1).mean(axis=1)   # equal-weight portfolio: keeps cross-correlation in the sd
            car = float(p_ar.sum()); sd = float(p_est.std(ddof=1)); t = car / (sd * np.sqrt(7))
            D.append(dict(test=lab, model=model, date=e.date.date(), event=e.label, sign=e.sign, cls=cls(e.sign), n_firms=len(ars), portfolio_car_m1_p5=car, t=t))
        dd = pd.DataFrame([r for r in D if r["test"] == lab and r["model"] == model])
        if dd.empty: continue
        from scipy.stats import chi2, norm
        for c, mult in (("pos", 1), ("neg", -1)):
            x = dd[dd.cls == c]
            if len(x): Drow.append(dict(test=lab, model=model, events=f"expected {c}", n_events=len(x), mean_car=x.portfolio_car_m1_p5.mean(), mean_signed_car=mult * x.portfolio_car_m1_p5.mean(),
                                        z_signed=float(mult * x.t.sum() / np.sqrt(len(x))), p_signed=float(2 * norm.sf(abs(mult * x.t.sum() / np.sqrt(len(x))))), chi2_any_effect_p=float(chi2.sf((x.t ** 2).sum(), len(x)))))
        x = dd[dd.cls.isin(["pos", "neg"])]
        sg = np.where(x.cls == "pos", 1, -1)
        if len(x): Drow.append(dict(test=lab, model=model, events="all signed (+ and -)", n_events=len(x), mean_car=x.portfolio_car_m1_p5.mean(), mean_signed_car=float((sg * x.portfolio_car_m1_p5).mean()),
                                    z_signed=float((sg * x.t).sum() / np.sqrt(len(x))), p_signed=float(2 * norm.sf(abs((sg * x.t).sum() / np.sqrt(len(x))))), chi2_any_effect_p=float(chi2.sf((x.t ** 2).sum(), len(x)))))
        x = dd[dd.cls != "company"]
        Drow.append(dict(test=lab, model=model, events="all non-company events, any sign", n_events=len(x), mean_car=x.portfolio_car_m1_p5.mean(), mean_signed_car=np.nan, z_signed=np.nan, p_signed=np.nan,
                         chi2_any_effect_p=float(chi2.sf((x.t ** 2).sum(), len(x)))))
pd.DataFrame(D).to_csv(OUT / "audit_event_pooled40_by_event.csv", index=False)
pd.DataFrame(Drow).to_csv(OUT / "audit_event_pooled40.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(pd.DataFrame(A).round(3).to_string()); print(pd.DataFrame(B).round(3).to_string()); print(pd.DataFrame(C).to_string()); print(pd.DataFrame(Drow).round(3).to_string())
print(pd.DataFrame(D).query("abs(t) >= 2").round(3).to_string())
