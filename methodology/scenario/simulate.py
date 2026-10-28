"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Scenario-mixture Monte Carlo of value per share for Nexans, Organo, Japan Material, Shin-Etsu.

Run:  ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/simulate.py
Seeded (SEED below), 20,000 paths per company, horizons 12 and 24 months.
All inputs are listed in INPUTS with their source tag; everything derived here is [inference].
Outputs: methodology/scenario/tables/sim_*.csv

Method (short):
  value_h = (EBITDA_h * multiple_h + net_cash_h - one_offs) / shares, discounted to today at DISC
  EBITDA_h = base_h (triangular on guidance / consensus) * prod(scenario impact factors) * exp(idio noise)
  multiple_h = triangular(low, base, high) * prod(scenario multiple factors) * exp(-f * residual), f ~ U(0, F_MAX)
  Scenario states: Nexans shocks 2 to 6 are Bernoullis joined by a Gaussian copula calibrated so that
  P(no shock) equals the macro-grid base probability. Semis demand states are mutually exclusive
  (probabilities normalised to sum to one), policy overlays are independent Bernoullis.
  Idiosyncratic EBITDA noise sigma is solved so that the simulated p10 of EBITDA_12m / base - 1 equals
  the empirical one-in-ten EBITDA fall for the group (midpoint of peer and broad samples).
