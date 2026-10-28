"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Scenario-mixture Monte Carlo, version 2 (after the red-team geopolitics and statistics challenge round).

Run:  ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/simulate_v2.py
Seeded, 20,000 paths per company, horizon and variant. Outputs methodology/scenario/tables/sim2_*.csv.

Changes from simulate.py (v1):
 1. Scenario inputs: the red-team corrected table. A Taiwan blockade is an OVERLAY that can co-occur with export
    controls and a memory downturn; gray-zone quarantine, AI capex pause, yen +10%, China retaliation on Japan, HV
    execution loss and a fab-project slip are added. Joint distribution: Gaussian copula with SIGNED pairwise
    correlations stated below (no fit to a target base probability); the base share is reported as it comes out.
 2. No discounting: 12m value = FY1 EBITDA x forward multiple (the forward multiple already prices FY1); 24m value =
    FY2 EBITDA (or the company target year) x forward multiple struck inside the horizon. Returns are vs today's price
    over the horizon; P(return < hurdle) is reported next to raw P(value < price).
 3. Multiples start at TODAY's forward multiple ((price x shares - net cash) / FY1 mode EBITDA), with low/high ratios
    from the peer spread as a triangular band, then scenario factors, then ONE mean-reversion step of SLOPE per year
    toward the fitted multiple (residual from reg_multiples.py; set to 0 where the residual is within model noise).
    Variants: (a) no reversion, (b) reversion, (c) reversion with independent shocks.
 4. One case gets two idiosyncratic sigmas (two plausible peer groups), both shown.
 5. Prices are the latest rows in the data layer; note the next reporting date of each company.
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from scipy.stats import norm

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import simulate as v1  # noqa: E402  (v1 engine, used only for the v1-to-v2 bridge)

SEED = 20261020
N = 20000
HURDLE = 0.09
SLOPE = 0.25          # mean reversion of the log multiple residual per year [illustrative; estimate your own with reg_multiples.py v2]
SIGMA_FLOOR = 0.05
TAB = os.path.join(HERE, "tables")

# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
# Every number in this block is made up and round on purpose. Units: EUR m / EUR per share; JPY bn, shares m, JPY per share.
#   price        latest close [placeholder: WRDS daily prices]
#   shares       diluted or outstanding shares, m [placeholder: company filing]
#   ebitda12     FY1 (low, mode, high): guidance range around the I/B/E/S consensus mode [placeholder]
#   ebitda24     FY2 or company medium-term target +/- a band [placeholder]
#   mult_ratio   low/high exit multiple relative to base, from the peer multiple spread [placeholder]
#   netcash12/24 net cash (negative = net debt incl. pensions) [placeholder: company filing]
#   resid        log residual of today's multiple vs the cross-section fit (reg_multiples.py) [placeholder]
#   p10_target   one-in-ten EBITDA fall for the peer group (reg_baserates.py) [placeholder]
#   hist_* / group_*  own and peer-group 12m log-return sd and 5/95 quantiles (reg_baserates.py) [placeholder]
INPUTS = {
    "Nexans": dict(ccy="EUR", price=100.0, shares=50.0,
                   ebitda12=(450.0, 500.0, 550.0), ebitda24=(550.0, 600.0, 650.0),
                   mult_ratio=(0.85, 1.15),
                   netcash12=-1000.0, netcash24=-1000.0,
                   resid=-0.20,
                   p10_target=-0.20, p10_alt=None,
                   hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
                   group="cable_grid", group_sd12=0.35, group_p05=-0.40, group_p95=0.55),
    "Organo": dict(ccy="JPY", price=2000.0, shares=100.0,
                   ebitda12=(14.0, 15.0, 16.0), ebitda24=(15.5, 17.0, 18.5),
                   mult_ratio=(0.85, 1.15),
                   netcash12=0.0, netcash24=0.0, resid=0.20, p10_target=-0.20, p10_alt=None,
                   hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
                   group="fab_water_facility", group_sd12=0.35, group_p05=-0.40, group_p95=0.55),
    "Japan Material": dict(ccy="JPY", price=1500.0, shares=100.0,
                           ebitda12=(11.0, 12.0, 13.0), ebitda24=(12.0, 13.5, 15.0),
                           mult_ratio=(0.85, 1.15),
                           netcash12=10.0, netcash24=10.0, resid=0.0,
                           p10_target=-0.20, p10_alt=-0.30,     # main peer-group target, alternative peer-group target
                           hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
                           group="fab_water_facility", group_sd12=0.35, group_p05=-0.40, group_p95=0.55),
    "Shin-Etsu": dict(ccy="JPY", price=5000.0, shares=2000.0,
                      ebitda12=(850.0, 900.0, 950.0), ebitda24=(900.0, 1000.0, 1100.0),
                      mult_ratio=(0.85, 1.15),
                      netcash12=1000.0, netcash24=1000.0, resid=0.0, p10_target=-0.30, p10_alt=None,
                      hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
                      group="chip_materials_and_chem", group_sd12=0.35, group_p05=-0.40, group_p95=0.55),
}
# ===== END PLACEHOLDER INPUTS =====
for nm, i in INPUTS.items():
    cap = i["price"] * i["shares"] / (1000.0 if i["ccy"] == "JPY" else 1.0)
    i["fwd_mult"] = (cap - i["netcash12"]) / i["ebitda12"][1]     # today's forward EV/EBITDA

