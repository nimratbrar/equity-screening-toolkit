"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

AtkinsRéalis analysis 4: scenario-mixture Monte Carlo on the simulate_v2 conventions (methodology/scenario/simulate_v2.py):
value_h = EBITDA_h x multiple_h + net cash - LSTK cash drag, no extra discounting; 12m uses FY2026 EBITDA (FY1), 24m FY2027 (FY2);
multiple starts at today's forward multiple (EV / FY1 mode EBITDA) with a triangular spread, then scenario factors, then one
reversion step of slope -0.25 per year toward the fitted multiple (log residual read from atkins_multiples.py output, broad peer-industry OLS);
signed Gaussian-copula correlations; raw P(loss) and 9 percent a year hurdle P reported separately; entry-price solver.
Variants: (a) no reversion, (b) reversion + signed correlations (headline), (c) reversion + independent shocks.
Seed 20261020, 20,000 paths. Scenario ranges [inference, illustrative]; company inputs via atkins_common.ATRL_IN (placeholders where licensed).
At 12m the EBITDA impact is scaled by 0.5 because FY2026 is 80 percent reported by the valuation date; multiple factors apply in full [inference].
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_simulate.py   (about 60 s)
Outputs (methodology/atkins/tables/): atrl_sim_summary.csv, atrl_sim_scenario_tree.csv, atrl_sim_tornado.csv, atrl_sim_crosscheck.csv,
atrl_sim_entry_prices.csv, atrl_sim_inputs.csv
"""
import numpy as np, pandas as pd
from scipy.stats import norm
from atkins_common import ATRL_IN, TABLES, tri_wide, CONSULT

SEED, N, HURDLE, SLOPE, SIGMA_FLOOR = 20261020, 20000, 0.09, 0.25, 0.05
FM = ATRL_IN["fwd_mult"]
RESID = float(pd.read_csv(TABLES / "atrl_multiples_residuals.csv").query("model.str.startswith('broad peer') and estimator == 'OLS'", engine="python").log_resid.iloc[0])
falls = pd.read_csv(TABLES / "atrl_ebitda_falls.csv").set_index("sample")
P10_MAIN = float(falls.loc["7 consultancies", "p10"]) - 0.10        # survivor consultancy p10 less 10 points (audit: deviation basis)
P10_ALT = float(falls.loc["10 engineering", "p10"]) - 0.10          # engineering incl. EPC
INP = dict(price=ATRL_IN["price"], shares=ATRL_IN["shares"], ebitda12=ATRL_IN["ebitda_fy1"], ebitda24=ATRL_IN["ebitda_fy2"],
           netcash12=-ATRL_IN["net_debt"] - np.mean(ATRL_IN["lstk_cash_drag_2026"]), netcash24=-ATRL_IN["net_debt"] - np.mean(ATRL_IN["lstk_cash_drag_2026"]) - 25.0,  # LSTK drag 2026, "little" 2027 [company filing]
           mult_ratio=(0.80, 1.20), fwd_mult=FM, resid=RESID)
turns = lambda lo, hi: (1 + lo / FM, 1 + hi / FM)
SCEN = {  # prob (P12, P24); ebitda (lo, hi) at 24m; mult factor (lo, hi) from turns [inference, illustrative: analyst scenario judgments]
    "2 Nuclear renaissance, CANDU exports": dict(prob=(0.15, 0.25), ebitda=(+0.06, +0.13), mult=turns(1.0, 2.0)),
    "3 Ontario new-build go-ahead":         dict(prob=(0.25, 0.50), ebitda=(+0.02, +0.06), mult=turns(1.5, 3.0)),
    "4 Refurbishment cost overrun":         dict(prob=(0.10, 0.20), ebitda=(-0.09, -0.04), mult=turns(-2.0, -1.0)),
    "5 Middle East slowdown deepens":       dict(prob=(0.35, 0.40), ebitda=(-0.06, -0.03), mult=turns(-1.0, -0.5)),
    "6 Public infrastructure squeeze":      dict(prob=(0.20, 0.30), ebitda=(-0.12, -0.06), mult=turns(-2.0, -1.0)),
    "7 Nuclear incident or policy reversal": dict(prob=(0.05, 0.10), ebitda=(-0.12, -0.06), mult=turns(-4.0, -2.0)),
    "8 Rate or recession shock":            dict(prob=(0.25, 0.35), ebitda=(-0.18, -0.10), mult=turns(-3.0, -2.0)),
}
CORR = {  # signed latent correlations [inference, illustrative]
    ("2 Nuclear renaissance, CANDU exports", "3 Ontario new-build go-ahead"): +0.4,
    ("4 Refurbishment cost overrun", "2 Nuclear renaissance, CANDU exports"): -0.3, ("4 Refurbishment cost overrun", "3 Ontario new-build go-ahead"): -0.3,
    ("7 Nuclear incident or policy reversal", "2 Nuclear renaissance, CANDU exports"): -0.3, ("7 Nuclear incident or policy reversal", "3 Ontario new-build go-ahead"): -0.3,
    ("5 Middle East slowdown deepens", "8 Rate or recession shock"): +0.4, ("6 Public infrastructure squeeze", "8 Rate or recession shock"): +0.4,
    ("8 Rate or recession shock", "3 Ontario new-build go-ahead"): -0.2,
}
NEG = [s for s in SCEN if s[0] in "45678"]

def corr_matrix(names, pairs, independent):
    C = np.eye(len(names))
    if not independent:
        ix = {n: i for i, n in enumerate(names)}
        for (a, b), r in pairs.items(): C[ix[a], ix[b]] = C[ix[b], ix[a]] = r
    w, V = np.linalg.eigh(C)
    if w.min() < 1e-6: C = V @ np.diag(np.clip(w, 1e-6, None)) @ V.T; d = np.sqrt(np.diag(C)); C = C / np.outer(d, d)
    return C

def simulate(hz, variant="b", sigma=None, ov=None, seed=SEED):
    inp = dict(INP); ov = ov or {}; inp.update({k: v for k, v in ov.items() if k in inp})
    rng = np.random.default_rng(seed + hz); years = 1.0 if hz == 0 else 2.0
    slope = 0.0 if variant == "a" else ov.get("slope", SLOPE); pscale = ov.get("pscale", 1.0); escale = 0.5 if hz == 0 else 1.0
    names = list(SCEN); L = np.linalg.cholesky(corr_matrix(names, CORR, variant == "c")); z = rng.standard_normal((N, len(names))) @ L.T
    on = {}
    for i, s in enumerate(names):
        p = SCEN[s]["prob"][hz] * (pscale if s in NEG else 1.0); on[s] = z[:, i] < norm.ppf(min(p, 0.95))
    lo, md, hi = inp["ebitda12"] if hz == 0 else inp["ebitda24"]
    base_eb = rng.triangular(lo, md, hi, N); base_m = inp["fwd_mult"] * rng.triangular(inp["mult_ratio"][0], 1.0, inp["mult_ratio"][1], N)
    eb_fac, m_fac = np.ones(N), np.ones(N)
    for s, d in SCEN.items():
        k = on[s]; m = int(k.sum()); eb_fac[k] *= 1 + escale * rng.uniform(*d["ebitda"], m); m_fac[k] *= rng.uniform(*d["mult"], m)
    sig = (sigma if sigma is not None else inp.get("sigma", 0.0)) * np.sqrt(years)
    ebitda = base_eb * eb_fac * np.exp(rng.normal(-0.5 * sig ** 2, sig, N))
    mult = base_m * m_fac * np.exp(-slope * years * inp["resid"])
    value = (ebitda * mult + (inp["netcash12"] if hz == 0 else inp["netcash24"])) / inp["shares"]
    ret = value / inp["price"] - 1
    return dict(value=value, ret=ret, ebitda=ebitda, mult=mult, on=on, sigma=sig, hurdle=(1 + HURDLE) ** years - 1, p_base=float(np.mean(~np.any(np.column_stack(list(on.values())), axis=1))),
                p_pure_base=float(np.mean(~np.any(np.column_stack([on[s] for s in NEG]), axis=1))))

def calibrate(target):
    lo, hi = 0.0, 0.8
    for _ in range(30):
        mid = (lo + hi) / 2; p10 = np.quantile(simulate(0, "b", sigma=mid)["ebitda"] / INP["ebitda12"][1] - 1, 0.10)
        lo, hi = (mid, hi) if p10 > target else (lo, mid)
    return (lo + hi) / 2

def stats(r):
    v, ret, h = r["value"], r["ret"], r["hurdle"]; q = np.quantile(v, [0.05, 0.25, 0.5, 0.75, 0.95])
    return dict(mean_value=v.mean(), median_value=q[2], p05=q[0], p25=q[1], p75=q[3], p95=q[4], exp_return=ret.mean(), median_return=np.median(ret),
                p_loss_raw=float(np.mean(ret < 0)), p_below_hurdle=float(np.mean(ret < h)), hurdle=h, p_gt15=float(np.mean(ret > 0.15)), p_gt30=float(np.mean(ret > 0.30)),
                ret_p05=np.quantile(ret, 0.05), ret_p95=np.quantile(ret, 0.95), p_base_no_shock=r["p_base"], p_no_negative_shock=r["p_pure_base"])

def main():
    s_main = max(calibrate(P10_MAIN), SIGMA_FLOOR); s_alt = max(calibrate(P10_ALT), SIGMA_FLOOR); INP["sigma"] = s_main
    summary, tree, tornado, entry, xcheck = [], [], [], [], []; res = {}
    for var in "abc":
        for hz, lab in ((0, "12m"), (1, "24m")):
            r = simulate(hz, var); res[(var, lab)] = r; s = stats(r); s.update(variant=var, horizon=lab, sigma_idio=r["sigma"], sigma_label="main"); summary.append(s)
            if var == "b":
                r2 = simulate(hz, var, sigma=s_alt); s2 = stats(r2); s2.update(variant=var, horizon=lab, sigma_idio=r2["sigma"], sigma_label="alt (engineering incl. EPC)"); summary.append(s2)
    for hz, lab in ((0, "12m"), (1, "24m")):
        r = res[("b", lab)]; ret, on = r["ret"], r["on"]
        rows = list(on.items()) + [("1 Base (no shock)", ~np.any(np.column_stack(list(on.values())), axis=1))]
        for sc, k in rows:
            if k.sum() == 0: continue
            p = float(k.mean()); cm = float(ret[k].mean())
            contrib = p * cm if sc.startswith("1 ") else p * (cm - float(ret[~k].mean()))
            tree.append(dict(horizon=lab, scenario=sc, prob=p, cond_median_value=float(np.median(r["value"][k])), cond_mean_return=cm, cond_p_loss_raw=float(np.mean(ret[k] < 0)), contribution=contrib,
                             kind="exclusive: P x E[ret|base]" if sc.startswith("1 ") else "layered: P x (E[ret|on] - E[ret|off])"))
        # entry prices
        v = r["value"]; q35, m15 = float(np.quantile(v, 0.35)), float(v.mean() / 1.15); q35h = q35 / (1 + r["hurdle"])
        entry.append(dict(horizon=lab, price=INP["price"], entry_p_loss_raw_lt_35=q35, entry_exp_ret_gt_15=m15, entry_price=min(q35, m15), discount_to_price=min(q35, m15) / INP["price"] - 1,
                          entry_p_below_hurdle_lt_35=q35h, entry_price_hurdle_basis=min(q35h, m15)))
    base = stats(simulate(0, "b"))["exp_return"]; e12 = INP["ebitda12"]
    for lab, (lo_o, hi_o) in {"forward multiple +/-1 turn": (dict(fwd_mult=FM - 1), dict(fwd_mult=FM + 1)), "FY1 EBITDA +/-10%": (dict(ebitda12=tuple(x * 0.9 for x in e12)), dict(ebitda12=tuple(x * 1.1 for x in e12))),
                             "negative-scenario probabilities x1.5 / x0.5": (dict(pscale=1.5), dict(pscale=0.5)), "reversion slope 0 / -0.5 per year": (dict(slope=0.0), dict(slope=0.5)),
                             "multiple residual: peer-set +0.2 / broad -0.2 (low = premium reverts down)": (dict(resid=+0.2), dict(resid=-0.2))}.items():
        lo_r = stats(simulate(0, "b", ov=lo_o))["exp_return"]; hi_r = stats(simulate(0, "b", ov=hi_o))["exp_return"]
        tornado.append(dict(input=lab, exp_return_base=base, exp_return_low=lo_r, exp_return_high=hi_r, swing=abs(hi_r - lo_r)))
    # base-rate cross-check: ATRL's own daily history is not on disk; references are (i) ATRL 1y realised vol (ATRL_IN["vol_1y"]) as a lognormal
    # and (ii) the realised 12m log total returns of the consultancy peers with daily data (overlapping windows, last 5 years) [WRDS data]
    tri = tri_wide(); cons = [g for g in CONSULT if g in tri.columns]
    r12 = pd.concat([np.log(tri[g] / tri[g].shift(252)).dropna() for g in cons]); r12 = r12[r12.index >= "2021-10-01"]
    r = res[("b", "12m")]; logret = np.log(r["value"] / INP["price"]); sim_sd, med = logret.std(), np.median(logret)
    for ref, sd_ref, p05_ref, p95_ref, share_neg in (("ATRL 1y realised vol (lognormal)", ATRL_IN["vol_1y"], -1.645 * ATRL_IN["vol_1y"], 1.645 * ATRL_IN["vol_1y"], np.nan),
                                                     ("consultancy peers 12m history", r12.std(), r12.quantile(0.05), r12.quantile(0.95), float((r12 < 0).mean()))):
        sc = med + (logret - med) * (sd_ref / sim_sd); rr = np.exp(sc) - 1
        xcheck.append(dict(reference=ref, sim_sd_log=sim_sd, ref_sd_log=sd_ref, sim_p05_log=np.quantile(logret, 0.05), ref_p05_log=p05_ref, sim_p95_log=np.quantile(logret, 0.95), ref_p95_log=p95_ref,
                           ref_share_negative=share_neg, sim_p_loss_raw=float(np.mean(r["ret"] < 0)), refvol_p_loss_raw=float(np.mean(rr < 0)), refvol_p_below_hurdle=float(np.mean(rr < HURDLE)), refvol_exp_return=float(rr.mean())))
    df = pd.DataFrame(summary); df.to_csv(TABLES / "atrl_sim_summary.csv", index=False)
    pd.DataFrame(tree).to_csv(TABLES / "atrl_sim_scenario_tree.csv", index=False); pd.DataFrame(tornado).sort_values("swing", ascending=False).to_csv(TABLES / "atrl_sim_tornado.csv", index=False)
    pd.DataFrame(xcheck).to_csv(TABLES / "atrl_sim_crosscheck.csv", index=False); pd.DataFrame(entry).to_csv(TABLES / "atrl_sim_entry_prices.csv", index=False)
    pd.DataFrame([dict(price=INP["price"], shares=INP["shares"], fwd_mult_today=FM, ebitda_fy1=INP["ebitda12"], ebitda_fy2=INP["ebitda24"], netcash12=INP["netcash12"], netcash24=INP["netcash24"],
                       resid_log=RESID, sigma_main=s_main, sigma_alt=s_alt, p10_target_main=P10_MAIN, p10_target_alt=P10_ALT, sigma_at_floor=s_main <= SIGMA_FLOOR)]).to_csv(TABLES / "atrl_sim_inputs.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print("fwd mult", round(FM, 2), "resid", round(RESID, 3), "sigma main/alt", round(s_main, 3), round(s_alt, 3), "p10 targets", round(P10_MAIN, 3), round(P10_ALT, 3))
    print(df[["variant", "horizon", "sigma_label", "mean_value", "median_value", "p05", "p95", "exp_return", "p_loss_raw", "p_below_hurdle", "p_gt15", "p_gt30", "ret_p05", "p_base_no_shock", "p_no_negative_shock"]].round(3).to_string())
    print(pd.DataFrame(tree).round(3).to_string()); print(pd.DataFrame(tornado).sort_values("swing", ascending=False).round(3).to_string()); print(pd.DataFrame(xcheck).round(3).to_string()); print(pd.DataFrame(entry).round(1).to_string())

if __name__ == "__main__":
    main()
