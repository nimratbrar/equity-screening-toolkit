"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Amkor analysis 1: weekly factor and event-dummy regressions (5 years), permutation p-values, daily event study
without the peer basket (per challenge_stats.md), and a decomposition of what moved the stock.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_returns.py
Outputs (methodology/amkor/tables/): amkr_factor_betas.csv, amkr_event_dummies_weekly.csv, amkr_event_pooled_perm.csv,
amkr_event_study_daily.csv, amkr_event_study_by_class.csv, amkr_top_moves.csv, amkr_variance_decomp.csv. Market data [WRDS data].
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import norm
from amkor_common import osat_set, tri_osat, us_market, indices, EVENTS_AMKR, RESULT_WINDOWS, TABLES, AMKR, ASOF

core = osat_set(); tri = tri_osat(); usm = us_market(); idx = indices()
START = ASOF - pd.DateOffset(years=5)
lr = lambda s: np.log(s).diff()
peers = [g for g in core.gvkey if g != AMKR]
wk = lambda s: s.resample("W-FRI").last()
y = lr(wk(tri[AMKR])).rename("ret")
mkt = usm.resample("W-FRI").sum(min_count=1).rename("mkt")            # weekly log return of the US large-cap proxy
basket = lr(wk(tri[peers])).mean(axis=1, skipna=True).rename("sector")  # equal-weight OSAT basket ex Amkor, local currency
taiex = lr(wk(idx["TAIEX"])).rename("taiex")
df = pd.concat([y, mkt, basket, taiex], axis=1).loc[START:].dropna(subset=["ret", "mkt", "sector"])
df["sector_orth"] = sm.OLS(df.sector, sm.add_constant(df.mkt)).fit().resid

# event weeks (Friday on/after the event; same-week events share one dummy)
ev = pd.DataFrame(EVENTS_AMKR, columns=["date", "label", "sign", "cls"]); ev["date"] = pd.to_datetime(ev.date)
ev["week"] = [d if d.weekday() == 4 else d + pd.offsets.Week(weekday=4) for d in ev.date]
ev = ev[ev.week.isin(df.index)].groupby("week", as_index=False).agg(date=("date", "min"), label=("label", " + ".join), sign=("sign", lambda s: "/".join(dict.fromkeys(s))), cls=("cls", lambda s: "/".join(dict.fromkeys(s))))
D = pd.DataFrame(0.0, index=df.index, columns=[f"ev_{i}" for i in ev.index])
for i, w in ev.week.items(): D.loc[w, f"ev_{i}"] = 1.0

