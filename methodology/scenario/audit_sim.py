"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-stats audit of simulate.py (2026-10-20). Imports the original model unchanged and runs variants by patching module globals.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/audit_sim.py   Writes tables/audit_sim_*.csv only. All outputs [inference].
"""
import sys, copy
from pathlib import Path
import numpy as np, pandas as pd
from scipy.stats import norm
HERE = Path(__file__).resolve().parent; sys.path.insert(0, str(HERE))
import simulate as S
OUT = HERE / "tables"
INPUTS0 = copy.deepcopy(S.INPUTS)
orig_grid, orig_semi = S.draw_grid_states, S.draw_semi_states

# ---------- 1. joint scenario distribution: copula as calibrated vs independent ----------
J = []
for hz, lab in ((0, "12m"), (1, "24m")):
    on, rho, pb = orig_grid(np.random.default_rng(7), hz, 400000)
    names = list(S.GRID); M = np.column_stack([on[s] for s in names]); neg = M[:, 1:].sum(1)
    probs = np.array([S.GRID[s]["prob"][hz] for s in names])
    ind_none = float(np.prod(1 - probs))
    J.append(dict(horizon=lab, rho=rho, p_no_shock=pb, p_no_shock_independent=ind_none, p_2plus_negative=float((neg >= 2).mean()),
                  p_2plus_negative_independent=float(1 - sum(np.prod([(probs[1:][i] if i == j else 1) for i in range(4)]) * 0 for j in range(1)) ) if False else np.nan,
                  p_offshore_and_greatsea=float((on["3 Offshore wind stall"] & on["5 Great Sea write-down"]).mean()),
                  p_offshore_and_greatsea_independent=probs[2] * probs[4],
                  p_recession_and_copper=float((on["6 European recession"] & on["4 Copper spike"]).mean()), p_recession_and_copper_independent=probs[5 - 2] * probs[4 - 1] if False else probs[4] * 0 + probs[3] * probs[4] if False else S.GRID["6 European recession"]["prob"][hz] * S.GRID["4 Copper spike"]["prob"][hz],
                  p_supercycle_and_any_negative=float((on["2 Grid super-cycle"] & (neg > 0)).mean())))
    # independent count of negatives
    pn = probs[1:]; dist = np.zeros(5); 
    for mask in range(16):
        bits = [(mask >> i) & 1 for i in range(4)]; dist[sum(bits)] += np.prod([pn[i] if b else 1 - pn[i] for i, b in enumerate(bits)])
    J[-1]["p_2plus_negative_independent"] = float(dist[2:].sum())
pd.DataFrame(J).to_csv(OUT / "audit_sim_joint.csv", index=False)

# ---------- 2. variants ----------
def grid_independent(rng, hz, n):
    names = list(S.GRID); probs = np.array([S.GRID[s]["prob"][hz] for s in names])
    on = rng.uniform(size=(n, len(names))) < probs
    return {s: on[:, i] for i, s in enumerate(names)}, 0.0, float(np.mean(~on.any(axis=1)))
def semi_no_forcing(rng, hz, n):
    names = list(S.SEMI_STATES); p = np.array([S.SEMI_STATES[s]["prob"][hz] for s in names], float); p_norm = p / p.sum()
    state = rng.choice(len(names), size=n, p=p_norm); on = {s: state == i for i, s in enumerate(names)}
    u = rng.uniform(size=(n, len(S.SEMI_OVERLAYS)))
    for j, s in enumerate(S.SEMI_OVERLAYS): on[s] = u[:, j] < S.SEMI_OVERLAYS[s]["prob"][hz]
    return on, p_norm
def semi_marginal_kept(rng, hz, n):
    """Taiwan still forces export controls, but P(controls | no Taiwan) is lowered so the marginal equals the stated 30% / 45%."""
    names = list(S.SEMI_STATES); p = np.array([S.SEMI_STATES[s]["prob"][hz] for s in names], float); p_norm = p / p.sum()
    state = rng.choice(len(names), size=n, p=p_norm); on = {s: state == i for i, s in enumerate(names)}
    u = rng.uniform(size=(n, len(S.SEMI_OVERLAYS))); pt = p_norm[names.index("Taiwan blockade")]
    for j, s in enumerate(S.SEMI_OVERLAYS):
        pr = S.SEMI_OVERLAYS[s]["prob"][hz]
        if s == "Export-control escalation": pr = (pr - pt) / (1 - pt)
        on[s] = u[:, j] < pr
    on["Export-control escalation"] |= on["Taiwan blockade"]
    return on, p_norm

def run(label, grid=orig_grid, semi=orig_semi, fmax=0.5, disc=0.09, inputs_patch=None, fixed_sigma=None):
    S.draw_grid_states, S.draw_semi_states, S.F_MAX, S.DISC = grid, semi, fmax, disc
    S.INPUTS.clear(); S.INPUTS.update(copy.deepcopy(INPUTS0))
    for nm, patch in (inputs_patch or {}).items(): S.INPUTS[nm].update(patch)
    rows = []
    for nm in S.INPUTS:
        S.INPUTS[nm]["sigma"] = fixed_sigma[nm] if fixed_sigma else S.calibrate_sigma(nm)
        for hz, h in ((0, "12m"), (1, "24m")):
            r = S.simulate(nm, hz); st = S.stats(r); v = r["value_0"]; raw = r["value_h"] / r["inp"]["price"] - 1
            rows.append(dict(variant=label, company=nm, horizon=h, sigma12=S.INPUTS[nm]["sigma"], exp_return=st["exp_return"], p_value_below_price=st["p_loss"],
                             ret_p05=st["ret_p05"], raw_exp_return_undiscounted=float(raw.mean()), p_raw_loss_undiscounted=float((raw < 0).mean()),
                             entry_price=min(np.quantile(v, 0.35), v.mean() / 1.15), price=r["inp"]["price"],
                             p_export_controls=float(r["on"]["Export-control escalation"].mean()) if "Export-control escalation" in r["on"] else np.nan))
    S.draw_grid_states, S.draw_semi_states, S.F_MAX, S.DISC = orig_grid, orig_semi, 0.5, 0.09
    S.INPUTS.clear(); S.INPUTS.update(copy.deepcopy(INPUTS0))
    return rows

# time-consistent horizon EBITDA at 12m: a forward multiple at the 12m horizon should be applied to forward EBITDA at the horizon.
# March-FYE names: FY2 (the model's own 24m inputs) is the nearest proxy. Calendar-FYE names: NTM at the horizon is roughly
# 0.2 x FY+1 + 0.8 x FY+2, with FY+1 interpolated geometrically toward the company's medium-term target [inference].
# Here every case simply uses its 24m inputs as a placeholder for that construction.
ntm = {nm: dict(ebitda12=INPUTS0[nm]["ebitda24"]) for nm in INPUTS0}
R = []
R += run("V0 reported")
R += run("V1 independent shocks (Nexans copula off, Taiwan no longer forces controls)", grid=grid_independent, semi=semi_no_forcing)
R += run("V2 no multiple mean reversion (f = 0)", fmax=0.0)
R += run("V3 independent shocks and no mean reversion", grid=grid_independent, semi=semi_no_forcing, fmax=0.0)
R += run("V4 export-control marginal kept at stated 30/45%", semi=semi_marginal_kept)
R += run("V5 Japan Material idio sigma calibrated to the alternative peer-group p10", inputs_patch={"Japan Material": dict(p10_target=-0.30)})   # [placeholder]
R += run("V6 time-consistent 12m: NTM-at-horizon EBITDA (FY2) with the forward multiple", inputs_patch=ntm)
sig0 = {r["company"]: r["sigma12"] for r in R if r["variant"] == "V0 reported" and r["horizon"] == "12m"}
R += run("V1b independent shocks, sigma held at reported values", grid=grid_independent, semi=semi_no_forcing, fixed_sigma=sig0)
# today's forward EV/EBITDA on the model's own inputs: (price x shares - net cash) / FY1 mode
fwd = {nm: ((i["price"] * i["shares"] / (1000.0 if i["ccy"] == "JPY" else 1.0)) - i["netcash12"]) / i["ebitda12"][1] for nm, i in INPUTS0.items()}
rer = {nm: dict(mult=tuple(x * fwd[nm] / INPUTS0[nm]["mult"][1] for x in INPUTS0[nm]["mult"])) for nm in INPUTS0}
R += run("V7 exit-multiple triangle re-centred on today's forward multiple, reversion kept (re-rating counted once)", inputs_patch=rer)
R += run("V8 exit-multiple triangle re-centred on today's forward multiple, no reversion", inputs_patch=rer, fmax=0.0)
pd.DataFrame([dict(company=nm, fwd_ev_ebitda_today=fwd[nm], model_base_exit_multiple=INPUTS0[nm]["mult"][1], built_in_rerating=INPUTS0[nm]["mult"][1] / fwd[nm] - 1) for nm in INPUTS0]).to_csv(OUT / "audit_sim_multiples.csv", index=False)
print(pd.read_csv(OUT / "audit_sim_multiples.csv").round(3).to_string())
T = pd.DataFrame(R); T.to_csv(OUT / "audit_sim_variants.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(pd.DataFrame(J).round(3).T.to_string())
print(T.drop(columns=["price"]).round(3).to_string())
