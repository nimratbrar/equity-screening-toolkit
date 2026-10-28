"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

reconcile-amkor: ONE audited Amkor simulation on one stated basis. Supersedes the headline tables in
amkr_sim_summary.csv (quant first estimate) and amkr_audit_sim.csv (red-team audit runs).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_final.py   (seed 20261020, 20,000 paths, about 1 min)
Outputs: tables/amkr_final.csv (headline), tables/amkr_final_sensitivity.csv. Every simulated number is [inference].

Engine: amkor_simulate.py unchanged (simulate_v2 conventions). Stated basis, applied to every row of amkr_final.csv:
 B1 FY2-struck: 12m value on FY2 EBITDA (FY1 consensus [I/B/E/S] x 1.03 / 1.09 / 1.15 triangular), 24m on FY3
    (FY1 x 1.03^2 / 1.09^2 / 1.15^2) [inference, audit T1]; today's forward multiple on FY1 EBITDA and the latest net cash.
 B2 Net debt rolled forward from the company's capex guidance less spend to date, against expected operating cash flow
    [company filing; inference]; half of the build credited as construction in progress at cost -> net cash inputs
    NETCASH_12M and NETCASH_24M below [inference, audit T2 'half'].
 B3 Corrected reversion residual RESID: the case company minus the peer-median residual in the broad multiples model (the
    residual that matches the slope estimate), instead of the raw peer cross-section residual [WRDS data; inference].
 B4 Two-sided Arizona overlay: on time (P 40% / 45%) multiple x U(1.00, 1.10); slip (P 60% / 55%, the complement on the same
    copula draw) multiple x U(0.90, 1.00); no EBITDA effect either way (no Arizona revenue before 2028). Expected multiple
    effect 0.40 x 5% - 0.60 x 5% = -1.0% (12m), -0.5% (24m): near neutral, as the audit asked [inference].
 B5 Probabilities normalised to 100%: four exclusive demand states, base is the residual: 12m squeeze 15 + phone 20 + boom 20
    + base 45 = 100; 24m 20 + 27 + 17 + 36 = 100. Taiwan halt (2.5% / 6%, a haircut of prediction-market prices quoted as
    given with their date [source: Polymarket]) is an overlay correlated -0.3 with demand, not a fifth exclusive state [inference].