# ------------------------------------------------------------------ Nexans scenario set (red-geo corrected)
# prob = (P12, P24); ebitda = (lo, hi) uniform % impact; mult = (lo, hi) uniform factor on the multiple
GRID2 = {
    "2 Grid super-cycle":      dict(prob=(0.15, 0.20), ebitda=(+0.06, +0.12), mult=(1.00, 1.15)),
    "3 Offshore wind stall":   dict(prob=(0.20, 0.25), ebitda=(-0.09, -0.04), mult=(0.92, 1.00)),
    "4 Copper spike":          dict(prob=(0.20, 0.25), ebitda=(-0.02, 0.00), mult=(1.00, 1.00), wc=(150.0, 250.0)),
    "5 Great Sea write-down":  dict(prob=(0.12, 0.22), ebitda=(-0.03, 0.00), mult=(0.95, 1.00), oneoff=(0.0, 100.0)),
    "6 European recession":    dict(prob=(0.15, 0.25), ebitda=(-0.14, -0.08), mult=(0.80, 0.92)),
    "7 HV execution loss":     dict(prob=(0.08, 0.15), ebitda=(-0.15, -0.05), mult=(0.90, 1.00)),
    "8 AI capex pause (common)": dict(prob=(0.10, 0.18), ebitda=(-0.06, -0.03), mult=(0.95, 1.00)),
    "9 Taiwan blockade (common)": dict(prob=(0.025, 0.06), ebitda=(-0.10, -0.05), mult=(0.90, 1.00)),
}
GRID2_CORR = {  # signed latent correlations [inference, illustrative; red-team geopolitics review plus common-factor links]
    ("2 Grid super-cycle", "3 Offshore wind stall"): -0.4,
    ("2 Grid super-cycle", "6 European recession"): -0.4,
    ("2 Grid super-cycle", "7 HV execution loss"): -0.4,
    ("3 Offshore wind stall", "6 European recession"): +0.4,
    ("4 Copper spike", "6 European recession"): -0.3,
    ("3 Offshore wind stall", "7 HV execution loss"): +0.2,
    ("6 European recession", "8 AI capex pause (common)"): +0.3,
    ("8 AI capex pause (common)", "9 Taiwan blockade (common)"): +0.3,
}

