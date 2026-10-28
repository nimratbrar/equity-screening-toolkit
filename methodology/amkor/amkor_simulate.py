"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Amkor scenario-mixture Monte Carlo on the simulate_v2 conventions (methodology/scenario/simulate_v2.py):
forward multiple on FY1 EBITDA, no discounting at 12m, multiple starts at today's forward multiple, one reversion step of slope
SLOPE per year toward the fitted multiple, signed Gaussian-copula correlations, raw P(loss) and hurdle P reported separately,
entry-price solver. Variants: (a) no reversion, (b) reversion toward the peer cross-section fit (residual resid_b),
(c) reversion with independent shocks, (d) reversion toward half the residual (resid_d: a peer re-rating may itself
revert, so the full residual is treated as an upper bound; compare amkr_multiple_history.csv).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_simulate.py   (seed 20261020, 20,000 paths; about 60 s)
Outputs methodology/amkor/tables/amkr_sim_*.csv. Every simulated number is [inference]; inputs labelled below.
"""
import json, numpy as np, pandas as pd
from scipy.stats import norm
from amkor_common import TABLES
SEED, N, HURDLE, SLOPE, SIGMA_FLOOR = 20261020, 20000, 0.09, 0.25, 0.05   # SLOPE: illustrative reversion slope per year; estimate your own
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
FY1_EBITDA = 500.0                                     # [placeholder: I/B/E/S FY1 EBITDA consensus]
INP = dict(
    price=100.0, shares=50.0,                          # [placeholder: latest close and shares outstanding, Compustat / Valuation inputs sheet]
    ebitda12=(FY1_EBITDA * 0.95, FY1_EBITDA, FY1_EBITDA * 1.05),  # FY1 consensus with a +/-5% spread [inference]
    ebitda24=(FY1_EBITDA * 1.03, FY1_EBITDA * 1.09, FY1_EBITDA * 1.15),  # FY2 [inference]: scenario-base growth range
    netcash=25.0,                                      # [placeholder: latest quarter net cash, company filing]
    netcash_fy25=50.0,                                 # [placeholder: Compustat last fiscal year (che - debt)]
    mult_ratio=(0.85, 1.20),                           # triangular spread around today's forward multiple [inference, illustrative]
    resid_b=-0.30, resid_d=-0.15,                      # [placeholder: median leave-one-out log residual vs peer fit (amkr_multiples_summary.csv); half for (d)]
    resid_broad=-0.40,                                 # [placeholder: residual in the broad-universe model, tornado low case]
    p10_main=-0.25, p10_alt=-0.15,                     # [placeholder: peer p10 EBITDA change vs median (deviation basis) and raw p10, Compustat]
    hist_sd12=0.40, hist_p05=-0.50, hist_p95=0.90,     # [placeholder: own 12m log total-return sd and quantiles, Compustat daily prices]
    group_sd12=0.40, group_p05=-0.45, group_p95=0.85,  # [placeholder: peer pooled 12m log total-return sd and quantiles]
    hist_share_negative=0.35,                          # [placeholder: share of own 12m windows with a negative return]
)
# ===== END PLACEHOLDER INPUTS =====
INP["fwd_mult"] = (INP["price"] * INP["shares"] - INP["netcash"]) / INP["ebitda12"][1]            # today's forward EV/EBITDA on the latest balance sheet
INP["fwd_mult_fy25bs"] = (INP["price"] * INP["shares"] - INP["netcash_fy25"]) / INP["ebitda12"][1]  # the deep dive's basis (last fiscal year balance sheet)
# Scenario set [inference, illustrative: P and impact ranges are analyst judgments for the worked example]. Demand states exclusive on one latent
# ("demand", worst to best); overlays are Bernoullis on the same copula. EBITDA impacts (lo, hi) uniform; mult = factor on the multiple.
STATES = ["TSMC squeeze / AI pause", "Smartphone second leg", "Base plateau", "AI packaging boom"]
STATE_P = {"TSMC squeeze / AI pause": (0.15, 0.20), "Smartphone second leg": (0.20, 0.27), "AI packaging boom": (0.20, 0.17)}
IMPACT = {"TSMC squeeze / AI pause": dict(eb=(-0.20, -0.08), mult=(0.80, 0.90)), "Smartphone second leg": dict(eb=(-0.20, -0.08), mult=(0.85, 0.95)),
          "Base plateau": dict(eb=(0.0, 0.0), mult=(1.0, 1.0)), "AI packaging boom": dict(eb=(+0.08, +0.16), mult=(1.10, 1.20)),
          "Taiwan halt 3 to 6 months": dict(eb=(-0.60, -0.25), mult=(0.60, 0.80)), "Tariff escalation (232 phase 2, SE Asia)": dict(eb=(-0.06, -0.02), mult=(0.90, 1.00)),
          "Arizona on time": dict(eb=(0.0, +0.02), mult=(1.10, 1.20)), "China decoupling": dict(eb=(-0.08, -0.03), mult=(0.95, 1.05))}
OVERLAYS = {"Taiwan halt 3 to 6 months": (0.025, 0.06), "Tariff escalation (232 phase 2, SE Asia)": (0.25, 0.40), "Arizona on time": (0.40, 0.45), "China decoupling": (0.30, 0.45)}
CORR = {("demand", "Taiwan halt 3 to 6 months"): -0.3, ("Taiwan halt 3 to 6 months", "Tariff escalation (232 phase 2, SE Asia)"): +0.5,
        ("Taiwan halt 3 to 6 months", "China decoupling"): +0.5, ("Tariff escalation (232 phase 2, SE Asia)", "China decoupling"): +0.4,
        ("Arizona on time", "Tariff escalation (232 phase 2, SE Asia)"): +0.2, ("demand", "Arizona on time"): +0.2}   # signed [inference]
NEG = ["TSMC squeeze / AI pause", "Smartphone second leg", "Taiwan halt 3 to 6 months", "Tariff escalation (232 phase 2, SE Asia)", "China decoupling"]

def corr_matrix(names, pairs, independent=False):
    C = np.eye(len(names))
    if not independent:
        ix = {n: i for i, n in enumerate(names)}
        for (a, b), r in pairs.items(): C[ix[a], ix[b]] = C[ix[b], ix[a]] = r
    w, V = np.linalg.eigh(C)
    if w.min() < 1e-6: C = V @ np.diag(np.clip(w, 1e-6, None)) @ V.T; dg = np.sqrt(np.diag(C)); C = C / np.outer(dg, dg)
    return C

def draw_states(rng, hz, n, independent=False, pscale=1.0, taiwan_x=1.0):
    names = ["demand"] + list(OVERLAYS); L = np.linalg.cholesky(corr_matrix(names, CORR, independent))
    z = rng.standard_normal((n, len(names))) @ L.T; z = {nm: z[:, i] for i, nm in enumerate(names)}
    p_sq = min(0.95, STATE_P["TSMC squeeze / AI pause"][hz] * pscale); p_ph = min(0.95, STATE_P["Smartphone second leg"][hz] * pscale); p_bm = STATE_P["AI packaging boom"][hz]
    p_base = 1 - p_sq - p_ph - p_bm; d = z["demand"]; c1, c2, c3 = norm.ppf(p_sq), norm.ppf(p_sq + p_ph), norm.ppf(p_sq + p_ph + p_base)
    on = {"TSMC squeeze / AI pause": d < c1, "Smartphone second leg": (d >= c1) & (d < c2), "Base plateau": (d >= c2) & (d < c3), "AI packaging boom": d >= c3}
    for s, p in OVERLAYS.items():
        pp = p[hz] * (taiwan_x if s.startswith("Taiwan") else 1.0) * (pscale if s in NEG else 1.0); on[s] = z[s] < norm.ppf(min(0.95, pp))
    return on, dict(squeeze=p_sq, phone=p_ph, base=p_base, boom=p_bm)

def simulate(hz, variant="b", sigma=None, overrides=None, seed=SEED):
    inp = dict(INP); ov = overrides or {}; inp.update({k: v for k, v in ov.items() if k in inp})
    rng = np.random.default_rng(seed + hz); years = 1.0 if hz == 0 else 2.0; n = N
    slope = 0.0 if variant == "a" else ov.get("slope", SLOPE); resid = inp["resid_d"] if variant == "d" else inp["resid_b"]; resid = ov.get("resid", resid)
    eb_lo, eb_md, eb_hi = inp["ebitda12"] if hz == 0 else inp["ebitda24"]
    base_eb = rng.triangular(eb_lo, eb_md, eb_hi, n); r_lo, r_hi = inp["mult_ratio"]; base_m = inp["fwd_mult"] * rng.triangular(r_lo, 1.0, r_hi, n)
    on, pst = draw_states(rng, hz, n, independent=(variant == "c"), pscale=ov.get("pscale", 1.0), taiwan_x=ov.get("taiwan_x", 1.0))
    eb_fac, m_fac = np.ones(n), np.ones(n)
    for s, d in IMPACT.items():
        k = on[s]; m = int(k.sum()); eb_fac[k] *= 1 + rng.uniform(*d["eb"], m); m_fac[k] *= rng.uniform(*d["mult"], m)
    sig = (sigma if sigma is not None else inp.get("sigma", 0.0)) * np.sqrt(years); noise = np.exp(rng.normal(-0.5 * sig ** 2, sig, n))
    ebitda = base_eb * eb_fac * noise; mult = base_m * m_fac * np.exp(-slope * years * resid)
    value = (ebitda * mult + inp["netcash"]) / inp["shares"]; ret = value / inp["price"] - 1
    pure = on["Base plateau"] & ~np.any(np.column_stack([on[s] for s in OVERLAYS if s != "Arizona on time"]), axis=1)
    return dict(value=value, ret=ret, ebitda=ebitda, mult=mult, on=on, p_base=float(pure.mean()), state_p=pst, sigma=sig, hurdle=(1 + HURDLE) ** years - 1, inp=inp)

def calibrate_sigma(target):
    mode = INP["ebitda12"][1]; lo, hi = 0.0, 0.8
    for _ in range(30):
        mid = (lo + hi) / 2; r = simulate(0, "b", sigma=mid); p10 = np.quantile(r["ebitda"] / mode - 1, 0.10)
        lo, hi = (mid, hi) if p10 > target else (lo, mid)
    return (lo + hi) / 2

def stats(r):
    v, ret, h = r["value"], r["ret"], r["hurdle"]; q = np.quantile(v, [0.05, 0.25, 0.5, 0.75, 0.95])
    return dict(mean_value=v.mean(), median_value=q[2], p05=q[0], p25=q[1], p75=q[3], p95=q[4], exp_return=ret.mean(), median_return=np.median(ret), p_loss_raw=float(np.mean(ret < 0)),
                p_below_hurdle=float(np.mean(ret < h)), hurdle=h, p_gt15=float(np.mean(ret > 0.15)), p_gt30=float(np.mean(ret > 0.30)), ret_p05=np.quantile(ret, 0.05), ret_p95=np.quantile(ret, 0.95))

def main():
    s_main = max(calibrate_sigma(INP["p10_main"]), SIGMA_FLOOR); s_alt = max(calibrate_sigma(INP["p10_alt"]), SIGMA_FLOOR); INP["sigma"] = s_main
    summary, tree, tornado, xcheck, entry = [], [], [], [], []; res = {}
    for var in ("a", "b", "c", "d"):
        for hz, lab in ((0, "12m"), (1, "24m")):
            r = simulate(hz, var); res[(var, lab)] = r; s = stats(r)
            s.update(variant=var, horizon=lab, sigma_idio=r["sigma"], sigma_label="main", p_base=r["p_base"], state_p=json.dumps({k: round(v, 3) for k, v in r["state_p"].items()})); summary.append(s)
            if var == "b":
                r2 = simulate(hz, var, sigma=s_alt); s2 = stats(r2); s2.update(variant=var, horizon=lab, sigma_idio=r2["sigma"], sigma_label="alt (raw p10)", p_base=r2["p_base"], state_p=""); summary.append(s2)
    for var in ("a", "b", "d"):
        for hz, lab in ((0, "12m"), (1, "24m")):
            r = res[(var, lab)]; ret, on = r["ret"], r["on"]
            for sc, k in on.items():
                if k.sum() == 0: continue
                p = float(k.mean()); cm = float(ret[k].mean())
                if sc in STATES: contrib, kind = p * cm, "exclusive state: P x E[ret|state]"
                else: contrib, kind = p * (cm - float(ret[~k].mean())), "overlay: P x (E[ret|on] - E[ret|off])"
                tree.append(dict(variant=var, horizon=lab, scenario=sc, prob=p, cond_median_value=float(np.median(r["value"][k])), cond_mean_return=cm, cond_p_loss_raw=float(np.mean(ret[k] < 0)), contribution=contrib, kind=kind))
    for var in ("a", "b"):
        base = stats(simulate(0, var))["exp_return"]; fm = INP["fwd_mult"]; e12 = INP["ebitda12"]
        cases = {"forward multiple +/-1 turn": (dict(fwd_mult=fm - 1), dict(fwd_mult=fm + 1)), "FY1 EBITDA +/-10%": (dict(ebitda12=tuple(x * 0.9 for x in e12)), dict(ebitda12=tuple(x * 1.1 for x in e12))),
                 "negative-scenario probabilities x1.5 / x0.5": (dict(pscale=1.5), dict(pscale=0.5)), "Taiwan halt P x4 / x0 (10% / 0%)": (dict(taiwan_x=4.0), dict(taiwan_x=0.0)),
                 "reversion slope 0 / -0.5 per year": (dict(slope=0.0), dict(slope=0.5)), f"residual {INP['resid_broad']} (broad) / {INP['resid_d']} (half)": (dict(resid=INP["resid_broad"]), dict(resid=INP["resid_d"]))}
        for lab, (lo_o, hi_o) in cases.items():
            if var == "a" and lab.startswith(("reversion", "residual")): continue
            lo_r = stats(simulate(0, var, overrides=lo_o))["exp_return"]; hi_r = stats(simulate(0, var, overrides=hi_o))["exp_return"]
            tornado.append(dict(variant=var, input=lab, exp_return_base=base, exp_return_low=lo_r, exp_return_high=hi_r, swing=abs(hi_r - lo_r)))
    for var in ("a", "b"):
        r = res[(var, "12m")]; logret = np.log(r["value"] / INP["price"]); sim_sd, med = logret.std(), np.median(logret)
        for ref, sd_ref, p05, p95 in (("Amkor own history", INP["hist_sd12"], INP["hist_p05"], INP["hist_p95"]), ("OSAT peers pooled", INP["group_sd12"], INP["group_p05"], INP["group_p95"])):
            sc = med + (logret - med) * (sd_ref / sim_sd); rr = np.exp(sc) - 1
            xcheck.append(dict(variant=var, reference=ref, sim_sd_log=sim_sd, hist_sd_log=sd_ref, sim_p05_log=np.quantile(logret, 0.05), hist_p05_log=p05, sim_p95_log=np.quantile(logret, 0.95), hist_p95_log=p95,
                               sim_p_loss_raw=float(np.mean(r["ret"] < 0)), histvol_p_loss_raw=float(np.mean(rr < 0)), histvol_p_below_hurdle=float(np.mean(rr < HURDLE)), histvol_exp_return=float(rr.mean()), hist_share_negative_actual=INP["hist_share_negative"]))
    for var in ("a", "b", "d"):
        for hz, lab in ((0, "12m"), (1, "24m")):
            r = res[(var, lab)]; v = r["value"]; q35, m15 = float(np.quantile(v, 0.35)), float(v.mean() / 1.15); q35h = q35 / (1 + r["hurdle"])
            entry.append(dict(variant=var, horizon=lab, price=INP["price"], entry_p_loss_raw_lt_35=q35, entry_exp_ret_gt_15=m15, entry_price=min(q35, m15), discount_to_price=min(q35, m15) / INP["price"] - 1, entry_p_below_hurdle_lt_35=q35h, entry_price_hurdle_basis=min(q35h, m15)))
    df = pd.DataFrame(summary); df.to_csv(TABLES / "amkr_sim_summary.csv", index=False)
    pd.DataFrame(tree).to_csv(TABLES / "amkr_sim_scenario_tree.csv", index=False); pd.DataFrame(tornado).sort_values(["variant", "swing"], ascending=[True, False]).to_csv(TABLES / "amkr_sim_tornado.csv", index=False)
    pd.DataFrame(xcheck).to_csv(TABLES / "amkr_sim_crosscheck.csv", index=False); pd.DataFrame(entry).to_csv(TABLES / "amkr_sim_entry_prices.csv", index=False)
    pd.DataFrame([dict(fwd_mult_today_jun26_bs=INP["fwd_mult"], fwd_mult_fy25_bs=INP["fwd_mult_fy25bs"], sigma_main=s_main, sigma_alt=s_alt, resid_b=INP["resid_b"], resid_d=INP["resid_d"], fy1_ebitda=INP["ebitda12"][1], fy2_ebitda_mode=INP["ebitda24"][1], netcash=INP["netcash"], shares=INP["shares"], price=INP["price"])]).to_csv(TABLES / "amkr_sim_inputs.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    print("fwd mult", round(INP["fwd_mult"], 3), "fy25 bs", round(INP["fwd_mult_fy25bs"], 3), "sigma", round(s_main, 3), round(s_alt, 3))
    print(df[["variant", "horizon", "sigma_label", "mean_value", "median_value", "p05", "p95", "exp_return", "p_loss_raw", "p_below_hurdle", "p_gt15", "p_gt30", "ret_p05", "p_base", "state_p"]].round(3).to_string())
    print(pd.DataFrame(tree).round(3).to_string()); print(pd.DataFrame(tornado).sort_values(["variant", "swing"], ascending=[True, False]).round(3).to_string()); print(pd.DataFrame(xcheck).round(3).to_string()); print(pd.DataFrame(entry).round(2).to_string())

if __name__ == "__main__":
    main()