Variants: (a) no reversion; (b) corrected reversion (B3); (o) own-history volatility: (a) with log value dispersion rescaled
around the median to the company's realised 12m sd [WRDS data], and that sd x sqrt(2) at 24m (square-root-of-time) [inference].
Realised overlapping 24m sd can rest on very few independent windows; sensitivity rows run 24m at the 12m sd and at the
realised 24m sd.
Entry price = min(35th percentile of value, mean value / 1.15): the price at which raw P(loss) < 35% and E[ret] > 15%.
Hurdle 9% a year: 9.0% at 12m, 1.09^2 - 1 = 18.8% at 24m.
"""
import numpy as np, pandas as pd
import amkor_simulate as S

# calibrate idiosyncratic sigma on the original engine (before any change), as amkor_simulate.main() does
S.INP["sigma"] = max(S.calibrate_sigma(S.INP["p10_main"]), S.SIGMA_FLOOR)
P0, SH = S.INP["price"], S.INP["shares"]
FY1 = S.INP["ebitda12"][1]
FY2 = tuple(FY1 * k for k in (1.03, 1.09, 1.15)); FY3 = tuple(FY1 * k for k in (1.03 ** 2, 1.09 ** 2, 1.15 ** 2))
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
NETCASH_12M, NETCASH_24M = -100.0, -200.0   # [placeholder: half-credited net debt roll-forward from capex guidance and CFO, company filing; inference]
RESID = -0.20                               # [placeholder: corrected reversion residual, broad multiples model]
RESID_ALT = (-0.30, -0.35)                  # [placeholder: alternative residuals (trimmed broad model; FY2 EPS growth control)]
SD_12M = S.INP["hist_sd12"]                 # [placeholder via amkor_simulate.INP: own realised 12m log return sd]
SD_24M_REALISED = 0.30                      # [placeholder: realised overlapping 24m log return sd]
# ===== END PLACEHOLDER INPUTS =====
OV = {0: dict(ebitda12=FY2, netcash=NETCASH_12M), 1: dict(ebitda24=FY3, netcash=NETCASH_24M)}
SD_OWN = {0: SD_12M, 1: SD_12M * np.sqrt(2)}

# B5 check: exclusive demand states sum to 100% with base as the residual
BASE = {hz: 1 - sum(v[hz] for v in S.STATE_P.values()) for hz in (0, 1)}
assert abs(BASE[0] - 0.45) < 1e-9 and abs(BASE[1] - 0.36) < 1e-9, BASE   # 15+20+20+45 = 100; 20+27+17+36 = 100

# B4: two-sided Arizona overlay. The slip branch is the complement of the on-time Bernoulli on the same copula draw.
_orig_draw = S.draw_states
def _draw_two_sided(*a, **k):
    on, pst = _orig_draw(*a, **k); on["Arizona slip"] = ~on["Arizona on time"]; return on, pst
AZ_MODES = {
    "two-sided (stated basis)": dict(on=dict(eb=(0.0, 0.0), mult=(1.00, 1.10)), slip=dict(eb=(0.0, 0.0), mult=(0.90, 1.00))),
    "removed (audit AZ0)": dict(on=dict(eb=(0.0, 0.0), mult=(1.0, 1.0)), slip=dict(eb=(0.0, 0.0), mult=(1.0, 1.0))),
    "slip only (audit AZ bear)": dict(on=dict(eb=(0.0, 0.0), mult=(1.0, 1.0)), slip=dict(eb=(0.0, 0.0), mult=(0.90, 1.00))),
    "one-sided upside (first estimate)": dict(on=dict(eb=(0.0, 0.02), mult=(1.10, 1.20)), slip=dict(eb=(0.0, 0.0), mult=(1.0, 1.0))),
}
def set_az(mode):
    S.draw_states = _draw_two_sided
    S.IMPACT["Arizona on time"] = AZ_MODES[mode]["on"]; S.IMPACT["Arizona slip"] = AZ_MODES[mode]["slip"]

def own_vol_values(v, sd_ref):
    lv = np.log(np.clip(v, 0.5, None)); med = np.median(lv)
    return np.exp(med + (lv - med) * (sd_ref / lv.std()))

def summarise(label, hz, v, hurdle, extra=None):
    ret = v / P0 - 1; q = np.quantile(v, [0.05, 0.35, 0.5, 0.95]); m115 = v.mean() / 1.15; entry = min(q[1], m115)
    row = dict(variant=label, horizon="12m" if hz == 0 else "24m", exp_return=ret.mean(), p_loss_raw=float((ret < 0).mean()), hurdle=hurdle,
               p_below_hurdle=float((ret < hurdle).mean()), value_p05=q[0], value_p50=q[2], value_p95=q[3], ret_p05=q[0] / P0 - 1, ret_p50=q[2] / P0 - 1,
               ret_p95=q[3] / P0 - 1, mean_value=v.mean(), entry_q35=q[1], entry_mean_over_1p15=m115, entry_price=entry, entry_vs_price=entry / P0 - 1,
               log_sd=float(np.log(np.clip(v, 0.5, None) / P0).std()))
    row.update(extra or {}); return row

def run(label, var, az="two-sided (stated basis)", ov=None, own_vol=False, resid=RESID, sd=None, impact=None):
    set_az(az); rows = []; saved = dict(S.IMPACT); S.IMPACT.update(impact or {})
    for hz in (0, 1):
        o = dict(OV[hz]); o.update((ov or {}).get(hz, {}))
        if var == "b": o["resid"] = resid
        r = S.simulate(hz, var, overrides=o); v = r["value"]
        if own_vol: v = own_vol_values(v, (sd or SD_OWN)[hz])
        rows.append(summarise(label, hz, v, r["hurdle"], dict(p_pure_base=r["p_base"], netcash_input=r["inp"]["netcash"])))
    S.IMPACT.clear(); S.IMPACT.update(saved); return rows

final = []
final += run("no reversion", "a")
final += run(f"corrected reversion (resid {RESID}, slope -{S.SLOPE})", "b")
final += run(f"own-history volatility (no reversion, sd {SD_OWN[0]:.3f} / {SD_OWN[1]:.3f})", "a", own_vol=True)
df = pd.DataFrame(final); df.insert(2, "price", P0); df.insert(3, "shares_m", SH)
df.to_csv(S.TABLES / "amkr_final.csv", index=False)

sens = []
for mode in list(AZ_MODES)[1:]:
    sens += run(f"no reversion, Arizona {mode}", "a", az=mode)
sens += run(f"no reversion, net debt full (no CIP credit: {2 * NETCASH_12M:,.0f} / {2 * NETCASH_24M:,.0f})", "a", ov={0: dict(netcash=2 * NETCASH_12M), 1: dict(netcash=2 * NETCASH_24M)})
sens += run("no reversion, net debt fully credited (latest net cash held)", "a", ov={0: dict(netcash=S.INP["netcash"]), 1: dict(netcash=S.INP["netcash"])})
sens += run("no reversion, first-estimate EBITDA basis (12m FY1, 24m FY2)", "a", ov={0: dict(ebitda12=S.INP["ebitda12"]), 1: dict(ebitda24=S.INP["ebitda24"])})
sens += run(f"reversion, resid {RESID_ALT[0]} (broad m4 trimmed)", "b", resid=RESID_ALT[0])
sens += run(f"reversion, resid {RESID_ALT[1]} (FY2 EPS growth control)", "b", resid=RESID_ALT[1])
sens += run(f"reversion {RESID} with own-history volatility", "b", own_vol=True)
sens += run("own-history volatility, 24m sd = 12m sd (audit convention)", "a", own_vol=True, sd={0: SD_12M, 1: SD_12M})
sens += run("own-history volatility, 24m sd = realised overlapping 24m (few independent windows)", "a", own_vol=True, sd={0: SD_12M, 1: SD_24M_REALISED})
sens += run("no reversion, phone leg EBITDA -6 to -12% (peer drop-through, red-team challenge)", "a", impact={"Smartphone second leg": dict(eb=(-0.12, -0.06), mult=(0.85, 0.95))})
pd.DataFrame(sens).to_csv(S.TABLES / "amkr_final_sensitivity.csv", index=False)

# realised Amkor 24m log return sd, for the own-vol 24m check [WRDS data]
try:
    from amkor_common import tri_osat, AMKR
    t = tri_osat()[AMKR].dropna(); t = t[t.index >= "2016-10-01"]
    for d, lab in ((252, "12m"), (504, "24m")):
        lr = np.log(t / t.shift(d)).dropna(); print(f"realised Amkor {lab} log sd, windows ending {lr.index.min():%Y-%m} to {lr.index.max():%Y-%m}: {lr.std():.3f}")
except Exception as e:
    print("realised sd check skipped:", e)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
cols = ["variant", "horizon", "exp_return", "p_loss_raw", "p_below_hurdle", "value_p05", "value_p50", "value_p95", "entry_q35", "entry_mean_over_1p15", "entry_price", "log_sd"]
print("sigma", round(S.INP["sigma"], 4), "fwd mult", round(S.INP["fwd_mult"], 3), "shares", SH, "price", P0)
print(df[cols].round(3).to_string()); print(pd.DataFrame(sens)[cols].round(3).to_string())