# ------------------------------------------------------------------ semis scenario set (red-geo corrected)
# Demand states are exclusive, ordered worst to best on one latent "demand" normal; base takes the residual.
SEMI2_STATES = ["AI capex pause", "Memory/NAND downturn", "Base plateau", "AI capex boom"]
SEMI2_STATE_P = {"AI capex pause": (0.10, 0.18), "Memory/NAND downturn": (0.15, 0.27), "AI capex boom": (0.22, 0.17)}
SEMI2_OVERLAYS = {
    "Taiwan blockade":            (0.025, 0.06),
    "Gray-zone quarantine":       (0.05, 0.10),
    "Export-control escalation":  (0.30, 0.45),
    "Yen +10%":                   (0.15, 0.20),
    "China retaliation on Japan": (0.15, 0.25),
    "Japan onshoring":            (0.20, 0.30),
    "Rapidus slip":               (0.10, 0.15),
}
SEMI2_CORR = {  # "demand" latent: low = downturn, high = boom
    ("demand", "Yen +10%"): -0.5,
    ("demand", "Taiwan blockade"): -0.3,
    ("Taiwan blockade", "Export-control escalation"): +0.5,
    ("Taiwan blockade", "Yen +10%"): +0.6,
    ("Taiwan blockade", "Gray-zone quarantine"): +0.3,
    ("Export-control escalation", "China retaliation on Japan"): +0.5,
    ("Japan onshoring", "Rapidus slip"): -0.7,
}
# impacts: company -> (lo, hi) EBITDA; 'ebitda_h' gives horizon-specific ranges; mult = multiple factor
SEMI2_IMPACT = {
    "AI capex boom":        dict(mult=(1.00, 1.15), Organo=(+0.08, +0.18), JM=(+0.08, +0.15), SE=(+0.06, +0.12)),
    "Memory/NAND downturn": dict(mult=(0.80, 0.95), Organo_h=((-0.08, 0.00), (-0.12, -0.05)),
                                 JM=(-0.30, -0.05), SE=(-0.09, -0.05)),
    "AI capex pause":       dict(mult=(0.70, 0.85), Organo=(-0.15, -0.05), JM=(-0.30, -0.15), SE=(-0.25, -0.15)),
    "Base plateau":         dict(mult=(1.00, 1.00), Organo=(0, 0), JM=(0, 0), SE=(0, 0)),
    "Taiwan blockade":      dict(mult=(0.70, 0.90), Organo=(-0.35, -0.15), JM=(-0.35, -0.20), SE=(-0.25, -0.15)),
    "Gray-zone quarantine": dict(mult=(0.85, 0.95), Organo=(-0.08, -0.03), JM=(-0.03, 0.0), SE=(-0.06, -0.03)),
    "Export-control escalation": dict(mult=(0.95, 1.00), Organo=(-0.04, -0.01), JM=(-0.02, 0.0), SE=(-0.06, -0.03)),
    "Yen +10%":             dict(mult=(1.00, 1.00), Organo=(-0.03, -0.01), JM=(0, 0), SE=(-0.08, -0.05)),
    "China retaliation on Japan": dict(mult=(0.97, 1.00), Organo=(-0.02, 0.0), JM=(0, 0), SE=(-0.08, -0.03)),
    "Japan onshoring":      dict(mult=(1.00, 1.08), Organo=(+0.05, +0.12), JM=(+0.05, +0.10), SE=(+0.01, +0.03)),
    "Rapidus slip":         dict(mult=(0.97, 1.00), Organo=(-0.05, -0.02), JM=(-0.05, -0.02), SE=(0, 0)),
}
SEMI_KEY = {"Organo": "Organo", "Japan Material": "JM", "Shin-Etsu": "SE"}


# ------------------------------------------------------------------ copula helpers
def corr_matrix(names, pairs, independent=False):
    k = len(names)
    C = np.eye(k)
    if not independent:
        idx = {n: i for i, n in enumerate(names)}
        for (a, b), r in pairs.items():
            C[idx[a], idx[b]] = C[idx[b], idx[a]] = r
    w, V = np.linalg.eigh(C)
    if w.min() < 1e-6:                      # nearest PSD by eigenvalue clipping, then unit diagonal
        C = V @ np.diag(np.clip(w, 1e-6, None)) @ V.T
        d = np.sqrt(np.diag(C))
        C = C / np.outer(d, d)
    return C