def hac(yv, X, lags=4): return sm.OLS(yv, sm.add_constant(X)).fit(cov_type="HAC", cov_kwds={"maxlags": lags})
rows = []
m_p = hac(df.ret, df[["mkt", "sector"]]); m_t = hac(df.ret, df[["mkt", "sector_orth"]])
m_d = hac(df.ret, pd.concat([df[["mkt", "sector"]], D], axis=1)); m_dc = sm.OLS(df.ret, sm.add_constant(pd.concat([df[["mkt", "sector"]], D], axis=1))).fit()
m_m = hac(df.ret, df[["mkt"]]); m_tw = hac(df.ret, df[["taiex", "sector"]])
for lab, m, k in [("partial beta, US proxy (basket held fixed)", m_p, "mkt"), ("total beta, US proxy (basket orthogonalised)", m_t, "mkt"), ("market only, US proxy", m_m, "mkt"),
                  ("sector beta (EW OSAT basket ex Amkor)", m_p, "sector"), ("sector beta, orthogonalised basket", m_t, "sector_orth"), ("partial beta with 26 event dummies", m_d, "mkt"),
                  ("TAIEX as market (alt), partial", m_tw, "taiex"), ("sector beta with TAIEX", m_tw, "sector")]:
    h1 = df.index < df.index[len(df) // 2]
    mh1 = sm.OLS(df.ret[h1], sm.add_constant(df.loc[h1, ["mkt", "sector"] if k != "taiex" else ["taiex", "sector"]])).fit(); mh2 = sm.OLS(df.ret[~h1], sm.add_constant(df.loc[~h1, ["mkt", "sector"] if k != "taiex" else ["taiex", "sector"]])).fit()
    kk = "sector" if k == "sector_orth" else k
    rows.append(dict(regressor=lab, beta=m.params[k], t_hac4=m.tvalues[k], t_hac8=hac(df.ret, m.model.exog[:, 1:], 8).tvalues[list(m.params.index).index(k)], r2=m.rsquared, n_weeks=int(m.nobs),
                     beta_first_half=mh1.params.get(kk, np.nan), beta_second_half=mh2.params.get(kk, np.nan), corr_mkt_sector=float(df.mkt.corr(df.sector)), sample=f"{df.index[0].date()} to {df.index[-1].date()}"))
pd.DataFrame(rows).to_csv(TABLES / "amkr_factor_betas.csv", index=False)

# single-week dummies: classical t (= abnormal / resid sd) and a permutation p for |t| > 2 (share of 5,000 random single weeks' factor-only residuals at least as large)
resid = sm.OLS(df.ret, sm.add_constant(df[["mkt", "sector"]])).fit().resid; sd = float(resid.std()); rng = np.random.default_rng(7)
dums = []
for i, r in ev.iterrows():
    k = f"ev_{i}"; ab = m_d.params[k]; t = m_dc.tvalues[k]
    perm = rng.choice(resid.values, 5000); pp = float((np.abs(perm) >= abs(ab)).mean()) if abs(t) > 2 else np.nan
    dums.append(dict(date=r.date.date(), week_ending=r.week.date(), event=r.label, cls=r.cls, expected_sign=r.sign, raw_weekly_return=df.ret[r.week], abnormal_weekly_return=ab, t_classical=t, permutation_p=pp, resid_sd_weekly=sd))
dums = pd.DataFrame(dums); dums.to_csv(TABLES / "amkr_event_dummies_weekly.csv", index=False)

# pooled by expected sign and by class, permutation p (5,000 random week sets, factor-only residuals)
pooled = []
def pool(label, weeks):
    k = len(weeks); stat = resid.loc[weeks].mean()
    perm = np.array([resid.sample(k, random_state=int(rng.integers(1e9))).mean() for _ in range(5000)])
    pooled.append(dict(pool=label, n_event_weeks=k, mean_abnormal_weekly_return=stat, t_classical=stat / (sd / np.sqrt(k)), permutation_p_two_sided=float((np.abs(perm) >= abs(stat)).mean()), share_positive=float((resid.loc[weeks] > 0).mean())))
for cls in ["+", "-"]:
    w = [r.week for r in ev.itertuples() if set(r.sign.split("/")) - {"0", "m"} == {cls}]
    if w: pool(f"expected sign {cls}", w)
for c in ["chips", "tariff", "apple", "ai", "china", "cycle", "co"]:
    w = [r.week for r in ev.itertuples() if c in r.cls.split("/")]
    if w: pool(f"class {c}", w)
pd.DataFrame(pooled).to_csv(TABLES / "amkr_event_pooled_perm.csv", index=False)

# daily event study, market only (no basket), CAR(-1,+5), estimation [-260,-11]
d = pd.concat([lr(tri[AMKR]).rename("ret"), usm.rename("mkt")], axis=1).dropna()
es = []
for _, r in ev.iterrows():
    pos = d.index.searchsorted(r.date); est = d.iloc[max(0, pos - 260):pos - 10]; win = d.iloc[pos - 1:pos + 6]
    if len(est) < 120 or len(win) < 7: continue
    mm = sm.OLS(est.ret, sm.add_constant(est[["mkt"]])).fit(); ar = win.ret - mm.predict(sm.add_constant(win[["mkt"]], has_constant="add")); s = np.sqrt(mm.scale)
    es.append(dict(date=r.date.date(), event=r.label, cls=r.cls, expected_sign=r.sign, event_day_ar=ar.iloc[1], car_m1_p5=ar.sum(), t_car=ar.sum() / (s * np.sqrt(len(ar))), sd_car=s * np.sqrt(len(ar))))
es = pd.DataFrame(es); es.to_csv(TABLES / "amkr_event_study_daily.csv", index=False)
byc = []
for lab, sel in [("expected +", es[es.expected_sign == "+"]), ("expected -", es[es.expected_sign == "-"])] + [(f"class {c}", es[es.cls.str.contains(c)]) for c in ["chips", "tariff", "apple", "ai", "china", "cycle"]]:
    if len(sel) == 0: continue
    z = sel.car_m1_p5.sum() / np.sqrt((sel.sd_car ** 2).sum())
    byc.append(dict(pool=lab, n_events=len(sel), mean_car_m1_p5=sel.car_m1_p5.mean(), share_positive=float((sel.car_m1_p5 > 0).mean()), z=z, p_two_sided=float(2 * (1 - norm.cdf(abs(z)))), bonferroni_threshold=0.05 / 8))
pd.DataFrame(byc).to_csv(TABLES / "amkr_event_study_by_class.csv", index=False)

# what moved Amkor: largest daily market-only residuals, classed as results window / listed event (within 1 trading day) / other; variance shares
dd = d.loc[START:]; mm = sm.OLS(dd.ret, sm.add_constant(dd[["mkt"]])).fit(); res_d = mm.resid
def in_window(t):
    md = t.strftime("%m-%d"); return any(a <= md <= b for a, b in RESULT_WINDOWS)
evdays = set()
for dt in ev.date:
    pos = d.index.searchsorted(dt)
    for j in (pos - 1, pos, pos + 1):
        if 0 <= j < len(d): evdays.add(d.index[j])
cls = pd.Series(["results window" if in_window(t) else "listed event +/-1d" if t in evdays else "other" for t in res_d.index], index=res_d.index)
top = res_d.abs().sort_values(ascending=False).head(20).index
tm = pd.DataFrame(dict(date=[t.date() for t in top], raw_return=dd.ret[top].values, abnormal_return=res_d[top].values, cls=cls[top].values,
                       nearest_listed_event=[ev.label[(ev.date - t).abs().idxmin()] if (ev.date - t).abs().min() <= pd.Timedelta(days=3) else "" for t in top]))
tm.to_csv(TABLES / "amkr_top_moves.csv", index=False)
vd = pd.DataFrame({"cls": cls, "r2": res_d ** 2}).groupby("cls").agg(n_days=("r2", "size"), sum_sq_abnormal=("r2", "sum"))
vd["share_days"] = vd.n_days / vd.n_days.sum(); vd["share_abnormal_variance"] = vd.sum_sq_abnormal / vd.sum_sq_abnormal.sum(); vd["variance_per_day_vs_other"] = (vd.sum_sq_abnormal / vd.n_days) / (vd.loc["other", "sum_sq_abnormal"] / vd.loc["other", "n_days"])
vd["market_r2_daily"] = mm.rsquared; vd.to_csv(TABLES / "amkr_variance_decomp.csv")
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 50)
print(pd.DataFrame(rows).round(3).to_string()); print(dums.round(3).to_string()); print(pd.DataFrame(pooled).round(3).to_string()); print(pd.DataFrame(byc).round(3).to_string()); print(tm.round(3).to_string()); print(vd.round(3).to_string())