"""
import json
import os
import numpy as np
import pandas as pd
from scipy.stats import norm

SEED = 20261020
N = 20000
DISC = 0.09
F_MAX = 0.5          # mean-reversion fraction of the multiple residual, f ~ U(0, F_MAX)
SIGMA_FLOOR = 0.05   # minimum idiosyncratic EBITDA sigma (12m) even when scenario shocks alone reach the p10 target
HERE = os.path.dirname(os.path.abspath(__file__))
TAB = os.path.join(HERE, "tables")
os.makedirs(TAB, exist_ok=True)

# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
# Original source tags, for orientation: CF = case file (company filings + WRDS deep-dive), PX = latest close in
# data/scenario/daily_prices.csv [WRDS data], XL = output/peers_*/analysis.xlsx "Valuation inputs" [WRDS data],
# RG = this folder's regression tables. Every number below is made up and round on purpose.
# Units: EUR names in m and EUR per share; JPY names in JPY bn, shares in m, price in JPY per share.
INPUTS = {
    "Nexans": dict(
        ccy="EUR", price=100.0,                                # [placeholder: PX close]
        shares=50.0,                                           # [placeholder: CF diluted shares, m]
        # 12m = FY1 guidance range or I/B/E/S consensus mode; 24m = FY2 / company medium-term target +/- a band
        ebitda12=(450.0, 500.0, 550.0), ebitda24=(550.0, 600.0, 650.0),   # [placeholder: guidance / I/B/E/S]
        mult=(10.0, 12.0, 14.0),                               # [placeholder: low / base / high exit EV/EBITDA from peer multiples]
        netcash12=-1000.0, netcash24=-1000.0,                  # [placeholder: net debt incl. pensions, negative = net debt]
        resid=-0.20,                                           # [placeholder: log residual vs fitted multiple, from reg_multiples.py]
        p10_target=-0.20,                                      # [placeholder: one-in-ten EBITDA fall, from reg_baserates.py]
        hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,         # [placeholder: own 12m log return sd and quantiles]
        group="cable_grid", group_sd12=0.35, group_p05=-0.40, group_p95=0.55,   # [placeholder: peer-group 12m log returns]
    ),
    "Organo": dict(
        ccy="JPY", price=2000.0, shares=100.0,                 # [placeholder: PX; CF shares m]
        ebitda12=(14.0, 15.0, 16.0), ebitda24=(15.5, 17.0, 18.5),   # [placeholder: guidance / I/B/E/S, JPY bn]
        mult=(11.0, 13.0, 15.0),                               # [placeholder: peer multiples]
        netcash12=0.0, netcash24=0.0,                          # [placeholder: net cash, JPY bn]
        resid=+0.20,                                           # [placeholder: multiple residual]
        p10_target=-0.20,                                      # [placeholder: base rate]
        hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
        group="fab_water_facility", group_sd12=0.35, group_p05=-0.40, group_p95=0.55,
    ),
    "Japan Material": dict(
        ccy="JPY", price=1500.0, shares=100.0,                 # [placeholder]
        ebitda12=(11.0, 12.0, 13.0), ebitda24=(12.0, 13.5, 15.0),   # [placeholder]
        mult=(11.0, 13.0, 15.0),                               # [placeholder]
        netcash12=10.0, netcash24=10.0,                        # [placeholder]
        resid=0.0,                                             # [placeholder]
        p10_target=-0.20,
        hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
        group="fab_water_facility", group_sd12=0.35, group_p05=-0.40, group_p95=0.55,
    ),
    "Shin-Etsu": dict(
        ccy="JPY", price=5000.0, shares=2000.0,                # [placeholder]
        ebitda12=(850.0, 900.0, 950.0), ebitda24=(900.0, 1000.0, 1100.0),   # [placeholder]
        mult=(10.0, 12.0, 14.0),                               # [placeholder]
        netcash12=1000.0, netcash24=1000.0,                    # [placeholder]
        resid=0.0,                                             # [placeholder]
        p10_target=-0.30,
        hist_sd12=0.30, hist_p05=-0.35, hist_p95=0.45,
        group="chip_materials_and_chem", group_sd12=0.35, group_p05=-0.40, group_p95=0.55,
    ),
}
# ===== END PLACEHOLDER INPUTS =====

# Scenario definitions. prob = (P12, P24). ebitda = (low, high) % impact on EBITDA, uniform.
# mult = (low, high) multiplicative factor on the exit multiple. Scenario probabilities and impacts are analyst judgments
# [inference, illustrative], kept to show the structure.
# Nexans (SG table): shocks layered on base; copula-joined.
GRID = {
    "2 Grid super-cycle":        dict(prob=(0.15, 0.20), ebitda=(+0.06, +0.12), mult=(1.00, 1.15), sign=+1),
    "3 Offshore wind stall":     dict(prob=(0.20, 0.25), ebitda=(-0.09, -0.04), mult=(0.92, 1.00), sign=-1),
    "4 Copper spike":            dict(prob=(0.20, 0.25), ebitda=(-0.04, -0.02), mult=(0.95, 1.00), sign=-1,
                                      wc=(150.0, 250.0)),      # working capital tied up, EUR m, half unwinds by 24m
    "5 Great Sea write-down":    dict(prob=(0.25, 0.35), ebitda=(-0.05, -0.02), mult=(0.95, 1.00), sign=-1,
                                      oneoff=(50.0, 150.0)),   # one-off charge, EUR m
    "6 European recession":      dict(prob=(0.15, 0.25), ebitda=(-0.14, -0.08), mult=(0.80, 0.92), sign=-1),
}
GRID_BASE_P = (0.45, 0.35)

# Semis (SS table). Demand states exclusive; overlays independent. Impacts per company (E column of SS).
SEMI_STATES = {
    "Base plateau":        dict(prob=(0.45, 0.30), mult=(1.00, 1.00),
                                Organo=(0, 0), JM=(0, 0), SE=(0, 0)),
    "AI capex boom":       dict(prob=(0.25, 0.20), mult=(1.00, 1.15),
                                Organo=(+0.08, +0.18), JM=(+0.08, +0.15), SE=(+0.06, +0.12)),
    "Memory/NAND downturn": dict(prob=(0.20, 0.40), mult=(0.80, 0.95),
                                Organo=(-0.12, -0.05), JM=(-0.35, -0.20), SE=(-0.09, -0.05)),
    "Taiwan blockade":     dict(prob=(0.04, 0.10), mult=(0.70, 0.90),
                                Organo=(-0.50, -0.30), JM=(-0.20, -0.10), SE=(-0.25, -0.15)),
}
SEMI_OVERLAYS = {
    "Export-control escalation": dict(prob=(0.30, 0.45), mult=(0.95, 1.00),
                                      Organo=(-0.04, -0.01), JM=(-0.02, 0.0), SE=(-0.06, -0.03)),
    "Japan onshoring":           dict(prob=(0.20, 0.30), mult=(1.00, 1.08),
                                      Organo=(+0.05, +0.12), JM=(+0.05, +0.10), SE=(+0.01, +0.03)),
}
SEMI_KEY = {"Organo": "Organo", "Japan Material": "JM", "Shin-Etsu": "SE"}


def tri(rng, lo, mode, hi, n):
    return rng.triangular(lo, mode, hi, n)


def uni(rng, lo, hi, n):
    return rng.uniform(lo, hi, n)


# ---------------------------------------------------------------- scenario state draws
def copula_corr(k, rho_neg, signs):
    """Correlation matrix: negative shocks cluster (+rho), the positive shock is anti-correlated (-rho)."""
    C = np.eye(k)
    for i in range(k):
        for j in range(k):
            if i != j:
                C[i, j] = rho_neg if signs[i] == signs[j] else -rho_neg
    return C


def draw_grid_states(rng, hz, n):
    names = list(GRID)
    probs = np.array([GRID[s]["prob"][hz] for s in names])
    signs = [GRID[s]["sign"] for s in names]
    thresholds = norm.ppf(probs)
    target = GRID_BASE_P[hz]

    def p_none(rho, m=200000, seed=1):
        C = copula_corr(len(names), rho, signs)
        L = np.linalg.cholesky(C)
        z = np.random.default_rng(seed).standard_normal((m, len(names))) @ L.T
        return float(np.mean(np.all(z > thresholds, axis=1)))

    lo, hi = 0.0, 0.95
    for _ in range(25):                       # bisection on rho so that P(no shock) = stated base
        mid = (lo + hi) / 2
        if p_none(mid) < target:
            lo = mid
        else:
            hi = mid
    rho = (lo + hi) / 2
    C = copula_corr(len(names), rho, signs)
    L = np.linalg.cholesky(C)
    z = rng.standard_normal((n, len(names))) @ L.T
    on = z < thresholds                        # shock fires when latent below its quantile
    return {s: on[:, i] for i, s in enumerate(names)}, rho, float(np.mean(~on.any(axis=1)))


def draw_semi_states(rng, hz, n):
    names = list(SEMI_STATES)
    p = np.array([SEMI_STATES[s]["prob"][hz] for s in names], float)
    p_norm = p / p.sum()
    state = rng.choice(len(names), size=n, p=p_norm)
    on = {s: state == i for i, s in enumerate(names)}
    u = rng.uniform(size=(n, len(SEMI_OVERLAYS)))
    for j, s in enumerate(SEMI_OVERLAYS):
        on[s] = u[:, j] < SEMI_OVERLAYS[s]["prob"][hz]
    on["Export-control escalation"] |= on["Taiwan blockade"]   # a blockade implies controls [inference]
    return on, p_norm


# ---------------------------------------------------------------- one company, one horizon
def simulate(name, hz, sigma=None, overrides=None, seed=SEED):
    """hz: 0 = 12 months, 1 = 24 months. Returns dict with arrays and diagnostics."""
    inp = dict(INPUTS[name])
    if overrides:
        inp.update(overrides)
    rng = np.random.default_rng(seed + hz)
    n = N
    years = 1.0 if hz == 0 else 2.0
    eb_lo, eb_md, eb_hi = inp["ebitda12"] if hz == 0 else inp["ebitda24"]
    m_lo, m_md, m_hi = inp["mult"]
    netcash = inp["netcash12"] if hz == 0 else inp["netcash24"]
    disc = overrides.get("disc", DISC) if overrides else DISC
    fmax = overrides.get("fmax", F_MAX) if overrides else F_MAX
    pscale = overrides.get("pscale", 1.0) if overrides else 1.0   # scales negative-shock probabilities

    base_eb = tri(rng, eb_lo, eb_md, eb_hi, n)
    base_m = tri(rng, m_lo, m_md, m_hi, n)
    eb_fac = np.ones(n)
    m_fac = np.ones(n)
    oneoff = np.zeros(n)
    extra_debt = np.zeros(n)
    diag = {}

    if name == "Nexans":
        if pscale != 1.0:
            saved = {s: GRID[s]["prob"] for s in GRID}
            for s in GRID:
                if GRID[s]["sign"] < 0:
                    GRID[s]["prob"] = tuple(min(0.95, p * pscale) for p in GRID[s]["prob"])
        on, rho, p_base = draw_grid_states(rng, hz, n)
        if pscale != 1.0:
            for s in GRID:
                GRID[s]["prob"] = saved[s]
        diag.update(rho=rho, p_base=p_base)
        for s, d in GRID.items():
            k = on[s]
            eb_fac[k] *= 1 + uni(rng, *d["ebitda"], k.sum())
            m_fac[k] *= uni(rng, *d["mult"], k.sum())
            if "oneoff" in d:
                oneoff[k] += uni(rng, *d["oneoff"], k.sum())
            if "wc" in d:
                extra_debt[k] += uni(rng, *d["wc"], k.sum()) * (1.0 if hz == 0 else 0.5)
    else:
        key = SEMI_KEY[name]
        if pscale != 1.0:
            # scale the downturn and Taiwan states, keep the ratio of the others
            saved = {s: SEMI_STATES[s]["prob"] for s in SEMI_STATES}
            for s in ("Memory/NAND downturn", "Taiwan blockade"):
                SEMI_STATES[s]["prob"] = tuple(p * pscale for p in SEMI_STATES[s]["prob"])
        on, p_norm = draw_semi_states(rng, hz, n)
        if pscale != 1.0:
            for s in SEMI_STATES:
                SEMI_STATES[s]["prob"] = saved[s]
        diag.update(p_norm=dict(zip(SEMI_STATES, np.round(p_norm, 4))))
        for s, d in {**SEMI_STATES, **SEMI_OVERLAYS}.items():
            k = on[s]
            lo, hi = d[key]
            eb_fac[k] *= 1 + uni(rng, lo, hi, k.sum())
            m_fac[k] *= uni(rng, *d["mult"], k.sum())

    # idiosyncratic EBITDA noise: sigma solved at 12m (see calibrate_sigma), scaled by sqrt(years) at 24m
    sig = (sigma if sigma is not None else inp.get("sigma", 0.0)) * np.sqrt(years)
    noise = np.exp(rng.normal(-0.5 * sig ** 2, sig, n))
    ebitda = base_eb * eb_fac * noise

    # exit multiple with partial mean reversion of the residual
    f = uni(rng, 0.0, fmax, n)
    mult = base_m * m_fac * np.exp(-f * inp["resid"])

    ev = ebitda * mult
    equity = ev + netcash - oneoff - extra_debt
    scale = 1000.0 if inp["ccy"] == "JPY" else 1.0          # JPY bn / m shares -> JPY per share
    value_h = equity * scale / inp["shares"]
    value_0 = value_h / (1 + disc) ** years
    ret = value_0 / inp["price"] - 1
    return dict(value_h=value_h, value_0=value_0, ret=ret, ebitda=ebitda, base_eb=base_eb, mult=mult,
                on=on, diag=diag, sigma=sig, inp=inp)


def calibrate_sigma(name):
    """Solve sigma so that p10 of EBITDA_12m / mode(base) - 1 equals the group one-in-ten EBITDA fall."""
    target = INPUTS[name]["p10_target"]
    mode = INPUTS[name]["ebitda12"][1]
    lo, hi = 0.0, 0.8
    for _ in range(30):
        mid = (lo + hi) / 2
        r = simulate(name, 0, sigma=mid)
        p10 = np.quantile(r["ebitda"] / mode - 1, 0.10)
        if p10 > target:
            lo = mid
        else:
            hi = mid
    return max((lo + hi) / 2, SIGMA_FLOOR)


def stats(r):
    v, ret = r["value_0"], r["ret"]
    q = np.quantile(v, [0.05, 0.25, 0.5, 0.75, 0.95])
    return dict(mean_value=v.mean(), median_value=q[2], p05=q[0], p25=q[1], p75=q[3], p95=q[4],
                exp_return=ret.mean(), median_return=np.median(ret),
                p_loss=float(np.mean(ret < 0)), p_gt15=float(np.mean(ret > 0.15)), p_gt30=float(np.mean(ret > 0.30)),
                ret_p05=np.quantile(ret, 0.05), ret_p95=np.quantile(ret, 0.95))


def main():
    names = list(INPUTS)
    sigmas = {}
    for nm in names:
        sigmas[nm] = calibrate_sigma(nm)
        INPUTS[nm]["sigma"] = sigmas[nm]

    summary, tree, tornado, xcheck, entry = [], [], [], [], []
    results = {}
    for nm in names:
        for hz, label in ((0, "12m"), (1, "24m")):
            r = simulate(nm, hz)
            results[(nm, label)] = r
            s = stats(r)
            s.update(company=nm, horizon=label, price=r["inp"]["price"], ccy=r["inp"]["ccy"],
                     sigma_idio=r["sigma"], **{k: (v if not isinstance(v, dict) else json.dumps(v)) for k, v in r["diag"].items()})
            summary.append(s)

            # scenario tree: exclusive states contribute P x E[ret|state]; layered shocks report the marginal effect
            ret, on = r["ret"], r["on"]
            exclusive = set(SEMI_STATES) if nm != "Nexans" else set()
            for sc, k in on.items():
                if k.sum() == 0:
                    continue
                p = float(k.mean())
                cond_ret = float(ret[k].mean())
                if sc in exclusive:
                    contrib = p * cond_ret
                    kind = "exclusive state: P x E[ret|state]"
                else:
                    contrib = p * (cond_ret - float(ret[~k].mean()))
                    kind = "layered shock: P x (E[ret|on] - E[ret|off])"
                tree.append(dict(company=nm, horizon=label, scenario=sc, prob=p,
                                 cond_median_value=float(np.median(r["value_0"][k])), cond_mean_return=cond_ret,
                                 cond_p_loss=float(np.mean(ret[k] < 0)), contribution=contrib, kind=kind))
            if nm == "Nexans":
                none = ~np.any(np.column_stack(list(on.values())), axis=1)
                tree.append(dict(company=nm, horizon=label, scenario="1 Base (no shock)", prob=float(none.mean()),
                                 cond_median_value=float(np.median(r["value_0"][none])), cond_mean_return=float(ret[none].mean()),
                                 cond_p_loss=float(np.mean(ret[none] < 0)), contribution=float(none.mean() * ret[none].mean()),
                                 kind="residual state: P x E[ret|state]"))

        # tornado at 12m: expected return under low / high setting of each input
        base = stats(simulate(nm, 0))["exp_return"]
        inp = INPUTS[nm]
        m = inp["mult"]
        e12 = inp["ebitda12"]
        cases = {
            "exit multiple +/-1 turn": (dict(mult=tuple(x - 1 for x in m)), dict(mult=tuple(x + 1 for x in m))),
            "EBITDA +/-10%": (dict(ebitda12=tuple(x * 0.9 for x in e12)), dict(ebitda12=tuple(x * 1.1 for x in e12))),
            "negative-scenario probabilities x0.5 / x1.5": (dict(pscale=0.5), dict(pscale=1.5)),
            "discount rate 11% / 7%": (dict(disc=0.11), dict(disc=0.07)),
            "multiple residual reversion: low=none (f=0) / high=full (f~U(0,1))": (dict(fmax=0.0), dict(fmax=1.0)),
        }
        for lab, (lo_o, hi_o) in cases.items():
            lo_r = stats(simulate(nm, 0, overrides=lo_o))["exp_return"]
            hi_r = stats(simulate(nm, 0, overrides=hi_o))["exp_return"]
            tornado.append(dict(company=nm, input=lab, exp_return_base=base, exp_return_low=lo_r, exp_return_high=hi_r,
                                swing=abs(hi_r - lo_r)))

        # cross-check vs empirical 12m log returns; historical-volatility version rescales the simulated log return
        r = results[(nm, "12m")]
        logret = np.log(r["value_h"] / inp["price"])               # undiscounted horizon value vs price
        sim_sd = logret.std()
        med = np.median(logret)
        for ref, sd_ref, p05_ref, p95_ref in (("firm", inp["hist_sd12"], inp["hist_p05"], inp["hist_p95"]),
                                              ("group", inp["group_sd12"], inp["group_p05"], inp["group_p95"])):
            scaled = med + (logret - med) * (sd_ref / sim_sd)
            disc_ret = np.exp(scaled) / (1 + DISC) - 1
            xcheck.append(dict(company=nm, reference=ref, sim_sd_log=sim_sd, hist_sd_log=sd_ref,
                               sim_p05_log=np.quantile(logret, 0.05), hist_p05_log=p05_ref,
                               sim_p95_log=np.quantile(logret, 0.95), hist_p95_log=p95_ref,
                               sim_p_loss=float(np.mean(r["ret"] < 0)), histvol_p_loss=float(np.mean(disc_ret < 0)),
                               histvol_exp_return=float(disc_ret.mean()), histvol_ret_p05=float(np.quantile(disc_ret, 0.05)),
                               histvol_ret_p95=float(np.quantile(disc_ret, 0.95))))

        # entry price: P(loss) < 35%  <=>  price < 35th percentile of discounted value; E[ret] > 15%  <=>  price < mean / 1.15
        for hz, label in ((0, "12m"), (1, "24m")):
            v = results[(nm, label)]["value_0"]
            q35 = float(np.quantile(v, 0.35))
            m15 = float(v.mean() / 1.15)
            entry.append(dict(company=nm, horizon=label, price=inp["price"], entry_p_loss_lt_35=q35,
                              entry_exp_ret_gt_15=m15, entry_price=min(q35, m15),
                              discount_to_price=min(q35, m15) / inp["price"] - 1))

    pd.DataFrame(summary).to_csv(os.path.join(TAB, "sim_summary.csv"), index=False)
    pd.DataFrame(tree).to_csv(os.path.join(TAB, "sim_scenario_tree.csv"), index=False)
    pd.DataFrame(tornado).sort_values(["company", "swing"], ascending=[True, False]).to_csv(
        os.path.join(TAB, "sim_tornado.csv"), index=False)
    pd.DataFrame(xcheck).to_csv(os.path.join(TAB, "sim_crosscheck_baserates.csv"), index=False)
    pd.DataFrame(entry).to_csv(os.path.join(TAB, "sim_entry_prices.csv"), index=False)

    rank = pd.DataFrame([s for s in summary if s["horizon"] == "12m"])[
        ["company", "exp_return", "p_loss", "ret_p05"]]
    rank["rank_exp_return"] = rank["exp_return"].rank(ascending=False).astype(int)
    rank["rank_p_loss"] = rank["p_loss"].rank().astype(int)
    rank["rank_downside_p05"] = rank["ret_p05"].rank(ascending=False).astype(int)
    rank.to_csv(os.path.join(TAB, "sim_ranking_12m.csv"), index=False)

    pd.set_option("display.width", 250)
    pd.set_option("display.max_columns", 40)
    print("sigma_idio (12m):", {k: round(v, 3) for k, v in sigmas.items()})
    print(pd.DataFrame(summary).round(3).to_string())
    print(pd.DataFrame(tree).round(3).to_string())
    print(pd.DataFrame(tornado).sort_values(["company", "swing"], ascending=[True, False]).round(3).to_string())
    print(pd.DataFrame(xcheck).round(3).to_string())
    print(pd.DataFrame(entry).round(1).to_string())
    print(rank.round(3).to_string())


if __name__ == "__main__":
    main()