def draw_latent(rng, names, pairs, n, independent=False):
    C = corr_matrix(names, pairs, independent)
    L = np.linalg.cholesky(C)
    z = rng.standard_normal((n, len(names))) @ L.T
    return {nm: z[:, i] for i, nm in enumerate(names)}


def draw_grid_states(rng, hz, n, independent=False):
    names = list(GRID2)
    z = draw_latent(rng, names, GRID2_CORR, n, independent)
    on = {s: z[s] < norm.ppf(GRID2[s]["prob"][hz]) for s in names}
    return on


def draw_semi_states(rng, hz, n, independent=False):
    names = ["demand"] + list(SEMI2_OVERLAYS)
    z = draw_latent(rng, names, SEMI2_CORR, n, independent)
    p_pause = SEMI2_STATE_P["AI capex pause"][hz]
    p_nand = SEMI2_STATE_P["Memory/NAND downturn"][hz]
    p_boom = SEMI2_STATE_P["AI capex boom"][hz]
    p_base = 1 - p_pause - p_nand - p_boom      # residual
    d = z["demand"]
    c1, c2, c3 = norm.ppf(p_pause), norm.ppf(p_pause + p_nand), norm.ppf(p_pause + p_nand + p_base)
    on = {"AI capex pause": d < c1, "Memory/NAND downturn": (d >= c1) & (d < c2),
          "Base plateau": (d >= c2) & (d < c3), "AI capex boom": d >= c3}
    for s, p in SEMI2_OVERLAYS.items():
        on[s] = z[s] < norm.ppf(p[hz])
    on["Yen +10%"] |= on["Taiwan blockade"]                       # red-geo: force yen on in a blockade
    on["Rapidus slip"] &= ~on["Japan onshoring"]                  # exclusive with onshoring
    return on, dict(pause=p_pause, nand=p_nand, base=p_base, boom=p_boom)


