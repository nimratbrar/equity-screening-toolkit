"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-team audit 2: Monte Carlo variants on amkor_simulate.py (same engine, seed, 20,000 paths).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/audit_amkor_sim.py  -> tables/amkr_audit_sim.csv. All outputs [inference].
Changes tested one at a time, then combined:
 T1 time-consistent: 12m value on FY2 EBITDA (FY1 x 1.03/1.09/1.15), 24m on FY3 (FY1 x 1.09^2 mode), today's multiple.
 T2 net debt rolled forward: the capex guide less first-half spend, against expected second-half CFO [company filing; inference],
    so net debt (incl. customer advances, which are debt-like) builds at 12m and 24m with no credit for construction in
    progress; 'half' credits half of it (construction valued at cost).
 AZ0 Arizona overlay removed (on time is the plan and in the price: expected multiple effect zero, the neutral case);
 AZ  two-sided bear version: on time no effect, slip with P 60% / 55% cuts the multiple 0-10%.
 R27 reversion on the company-specific residual inside the broad model (company minus peer median), R50 on the
    FY2-EPS-growth-controlled peer residual.
"""
import numpy as np, pandas as pd
import amkor_simulate as S
S.INP["sigma"] = max(S.calibrate_sigma(S.INP["p10_main"]), S.SIGMA_FLOOR)   # recalibrated, as amkor_simulate.main() does
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
ND_FULL = (-200.0, -400.0)          # [placeholder: net cash input 12m / 24m with no construction credit, company filing; inference]
ND_HALF = (-100.0, -200.0)          # [placeholder: same with half credit]
R27, R50 = -0.20, -0.35             # [placeholder: broad-model company-vs-peer residual; FY2-EPS-growth-controlled residual]
EPS_GROWTH_FY2 = 0.055              # [placeholder: I/B/E/S FY2 EPS growth, used as a growth-leg check]
AZ_EBITDA = (100.0, 140.0, 220.0)   # [placeholder: Arizona Phase 1 EBITDA cases, inference from company targets]
AZ_NET_COST = (1300.0, 1500.0)      # [placeholder: Phase 1 capital net of tax credit and grants, company filing; inference]
# ===== END PLACEHOLDER INPUTS =====
FY1 = S.INP["ebitda12"][1]; FY2 = tuple(FY1 * k for k in (1.03, 1.09, 1.15)); FY3 = tuple(FY1 * k for k in (1.03 ** 2, 1.09 ** 2, 1.15 ** 2))
P0 = S.INP["price"]
def own_vol(r, sd_ref=S.INP["hist_sd12"]):
    lr = np.log(np.clip(r["value"], 0.5, None) / P0); med = np.median(lr); sc = med + (lr - med) * (sd_ref / lr.std()); rr = np.exp(sc) - 1
    return float(rr.mean()), float((rr < 0).mean())
def run(label, var, ov12=None, ov24=None, az=False):
    saved = (dict(S.IMPACT), dict(S.OVERLAYS), dict(S.CORR))
    if az == "off":
        S.OVERLAYS["Arizona on time"] = (0.0, 0.0)
    elif az:
        S.IMPACT["Arizona on time"] = dict(eb=(0.0, 0.0), mult=(0.90, 1.00)); S.OVERLAYS["Arizona on time"] = (0.60, 0.55)
        S.CORR[("Arizona on time", "Tariff escalation (232 phase 2, SE Asia)")] = -0.2; S.CORR[("demand", "Arizona on time")] = -0.2
    out = []
    for hz, ov, lab in ((0, ov12, "12m"), (1, ov24, "24m")):
        r = S.simulate(hz, var, overrides=ov); st = S.stats(r); ev, pl = own_vol(r)
        out.append(dict(variant=label, horizon=lab, exp_return=st["exp_return"], p_loss_raw=st["p_loss_raw"], p_below_hurdle=st["p_below_hurdle"], p05=st["p05"], p95=st["p95"],
                        sim_sd_log=float(np.log(np.clip(r["value"], 0.5, None) / P0).std()), ownvol_exp_return=ev, ownvol_p_loss=pl))
    S.IMPACT.clear(); S.IMPACT.update(saved[0]); S.OVERLAYS.clear(); S.OVERLAYS.update(saved[1]); S.CORR.clear(); S.CORR.update(saved[2])
    return out
rows = []
rows += run("(a) reported: no reversion", "a"); rows += run("(b) reported: reversion resid_b", "b"); rows += run("(d) reported: reversion resid_d", "d")
rows += run("T1 time-consistent EBITDA, no reversion", "a", dict(ebitda12=FY2), dict(ebitda24=FY3))
rows += run("T1+T2 full net debt build, no reversion", "a", dict(ebitda12=FY2, netcash=ND_FULL[0]), dict(ebitda24=FY3, netcash=ND_FULL[1]))
rows += run("T1+T2 half credit, no reversion", "a", dict(ebitda12=FY2, netcash=ND_HALF[0]), dict(ebitda24=FY3, netcash=ND_HALF[1]))
rows += run("AZ0 Arizona overlay neutral (removed), (a) otherwise", "a", az="off")
rows += run("AZ two-sided Arizona slip, (a) otherwise", "a", az=True)
rows += run("(b) engine, residual R27 (company vs peers in broad model)", "b", dict(resid=R27), dict(resid=R27))
rows += run("(b) engine, residual R50 (FY2 EPS growth control)", "b", dict(resid=R50), dict(resid=R50))
rows += run("AUDITED central: T1+T2 half + AZ0, no reversion", "a", dict(ebitda12=FY2, netcash=ND_HALF[0]), dict(ebitda24=FY3, netcash=ND_HALF[1]), az="off")
rows += run("AUDITED with reversion R27: T1+T2 half + AZ0", "b", dict(ebitda12=FY2, netcash=ND_HALF[0], resid=R27), dict(ebitda24=FY3, netcash=ND_HALF[1], resid=R27), az="off")
rows += run("AUDITED low: T1+T2 full + AZ slip, no reversion", "a", dict(ebitda12=FY2, netcash=ND_FULL[0]), dict(ebitda24=FY3, netcash=ND_FULL[1]), az=True)
rows += run("AUDITED high: T1 only + AZ0 + reversion R50", "b", dict(ebitda12=FY2, resid=R50), dict(ebitda24=FY3, resid=R50), az="off")
df = pd.DataFrame(rows); df.to_csv(S.TABLES / "amkr_audit_sim.csv", index=False)
pd.set_option("display.width", 250); print(df.round(3).to_string())
# valuation identities [inference]: per USD 1bn of net debt not offset by credited construction
print("per USD 1bn net debt: USD/share", round(1000 / S.INP["shares"], 2), "=", round(1000 / S.INP["shares"] / P0 * 100, 1), "% of price")
m = S.INP["fwd_mult"]
for lab, eb, nc in [("growth leg 12m as reported", FY2[1], S.INP["netcash"]), ("growth leg 12m, half-credit net debt", FY2[1], ND_HALF[0]), ("growth leg 12m, full net debt", FY2[1], ND_FULL[0]),
                    ("growth leg on consensus FY2 EPS growth only, half-credit net debt", FY1 * (1 + EPS_GROWTH_FY2), ND_HALF[0])]:
    v = (eb * m + nc) / S.INP["shares"]; print(f"{lab}: {v:.2f} ({v / P0 - 1:+.1%})")
# Arizona Phase 1 at today's multiple, net of its capital (tax credit and grants deducted) [company filing; inference]
for eb in AZ_EBITDA:
    for cost in AZ_NET_COST:
        print(f"Arizona P1 EBITDA {eb}, net cost after ITC/CHIPS {cost:.0f}: value/share {(eb * m - cost) / S.INP['shares']:+.2f}")
