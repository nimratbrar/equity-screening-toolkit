"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

HDE analysis 4: scenario-mixture Monte Carlo (20,000 paths, fixed seed) on the house conventions
(methodology/amkor/amkor_final.py, methodology/atkins/atkins_final.py, docs/METHODOLOGY.md):
 C1 Value struck on the forward year not yet reported: 12m on FY+1 EBITDA, 24m on FY+2, each times today's forward EV/EBITDA,
    plus net cash at the horizon, over the latest share count. No extra discounting.
 C2 Same-date balance sheet: latest-quarter Compustat dltt + dlc - che = net debt (lease-inclusive) and the company's share
    count (issued less treasury) [company filing]. Today's forward multiple = EV / FY1 consensus EBITDA [I/B/E/S via WRDS].
    The company's own net cash (ex leases) is not the valuation basis.
 C3 Base exit multiple = today's forward multiple x triangular(0.80, 1.00, 1.20): mean 1.00, no built-in re-rating.
 C4 Four exclusive states on one latent, summing to 100% (probabilities below are analyst judgments) [inference, illustrative].
    EBITDA impacts are 24m ranges, half at 12m; multiple factors in full at both horizons (multiple moves first).
 C5 Overlays separate from states. Two-sided where an outside-base upside exists, on the same latent so branches exclude each other:
    tariff (step-up vs relief), won (+10% vs -10%), Gulf (disruption vs acceleration).
    One-sided tails with no symmetric upside outside the base: localisation, labour, peninsula, US recession (correlated with the
    low-demand latent). Expected overlay effects are printed. A tariff step dated after the 12m horizon touches only the multiple at 12m.
 C6 Reversion residual from the matching model basis: broad house model m4 (the basis of the -0.25 a year slope), HDE minus grid-peer
    median residual (hde_multiples_broad.csv). Variants: (a) no reversion [headline], (b) reversion, (o) own-history vol:
    (a) with log value dispersion rescaled to HDE's realised 12m log sd (overlapping windows) and that sd x sqrt(2) at 24m
    (square-root-of-time).
 C7 Raw P(loss) (value < price) and P(below 9% a year hurdle: 9.0% at 12m, 18.8% at 24m) reported separately.
 C8 Entry price = min(35th percentile of value, mean value / 1.15) [house rule].