# ------------------------------------------------------------------ engine
def simulate(name, hz, variant="b", sigma=None, overrides=None, seed=SEED):
    """hz 0 = 12m, 1 = 24m. variant: 'a' no reversion, 'b' reversion, 'c' reversion + independent shocks."""
    inp = dict(INPUTS[name])
    if overrides:
        inp.update(overrides)
    rng = np.random.default_rng(seed + hz)
    n = N
    years = 1.0 if hz == 0 else 2.0
    independent = variant == "c"
    slope = 0.0 if variant == "a" else overrides.get("slope", SLOPE) if overrides else SLOPE
    pscale = overrides.get("pscale", 1.0) if overrides else 1.0

    eb_lo, eb_md, eb_hi = inp["ebitda12"] if hz == 0 else inp["ebitda24"]
    base_eb = rng.triangular(eb_lo, eb_md, eb_hi, n)
    r_lo, r_hi = inp["mult_ratio"]
    base_m = inp["fwd_mult"] * rng.triangular(r_lo, 1.0, r_hi, n)
    eb_fac, m_fac, oneoff, extra_debt = np.ones(n), np.ones(n), np.zeros(n), np.zeros(n)
    diag = {}

    def scaled(tbl, keys):
        saved = {s: tbl[s] for s in keys}
        for s in keys:
            tbl[s] = tuple(min(0.95, p * pscale) for p in tbl[s])
        return saved

    if name == "Nexans":
        neg = [s for s in GRID2 if not s.startswith("2 ")]
        if pscale != 1.0:
            saved = {s: GRID2[s]["prob"] for s in neg}
            for s in neg:
                GRID2[s]["prob"] = tuple(min(0.95, p * pscale) for p in GRID2[s]["prob"])
        on = draw_grid_states(rng, hz, n, independent)
        if pscale != 1.0:
            for s in neg:
                GRID2[s]["prob"] = saved[s]
        diag["p_base"] = float(np.mean(~np.any(np.column_stack(list(on.values())), axis=1)))
        for s, d in GRID2.items():
            k = on[s]
            m = int(k.sum())
            eb_fac[k] *= 1 + rng.uniform(*d["ebitda"], m)
            m_fac[k] *= rng.uniform(*d["mult"], m)
            if "oneoff" in d:
                oneoff[k] += rng.uniform(*d["oneoff"], m)
            if "wc" in d:
                extra_debt[k] += rng.uniform(*d["wc"], m) * (1.0 if hz == 0 else 0.5)
    else:
        key = SEMI_KEY[name]
        if pscale != 1.0:
            saved = scaled(SEMI2_STATE_P, ["AI capex pause", "Memory/NAND downturn"])
            saved2 = scaled(SEMI2_OVERLAYS, ["Taiwan blockade", "Gray-zone quarantine"])
        on, pst = draw_semi_states(rng, hz, n, independent)
        if pscale != 1.0:
            SEMI2_STATE_P.update(saved)
            SEMI2_OVERLAYS.update(saved2)
        diag["state_p"] = json.dumps({k: round(v, 3) for k, v in pst.items()})
        pure = on["Base plateau"] & ~np.any(np.column_stack([on[s] for s in SEMI2_OVERLAYS
                                                             if s != "Japan onshoring"]), axis=1)
        diag["p_base"] = float(pure.mean())      # base state with no negative overlay (onshoring allowed)
        for s, d in SEMI2_IMPACT.items():
            k = on[s]
            m = int(k.sum())
            rng_e = d.get(key + "_h", None)
            lo, hi = rng_e[hz] if rng_e else d[key]
            eb_fac[k] *= 1 + rng.uniform(lo, hi, m)
            m_fac[k] *= rng.uniform(*d["mult"], m)

    sig = (sigma if sigma is not None else inp.get("sigma", 0.0)) * np.sqrt(years)
    noise = np.exp(rng.normal(-0.5 * sig ** 2, sig, n))
    ebitda = base_eb * eb_fac * noise
    mult = base_m * m_fac * np.exp(-slope * years * inp["resid"])
    netcash = inp["netcash12"] if hz == 0 else inp["netcash24"]
    equity = ebitda * mult + netcash - oneoff - extra_debt
    value = equity * (1000.0 if inp["ccy"] == "JPY" else 1.0) / inp["shares"]
    ret = value / inp["price"] - 1
    hurdle = (1 + HURDLE) ** years - 1
    return dict(value=value, ret=ret, ebitda=ebitda, mult=mult, on=on, diag=diag, sigma=sig, inp=inp,
                hurdle=hurdle, years=years)


def calibrate_sigma(name, target):
    mode = INPUTS[name]["ebitda12"][1]
    lo, hi = 0.0, 0.8
    for _ in range(30):
        mid = (lo + hi) / 2
        r = simulate(name, 0, "b", sigma=mid)
        p10 = np.quantile(r["ebitda"] / mode - 1, 0.10)
        if p10 > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def stats(r):
    v, ret, h = r["value"], r["ret"], r["hurdle"]
    q = np.quantile(v, [0.05, 0.25, 0.5, 0.75, 0.95])
    return dict(mean_value=v.mean(), median_value=q[2], p05=q[0], p25=q[1], p75=q[3], p95=q[4],
                exp_return=ret.mean(), median_return=np.median(ret),
                p_loss_raw=float(np.mean(ret < 0)), p_below_hurdle=float(np.mean(ret < h)), hurdle=h,
                p_gt15=float(np.mean(ret > 0.15)), p_gt30=float(np.mean(ret > 0.30)),
                ret_p05=np.quantile(ret, 0.05), ret_p95=np.quantile(ret, 0.95))


def main():
    names = list(INPUTS)
    sig_main, sig_alt = {}, {}
    for nm in names:
        s = calibrate_sigma(nm, INPUTS[nm]["p10_target"])
        sig_main[nm] = max(s, SIGMA_FLOOR)
        INPUTS[nm]["sigma"] = sig_main[nm]
        INPUTS[nm]["sigma_at_floor"] = s < SIGMA_FLOOR
        if INPUTS[nm]["p10_alt"] is not None:
            sig_alt[nm] = max(calibrate_sigma(nm, INPUTS[nm]["p10_alt"]), SIGMA_FLOOR)

    summary, tree, tornado, xcheck, entry, rank_rows = [], [], [], [], [], []
    res = {}
    for nm in names:
        for var in ("a", "b", "c"):
            for hz, label in ((0, "12m"), (1, "24m")):
                r = simulate(nm, hz, var)
                res[(nm, var, label)] = r
                s = stats(r)
                s.update(company=nm, variant=var, horizon=label, price=r["inp"]["price"], ccy=r["inp"]["ccy"],
                         fwd_mult_today=r["inp"]["fwd_mult"], sigma_idio=r["sigma"], sigma_label="main", **r["diag"])
                summary.append(s)
                if nm in sig_alt and var == "b":
                    r2 = simulate(nm, hz, var, sigma=sig_alt[nm])
                    s2 = stats(r2)
                    s2.update(company=nm + " (chip-materials sigma)", variant=var, horizon=label, price=r2["inp"]["price"],
                              ccy=r2["inp"]["ccy"], fwd_mult_today=r2["inp"]["fwd_mult"], sigma_idio=r2["sigma"],
                              sigma_label="alt", **r2["diag"])
                    summary.append(s2)
                    res[(nm + " (chip-materials sigma)", var, label)] = r2

        # scenario tree, variant (b)
        for hz, label in ((0, "12m"), (1, "24m")):
            r = res[(nm, "b", label)]
            ret, on = r["ret"], r["on"]
            exclusive = set(SEMI2_STATES) if nm != "Nexans" else set()
            rows = list(on.items())
            if nm == "Nexans":
                rows.append(("1 Base (no shock)", ~np.any(np.column_stack(list(on.values())), axis=1)))
            for sc, k in rows:
                if k.sum() == 0:
                    continue
                p = float(k.mean())
                cm = float(ret[k].mean())
                if sc in exclusive or sc.startswith("1 "):
                    contrib, kind = p * cm, "exclusive state: P x E[ret|state]"
                else:
                    contrib, kind = p * (cm - float(ret[~k].mean())), "layered shock: P x (E[ret|on] - E[ret|off])"
                tree.append(dict(company=nm, horizon=label, scenario=sc, prob=p,
                                 cond_median_value=float(np.median(r["value"][k])), cond_mean_return=cm,
                                 cond_p_loss_raw=float(np.mean(ret[k] < 0)), contribution=contrib, kind=kind))

        # tornado, variant (b), 12m
        base = stats(simulate(nm, 0, "b"))["exp_return"]
        fm = INPUTS[nm]["fwd_mult"]
        e12 = INPUTS[nm]["ebitda12"]
        cases = {
            "forward multiple +/-1 turn": (dict(fwd_mult=fm - 1), dict(fwd_mult=fm + 1)),
            "EBITDA +/-10%": (dict(ebitda12=tuple(x * 0.9 for x in e12)), dict(ebitda12=tuple(x * 1.1 for x in e12))),
            "negative-scenario probabilities x1.5 / x0.5": (dict(pscale=1.5), dict(pscale=0.5)),
            "reversion slope 0 / -0.5 per year (low = none)": (dict(slope=0.0), dict(slope=0.5)),
        }
        for lab, (lo_o, hi_o) in cases.items():
            lo_r = stats(simulate(nm, 0, "b", overrides=lo_o))["exp_return"]
            hi_r = stats(simulate(nm, 0, "b", overrides=hi_o))["exp_return"]
            tornado.append(dict(company=nm, input=lab, exp_return_base=base, exp_return_low=lo_r,
                                exp_return_high=hi_r, swing=abs(hi_r - lo_r)))

        # base-rate cross-check, variant (b), 12m
        r = res[(nm, "b", "12m")]
        inp = INPUTS[nm]
        logret = np.log(r["value"] / inp["price"])
        sim_sd, med = logret.std(), np.median(logret)
        for ref, sd_ref, p05_ref, p95_ref in (("firm", inp["hist_sd12"], inp["hist_p05"], inp["hist_p95"]),
                                              ("group", inp["group_sd12"], inp["group_p05"], inp["group_p95"])):
            sc = med + (logret - med) * (sd_ref / sim_sd)
            rr = np.exp(sc) - 1
            xcheck.append(dict(company=nm, reference=ref, sim_sd_log=sim_sd, hist_sd_log=sd_ref,
                               sim_p05_log=np.quantile(logret, 0.05), hist_p05_log=p05_ref,
                               sim_p95_log=np.quantile(logret, 0.95), hist_p95_log=p95_ref,
                               sim_p_loss_raw=float(np.mean(r["ret"] < 0)), histvol_p_loss_raw=float(np.mean(rr < 0)),
                               histvol_p_below_hurdle=float(np.mean(rr < HURDLE)), histvol_exp_return=float(rr.mean()),
                               histvol_ret_p05=float(np.quantile(rr, 0.05)), histvol_ret_p95=float(np.quantile(rr, 0.95))))

        # entry prices, variant (b): raw P(loss) < 35% and E[ret] > 15%; hurdle version P(ret < hurdle) < 35%
        for hz, label in ((0, "12m"), (1, "24m")):
            r = res[(nm, "b", label)]
            v = r["value"]
            q35, m15 = float(np.quantile(v, 0.35)), float(v.mean() / 1.15)
            q35h = q35 / (1 + r["hurdle"])
            entry.append(dict(company=nm, horizon=label, price=inp["price"], entry_p_loss_raw_lt_35=q35,
                              entry_exp_ret_gt_15=m15, entry_price=min(q35, m15),
                              discount_to_price=min(q35, m15) / inp["price"] - 1,
                              entry_p_below_hurdle_lt_35=q35h, entry_price_hurdle_basis=min(q35h, m15)))

    # rankings per variant, 12m
    df = pd.DataFrame(summary)
    for var in ("a", "b", "c"):
        d = df[(df.variant == var) & (df.horizon == "12m") & (df.sigma_label == "main")][
            ["company", "exp_return", "p_loss_raw", "p_below_hurdle", "ret_p05"]].copy()
        d["variant"] = var
        d["rank_exp_return"] = d["exp_return"].rank(ascending=False).astype(int)
        d["rank_p_loss_raw"] = d["p_loss_raw"].rank().astype(int)
        d["rank_downside_p05"] = d["ret_p05"].rank(ascending=False).astype(int)
        rank_rows.append(d)

    # v1 -> v2 bridge at 12m (expected return, raw P(loss), P(below hurdle))
    v1_sum = pd.read_csv(os.path.join(TAB, "sim_summary.csv"))
    bridge = []
    for nm in names:
        v1.INPUTS[nm]["sigma"] = v1.calibrate_sigma(nm)
    for nm in names:
        row0 = v1_sum[(v1_sum.company == nm) & (v1_sum.horizon == "12m")].iloc[0]
        bridge.append(dict(company=nm, step="0 v1 as reported (discounted value, peer-median exit, f~U(0,0.5), v1 scenarios)",
                           exp_return=row0.exp_return, p_loss_raw=np.nan, p_below_hurdle=row0.p_loss))
        r1 = v1.simulate(nm, 0, overrides=dict(disc=0.0))
        bridge.append(dict(company=nm, step="1 + no discount at 12m (v1 engine, disc = 0)",
                           exp_return=r1["ret"].mean(), p_loss_raw=float(np.mean(r1["ret"] < 0)),
                           p_below_hurdle=float(np.mean(r1["ret"] < HURDLE))))
        fm = INPUTS[nm]["fwd_mult"]
        rl, rh = INPUTS[nm]["mult_ratio"]
        r2 = v1.simulate(nm, 0, overrides=dict(disc=0.0, mult=(fm * rl, fm, fm * rh), resid=INPUTS[nm]["resid"]))
        bridge.append(dict(company=nm, step="2 + multiple re-centred on today's forward, residual reversion (v1 engine)",
                           exp_return=r2["ret"].mean(), p_loss_raw=float(np.mean(r2["ret"] < 0)),
                           p_below_hurdle=float(np.mean(r2["ret"] < HURDLE))))
        r3 = simulate(nm, 0, "b", sigma=v1.INPUTS[nm]["sigma"])
        bridge.append(dict(company=nm, step="3 + red-geo scenario table, signed correlations, slope reversion (v2 engine, v1 sigma)",
                           exp_return=r3["ret"].mean(), p_loss_raw=float(np.mean(r3["ret"] < 0)),
                           p_below_hurdle=float(np.mean(r3["ret"] < HURDLE))))
        r4 = res[(nm, "b", "12m")]
        bridge.append(dict(company=nm, step="4 + sigma recalibrated on v2 (= v2 variant b)",
                           exp_return=r4["ret"].mean(), p_loss_raw=float(np.mean(r4["ret"] < 0)),
                           p_below_hurdle=float(np.mean(r4["ret"] < HURDLE))))
        if nm in sig_alt:
            r5 = res[(nm + " (chip-materials sigma)", "b", "12m")]
            bridge.append(dict(company=nm, step="5 alt: chip-materials sigma", exp_return=r5["ret"].mean(),
                               p_loss_raw=float(np.mean(r5["ret"] < 0)), p_below_hurdle=float(np.mean(r5["ret"] < HURDLE))))

    df.to_csv(os.path.join(TAB, "sim2_summary.csv"), index=False)
    pd.DataFrame(tree).to_csv(os.path.join(TAB, "sim2_scenario_tree.csv"), index=False)
    pd.DataFrame(tornado).sort_values(["company", "swing"], ascending=[True, False]).to_csv(
        os.path.join(TAB, "sim2_tornado.csv"), index=False)
    pd.DataFrame(xcheck).to_csv(os.path.join(TAB, "sim2_crosscheck_baserates.csv"), index=False)
    pd.DataFrame(entry).to_csv(os.path.join(TAB, "sim2_entry_prices.csv"), index=False)
    pd.concat(rank_rows).to_csv(os.path.join(TAB, "sim2_ranking_12m.csv"), index=False)
    pd.DataFrame(bridge).to_csv(os.path.join(TAB, "sim2_v1_vs_v2.csv"), index=False)
    pd.DataFrame([dict(company=nm, fwd_mult_today=INPUTS[nm]["fwd_mult"], sigma_main=sig_main[nm],
                       sigma_at_floor=INPUTS[nm]["sigma_at_floor"], sigma_alt=sig_alt.get(nm, np.nan),
                       resid_log=INPUTS[nm]["resid"]) for nm in names]).to_csv(os.path.join(TAB, "sim2_inputs.csv"), index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print("fwd multiples:", {k: round(v["fwd_mult"], 2) for k, v in INPUTS.items()})
    print("sigma main:", {k: round(v, 3) for k, v in sig_main.items()}, "alt:", {k: round(v, 3) for k, v in sig_alt.items()})
    cols = ["company", "variant", "horizon", "mean_value", "median_value", "p05", "p95", "exp_return", "p_loss_raw",
            "p_below_hurdle", "p_gt15", "p_gt30", "ret_p05", "p_base"]
    print(df[cols].round(3).to_string())
    print(pd.DataFrame(tree).round(3).to_string())
    print(pd.DataFrame(tornado).sort_values(["company", "swing"], ascending=[True, False]).round(3).to_string())
    print(pd.DataFrame(xcheck).round(3).to_string())
    print(pd.DataFrame(entry).round(1).to_string())
    print(pd.concat(rank_rows).round(3).to_string())
    print(pd.DataFrame(bridge).round(3).to_string())


if __name__ == "__main__":
    main()