FY+1 EBITDA (bottom-up, [inference, illustrative]): USD sales triangular x spot KRW/USD x EBITDA margin triangular, built from backlog
conversion (hde_backlog_conversion.csv), capacity and price/mix. Consensus path (sensitivity): I/B/E/S FY1 EBITDA x FY2/FY1 EPS growth.
FY+2 = FY+1 x tri(1.00, 1.08, 1.16).
Idiosyncratic sigma: calibrated so the 12m p10 of EBITDA vs mode matches the p10 of grid-peer log EBITDA growth minus the
peer-year median (hde_ebitda_base_rates.csv, deviation basis).
Net cash at horizon [inference]: today's net cash + FCF (share of EBITDA) - dividends (payout).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_simulate.py   (about 1 min)
Outputs: tables/hde_sim_summary.csv (headline), hde_sim_scenario_tree.csv, hde_sim_tornado.csv, hde_sim_sensitivity.csv,
hde_sim_inputs.csv, hde_valuation_cases.csv. Every simulated number is [inference].
"""
import numpy as np, pandas as pd
from scipy.stats import norm
from hde_common import HDE_IN, TABLES, FX

SEED, N, HURDLE, SLOPE = 20261020, 20000, 0.09, 0.25
P0, SH, FM = HDE_IN["price"] / 1000.0, HDE_IN["shares_jun26"], HDE_IN["fwd_mult"]      # price in KRW thousand; KRW bn / m shares = KRW thousand
SPOT = FX["spot"]                                                                         # [placeholder in hde_common.FX]
FY2 = (3.40 * SPOT * 0.245, 3.60 * SPOT * 0.262, 3.85 * SPOT * 0.280)                     # KRW bn (USD bn x KRW/USD = KRW bn) [inference, illustrative]
FY2_CONS = HDE_IN["ebitda_fy1_cons"] * HDE_IN["eps_fy2"] / HDE_IN["eps_fy1"]
G3 = (1.00, 1.08, 1.16)                                                                   # [inference, illustrative]
RESID = float(pd.read_csv(TABLES / "hde_multiples_broad.csv").set_index("model").loc["broad m4: peer industries (house model)", "hde_minus_grid_median"])
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
NC = {0: 800.0, 1: 1100.0}                 # [placeholder: net cash at 12m / 24m, built on Compustat net debt + FCF - dividends]
SD_OWN = {0: 0.40, 1: 0.40 * np.sqrt(2)}   # [placeholder: own realised 12m log-return sd from your price file, sqrt-time at 24m]
P10_DEV = -0.20                            # [placeholder: p10 of peer log EBITDA growth minus peer-year median, Compustat]
FM_BOTTOM_UP_FY1 = 1100.0                  # [placeholder: bottom-up FY1 EBITDA, KRW bn, for the multiple sensitivity]
SD_LAST1Y = 0.60                           # [placeholder: annualised daily vol over the last year]
SD_24M_REALISED = 0.50                     # [placeholder: realised overlapping 24m log-return sd]
RESID_RAW_M4, RESID_GRID_FWD = 0.15, -0.50 # [placeholder: alternative residual bases from hde_multiples.py output]
MULT_LOW_CASE = 10.0                       # [placeholder: low-multiple valuation case, e.g. regional peer forward range]
# ===== END PLACEHOLDER INPUTS =====

STATES = ["AI capex pause", "Supply-led turn", "Base: tight plateau", "Super-cycle extends"]     # worst to best on the demand latent
# Scenario probabilities, impacts and correlations are analyst judgments [inference, illustrative].
STATE_P = {"AI capex pause": (0.12, 0.18), "Supply-led turn": (0.10, 0.20), "Super-cycle extends": (0.18, 0.20)}
IMPACT = {  # EBITDA (lo, hi) at 24m, mult factor (lo, hi) [inference, illustrative]; 'eb12' overrides the half-at-12m rule
    "AI capex pause": dict(eb=(-0.15, -0.06), mult=(0.60, 0.80)), "Supply-led turn": dict(eb=(-0.10, -0.04), mult=(0.70, 0.85)),
    "Base: tight plateau": dict(eb=(0.0, 0.0), mult=(1.0, 1.0)), "Super-cycle extends": dict(eb=(0.10, 0.20), mult=(1.10, 1.25)),
    "O1 tariff step-up to 25%": dict(eb=(-0.08, -0.03), mult=(0.90, 0.97), eb12=(0.0, 0.0)),
    "O1 tariff relief": dict(eb=(0.01, 0.03), mult=(1.00, 1.03), eb12=(0.0, 0.0)),
    "O2 US localisation rule": dict(eb=(-0.12, -0.04), mult=(0.85, 0.95)),
    "O3 won +10% further": dict(eb=(-0.18, -0.08), mult=(1.0, 1.0)), "O3 won -10%": dict(eb=(0.08, 0.18), mult=(1.0, 1.0)),
    "O4 Gulf disruption": dict(eb=(-0.05, -0.02), mult=(0.97, 1.00)), "O4 Gulf acceleration": dict(eb=(0.01, 0.03), mult=(1.00, 1.00)),
    "O5 labour disruption": dict(eb=(-0.03, -0.01), mult=(1.0, 1.0)), "O6 peninsula conflict": dict(eb=(-0.50, -0.20), mult=(0.60, 0.80)),
    "O7 US recession": dict(eb=(-0.04, 0.0), mult=(0.85, 0.95)),
}
# overlay latents: (name of down branch, P down, name of up branch or None, P up)
OVL = {"tariff": ("O1 tariff step-up to 25%", (0.20, 0.40), "O1 tariff relief", (0.05, 0.10)),
       "local": ("O2 US localisation rule", (0.05, 0.12), None, None),
       "won": ("O3 won +10% further", (0.15, 0.20), "O3 won -10%", (0.12, 0.18)),
       "gulf": ("O4 Gulf disruption", (0.15, 0.20), "O4 Gulf acceleration", (0.10, 0.15)),
       "labour": ("O5 labour disruption", (0.08, 0.15), None, None), "pen": ("O6 peninsula conflict", (0.015, 0.03), None, None),
       "rec": ("O7 US recession", (0.08, 0.30), None, None)}
CORR = {("demand", "rec"): 0.5, ("pen", "won"): -0.3}       # signed latent correlations [inference, illustrative]
NEG = ["AI capex pause", "Supply-led turn"]

def corr_matrix(names):
    C = np.eye(len(names)); ix = {n: i for i, n in enumerate(names)}
    for (a, b), r in CORR.items(): C[ix[a], ix[b]] = C[ix[b], ix[a]] = r
    return C

def draw(rng, hz, n, ov):
    names = ["demand"] + list(OVL); z = rng.standard_normal((n, len(names))) @ np.linalg.cholesky(corr_matrix(names)).T; z = {k: z[:, i] for i, k in enumerate(names)}
    ps = ov.get("pscale", 1.0); p_ai, p_tu, p_sc = STATE_P["AI capex pause"][hz] * ps, STATE_P["Supply-led turn"][hz] * ps, STATE_P["Super-cycle extends"][hz]
    p_b = 1 - p_ai - p_tu - p_sc; assert p_b > 0; d = z["demand"]; c1, c2, c3 = norm.ppf(p_ai), norm.ppf(p_ai + p_tu), norm.ppf(p_ai + p_tu + p_b)
    on = {"AI capex pause": d < c1, "Supply-led turn": (d >= c1) & (d < c2), "Base: tight plateau": (d >= c2) & (d < c3), "Super-cycle extends": d >= c3}
    for k, (dn, pd_, up, pu) in OVL.items():
        pdn = ov.get("p_" + k, pd_)[hz]
        on[dn] = (z[k] < norm.ppf(min(pdn, 0.999))) if pdn > 0 else np.zeros(n, bool)
        if up: on[up] = ((z[k] > norm.ppf(1 - pu[hz])) & ~on[dn]) if ov.get("p_" + k + "_up", 1) else np.zeros(n, bool)
    return on, dict(ai=p_ai, turn=p_tu, base=p_b, super=p_sc)

def simulate(hz, variant="a", sigma=None, ov=None, seed=SEED):
    ov = ov or {}; rng = np.random.default_rng(seed + hz); years = 1.0 if hz == 0 else 2.0
    fy2 = ov.get("fy2", FY2); fm = ov.get("fm", FM)
    base = rng.triangular(*fy2, N)
    if hz == 1: base = base * rng.triangular(*ov.get("g3", G3), N)
    m = fm * rng.triangular(0.80, 1.0, 1.20, N)
    on, pst = draw(rng, hz, N, ov)
    ebf, mf = np.ones(N), np.ones(N)
    for s, d in IMPACT.items():
        k = on[s]; c = int(k.sum())
        lo, hi = (d["eb12"] if (hz == 0 and "eb12" in d) else tuple(x * (0.5 if hz == 0 else 1.0) for x in d["eb"]))
        if s.startswith("O3") and "fx_scale" in ov: lo, hi = lo * ov["fx_scale"], hi * ov["fx_scale"]
        ebf[k] *= 1 + rng.uniform(lo, hi, c); mf[k] *= rng.uniform(*d["mult"], c)
    sg = (sigma if sigma is not None else SIGMA) * np.sqrt(years)
    eb = base * ebf * np.exp(rng.normal(-0.5 * sg ** 2, sg, N))
    slope = 0.0 if variant == "a" else ov.get("slope", SLOPE)
    mult = m * mf * np.exp(-slope * years * ov.get("resid", RESID))
    value = (eb * mult + ov.get("nc", NC)[hz]) / SH
    return dict(value=value, eb=eb, on=on, pst=pst, hurdle=(1 + HURDLE) ** years - 1, mode=(fy2[1] if hz == 0 else fy2[1] * G3[1]))

def calibrate_sigma():
    lo, hi = 0.0, 0.8
    for _ in range(30):
        mid = (lo + hi) / 2; r = simulate(0, sigma=mid); p10 = np.quantile(r["eb"] / r["mode"] - 1, 0.10)
        lo, hi = (mid, hi) if p10 > P10_DEV else (lo, mid)
    return (lo + hi) / 2
SIGMA = 0.0
SIGMA = max(calibrate_sigma(), 0.05)

def own_vol(v, sd):
    lv = np.log(np.clip(v, 1e-3, None)); med = np.median(lv); return np.exp(med + (lv - med) * sd / lv.std())

def summ(label, hz, v, h, extra=None):
    r = v / P0 - 1; q = np.quantile(v, [0.05, 0.25, 0.35, 0.5, 0.75, 0.95]); m15 = v.mean() / 1.15
    row = dict(variant=label, horizon="12m" if hz == 0 else "24m", price_krw=P0 * 1000, exp_return=r.mean(), median_return=np.median(r), p_loss_raw=float((r < 0).mean()),
               hurdle=h, p_below_hurdle=float((r < h).mean()), p_gt15=float((r > 0.15).mean()), ret_p05=q[0] / P0 - 1, ret_p25=q[1] / P0 - 1, ret_p75=q[4] / P0 - 1, ret_p95=q[5] / P0 - 1,
               value_p05_krw=q[0] * 1000, value_p50_krw=q[3] * 1000, value_p95_krw=q[5] * 1000, mean_value_krw=v.mean() * 1000,
               entry_q35_krw=q[2] * 1000, entry_mean_over_1p15_krw=m15 * 1000, entry_price_krw=min(q[2], m15) * 1000, entry_vs_price=min(q[2], m15) / P0 - 1,
               log_sd=float(np.log(np.clip(v, 1e-3, None) / P0).std()))
    row.update(extra or {}); return row

def run(label, variant="a", ov=None, own=None):
    out = []
    for hz in (0, 1):
        r = simulate(hz, variant, ov=ov); v = r["value"]
        if own: v = own_vol(v, own[hz])
        out.append(summ(label, hz, v, r["hurdle"], dict(**{f"p_{k}": x for k, x in r["pst"].items()})))
    return out

if __name__ == "__main__":
    head = run("(a) no reversion [headline]") + run(f"(b) reversion, resid {RESID:+.3f} (broad m4 minus grid median), slope -0.25", "b") + \
           run("(o) own-history volatility, no reversion (sd per SD_OWN)", own=SD_OWN)
    S = pd.DataFrame(head); S.to_csv(TABLES / "hde_sim_summary.csv", index=False)

    # scenario tree and expected overlay effects (variant a)
    tree = []
    for hz in (0, 1):
        r = simulate(hz); ret = r["value"] / P0 - 1
        for s, k in r["on"].items():
            p = float(k.mean())
            if p == 0: continue
            if s in STATES: c, kind = p * ret[k].mean(), "state: P x E[ret|state]"
            else: c, kind = p * (ret[k].mean() - ret[~k].mean()), "overlay: P x (E[ret|on] - E[ret|off])"
            tree.append(dict(horizon="12m" if hz == 0 else "24m", scenario=s, prob=p, cond_mean_return=ret[k].mean(), cond_median_value_krw=np.median(r["value"][k]) * 1000,
                             cond_p_loss_raw=float((ret[k] < 0).mean()), contribution=c, kind=kind))
    T = pd.DataFrame(tree); T.to_csv(TABLES / "hde_sim_scenario_tree.csv", index=False)

    # tornado, 12m, variant a
    b0 = simulate(0)["value"].mean() / P0 - 1; tor = []
    cases = {"FY2027 EBITDA mode -10% / +10%": (dict(fy2=tuple(x * 0.9 for x in FY2)), dict(fy2=tuple(x * 1.1 for x in FY2))),
             "forward multiple -2 / +2 turns": (dict(fm=FM - 2), dict(fm=FM + 2)),
             "negative-state probabilities x1.5 / x0.5": (dict(pscale=1.5), dict(pscale=0.5)),
             "won overlay impact x1.5 / x0.5": (dict(fx_scale=1.5), dict(fx_scale=0.5)),
             "FY2 consensus path (high) vs bottom-up low": (dict(fy2=(FY2[0] * 0.95, FY2[0], FY2[0] * 1.05)), dict(fy2=(FY2_CONS * 0.95, FY2_CONS, FY2_CONS * 1.05))),
             "multiple on bottom-up FY1 vs consensus": (dict(), dict(fm=HDE_IN["ev"] / FM_BOTTOM_UP_FY1)),
             "net cash at 12m: today (no FCF) / +25%": (dict(nc={0: -HDE_IN["net_debt_jun26"], 1: -HDE_IN["net_debt_jun26"]}), dict(nc={0: NC[0] * 1.25, 1: NC[1] * 1.25}))}
    for lab, (lo, hi) in cases.items():
        lo_r = simulate(0, ov=lo)["value"].mean() / P0 - 1; hi_r = simulate(0, ov=hi)["value"].mean() / P0 - 1
        tor.append(dict(input=lab, exp_return_base=b0, exp_return_low=lo_r, exp_return_high=hi_r, swing=abs(hi_r - lo_r)))
    TOR = pd.DataFrame(tor).sort_values("swing", ascending=False); TOR.to_csv(TABLES / "hde_sim_tornado.csv", index=False)

    # sensitivities (both horizons)
    sens = []
    sens += run("no reversion, FY2 on consensus path", ov=dict(fy2=(FY2_CONS * 0.92, FY2_CONS, FY2_CONS * 1.05)))
    sens += run("no reversion, bottom-up at 1,450 KRW/USD (margin tri 26.0/27.5/29.0%) [inference, illustrative]", ov=dict(fy2=(3.40 * 1450 * 0.260, 3.60 * 1450 * 0.275, 3.85 * 1450 * 0.290)))
    sens += run("no reversion, multiple on bottom-up FY1", ov=dict(fm=HDE_IN["ev"] / FM_BOTTOM_UP_FY1))
    sens += run("no reversion, tariff step at statutory path (P 0 / 100%, no relief)", ov=dict(p_tariff=(0.0, 0.999), p_tariff_up=0))
    sens += run("no reversion, one-sided overlays (no relief, no weak won, no Gulf upside)", ov=dict(p_tariff_up=0, p_won_up=0, p_gulf_up=0))
    sens += run("reversion, resid on raw m4", "b", ov=dict(resid=RESID_RAW_M4))
    sens += run("reversion, resid on grid forward median spec (not the slope basis)", "b", ov=dict(resid=RESID_GRID_FWD))
    sens += run("own-history vol, last-1y daily vol", own={0: SD_LAST1Y, 1: SD_LAST1Y * np.sqrt(2)})
    sens += run("own-history vol, realised overlapping 24m sd at 24m", own={0: SD_OWN[0], 1: SD_24M_REALISED})
    SE = pd.DataFrame(sens); SE.to_csv(TABLES / "hde_sim_sensitivity.csv", index=False)

    # deterministic valuation cases (section 6): FY2027 x multiple + net cash Sep-27, per share KRW
    peer_med = float(pd.read_csv(TABLES / "hde_multiples_peer_specs.csv").peer_median.iloc[0])
    vc = []
    def case(lab, eb, mult, nc=NC[0], note=""):
        v = (eb * mult + nc) / SH; vc.append(dict(case=lab, fy2027_ebitda=eb, multiple=mult, net_cash=nc, value_krw=v * 1000, vs_price=v / P0 - 1, note=note))
    case("central: bottom-up FY+1 x today's forward multiple", FY2[1], FM)
    case("central at grid-peer forward median", FY2[1], peer_med, note="peer median ex HDE [WRDS data]")
    case("central at the low-multiple case", FY2[1], MULT_LOW_CASE)
    case("consensus FY2 path x today's forward multiple", FY2_CONS, FM)
    case("upside: super-cycle (EBITDA +15% at 24m, half at 12m; multiple x1.175)", FY2[1] * 1.075, FM * 1.175)
    case("upside 24m: super-cycle on FY+2 (+15%, multiple x1.175, 24m net cash)", FY2[1] * G3[1] * 1.15, FM * 1.175, NC[1])
    case("downside: AI pause + won +10% (EBITDA -10.5% and -13%, half at 12m; multiple x0.70)", FY2[1] * (1 - 0.0525) * (1 - 0.065), FM * 0.70)
    case("downside 24m: AI pause + won + tariff step (EBITDA -10.5%, -13%, -5.5%; multiple x0.70 x0.935)", FY2[1] * G3[1] * (1 - 0.105) * (1 - 0.13) * (1 - 0.055), FM * 0.70 * 0.935, NC[1])
    case("supply-led turn 24m (EBITDA -7%, multiple x0.775)", FY2[1] * G3[1] * 0.93, FM * 0.775, NC[1])
    bl_spot = HDE_IN["backlog_usd_m"] * SPOT / 1000
    VC = pd.DataFrame(vc)
    VC = pd.concat([VC, pd.DataFrame([dict(case="backlog KRW bn at spot (backlog USD x spot)", value_krw=bl_spot), dict(case="backlog / LTM sales (x)", value_krw=bl_spot / HDE_IN["ltm_sales"]),
                                      dict(case="EV / backlog (x)", value_krw=HDE_IN["ev"] / bl_spot), dict(case="backlog EBITDA at 26% (KRW bn)", value_krw=bl_spot * 0.26),
                                      dict(case="EV / backlog EBITDA (x)", value_krw=HDE_IN["ev"] / (bl_spot * 0.26)),
                                      dict(case="share of FY+1 USD sales covered by year-end backlog", value_krw=1.0, note="FY+1 USD sales mode vs projected year-end backlog [inference]")])])
    VC.to_csv(TABLES / "hde_valuation_cases.csv", index=False)
    inputs = dict(price_krw=P0 * 1000, shares_m=SH, net_debt_jun26=HDE_IN["net_debt_jun26"], ev=HDE_IN["ev"], fy1_cons=HDE_IN["ebitda_fy1_cons"], fwd_mult=FM,
                  fy2_lo=FY2[0], fy2_mode=FY2[1], fy2_hi=FY2[2], fy2_consensus_path=FY2_CONS, fy3_mode=FY2[1] * G3[1], sigma=SIGMA, resid=RESID, nc12=NC[0], nc24=NC[1], spot=SPOT, peer_fwd_median=peer_med)
    pd.Series(inputs).to_csv(TABLES / "hde_sim_inputs.csv")

    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40); pd.set_option("display.max_colwidth", 70)
    print({k: round(v, 3) for k, v in inputs.items()})
    cols = ["variant", "horizon", "exp_return", "median_return", "p_loss_raw", "p_below_hurdle", "p_gt15", "ret_p05", "ret_p95", "value_p05_krw", "value_p50_krw", "value_p95_krw", "entry_price_krw", "entry_vs_price", "log_sd"]
    print(S[cols].round(3).to_string()); print(T.round(3).to_string()); print(TOR.round(3).to_string()); print(SE[cols].round(3).to_string()); print(VC.round(3).to_string())
    print("state P check 12m:", S.iloc[0][["p_ai", "p_turn", "p_base", "p_super"]].sum(), "24m:", S.iloc[1][["p_ai", "p_turn", "p_base", "p_super"]].sum())
