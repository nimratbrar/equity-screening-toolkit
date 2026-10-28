"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

RERUN one week later of amkor_final.py. Engine (amkor_simulate.py), seed, states, overlays, residual, variants and entry rule
UNCHANGED. Input changes only (diff against amkor_final.py), which is the discipline this file illustrates:
 R1 New price [Compustat via the refresh run's Valuation inputs sheet]; shares unchanged.
 R2 Balance sheet re-dated to the latest quarter: net debt = debt less cash and short-term investments [company filing: 10-Q].
    Today's forward multiple re-struck = (price x shares + net debt) / FY1 EBITDA.
 R3 B2 roll-forward, same method on the new inputs: full-year capex guide [company filing: 8-K] less 9M PP&E spend [company filing]
    = Q4 capex; H2 CFO kept at the earlier assumption [inference] less Q3 CFO (9M less H1 [company filing]) = Q4 CFO;
    year-end net debt = current net debt + Q4 capex - Q4 CFO; next year's build kept from the earlier convention; half credited
    as construction at cost.
 R4 Q4 guide (revenue and gross margin ranges) [company filing] used as a CHECK on FY1, not as a new input: Q1 + Q2 + Q3 EBITDA
    [company filing] + Q4 (= Q3 EBITDA + (Q4 GP - Q3 GP) at flat opex [inference]) compared with the I/B/E/S FY1 consensus.
    If it brackets consensus, FY1 and FY2/FY3 stay unchanged.
 R5 Arizona overlay re-dated to the latest company timeline [source: earnings call transcript and press coverage]; P, the multiple
    factors and the zero EBITDA effect are unchanged when the ramp falls at or past the 24m horizon [inference]. No new rule is invented.
Outputs: tables/amkr_final_1027.csv (headline + bridge + basis), tables/amkr_final_sensitivity_1027.csv.
Original stated basis (B1 to B5, variants, entry rule, hurdle): see the docstring of amkor_final.py.
"""
import numpy as np, pandas as pd
import amkor_simulate as S

# calibrate idiosyncratic sigma on the original engine (before any change), as amkor_simulate.main() does
S.INP["sigma"] = max(S.calibrate_sigma(S.INP["p10_main"]), S.SIGMA_FLOOR)
OLD = dict(price=S.INP["price"], netcash=S.INP["netcash"], fwd_mult=S.INP["fwd_mult"])           # earlier basis, for the bridge
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
NEW_PRICE = 90.0                                  # [placeholder: R1 latest close, Compustat]
DEBT_Q3, CASH_Q3 = 600.0, 580.0                   # [placeholder: R2 total debt and cash + STI, company filing 10-Q]
CAPEX_FY26, PPE_9M, CFO_9M, CFO_H1 = 400.0, 280.0, 300.0, 190.0   # [placeholder: R3 capex guide, 9M PP&E, 9M and H1 CFO, company filing]
CFO_H2_RANGE = (230.0, 250.0, 270.0)              # [placeholder: earlier H2 CFO assumption lo / mid / hi, inference]
BUILD_NEXT_YEAR = 150.0                           # [placeholder: next year's net debt build, earlier convention]
EB_Q, GP_Q3 = dict(q1=115.0, q2=120.0, q3=130.0), 150.0          # [placeholder: R4 quarterly EBITDA and Q3 gross profit, company filing]
Q4_GUIDE = dict(lo=(800.0, 0.18), mid=(825.0, 0.188), hi=(850.0, 0.195))   # [placeholder: Q4 revenue and gross margin guide, company filing]
OLD_NETCASH_12M, OLD_NETCASH_24M = -100.0, -200.0  # [placeholder: earlier half-credited net cash inputs (amkor_final.py)]
RESID = -0.20                                     # [placeholder: corrected reversion residual, broad multiples model]
RESID_ALT = (-0.30, -0.35)                        # [placeholder: alternative residuals]
SD_24M_REALISED = 0.30                            # [placeholder: realised overlapping 24m log return sd]
# ===== END PLACEHOLDER INPUTS =====
S.INP["price"] = NEW_PRICE                                                                        # R1
S.INP["netcash"] = -(DEBT_Q3 - CASH_Q3)                                                           # R2 latest net debt
S.INP["fwd_mult"] = (S.INP["price"] * S.INP["shares"] - S.INP["netcash"]) / S.INP["ebitda12"][1]
S.INP["fwd_mult_fy25bs"] = (S.INP["price"] * S.INP["shares"] - S.INP["netcash_fy25"]) / S.INP["ebitda12"][1]
P0, SH = S.INP["price"], S.INP["shares"]
# R3 net debt roll-forward [company filing; inference]
CFO_Q3 = CFO_9M - CFO_H1; CAPEX_Q4 = CAPEX_FY26 - PPE_9M
CFO_Q4 = {"lo": CFO_H2_RANGE[0] - CFO_Q3, "mid": CFO_H2_RANGE[1] - CFO_Q3, "hi": CFO_H2_RANGE[2] - CFO_Q3}
ND12 = -S.INP["netcash"] + CAPEX_Q4 - CFO_Q4["mid"]; ND24 = ND12 + BUILD_NEXT_YEAR
ND12_Q3RATE = -S.INP["netcash"] + CAPEX_Q4 - CFO_Q3                                                # sensitivity: Q4 CFO at the Q3 rate
# R4 Q4 guide check on FY1 [company filing; inference]
FY26_GUIDE = {k: sum(EB_Q.values()) + EB_Q["q3"] + (rev * gm - GP_Q3) for k, (rev, gm) in Q4_GUIDE.items()}
print(f"Q4 capex {CAPEX_Q4:.1f}; Q3 CFO {CFO_Q3:.1f}; Q4 CFO {CFO_Q4}; net debt 12m {ND12:.1f} (range {-S.INP['netcash'] + CAPEX_Q4 - CFO_Q4['hi']:.1f} "
      f"to {-S.INP['netcash'] + CAPEX_Q4 - CFO_Q4['lo']:.1f}), 24m {ND24:.1f}; at Q3 CFO rate {ND12_Q3RATE:.1f}")
print("FY26 EBITDA from Q4 guide:", {k: round(v, 1) for k, v in FY26_GUIDE.items()}, "vs I/B/E/S", S.INP["ebitda12"][1])
FY1 = S.INP["ebitda12"][1]
FY2 = tuple(FY1 * k for k in (1.03, 1.09, 1.15)); FY3 = tuple(FY1 * k for k in (1.03 ** 2, 1.09 ** 2, 1.15 ** 2))
OV = {0: dict(ebitda12=FY2, netcash=-0.5 * ND12), 1: dict(ebitda24=FY3, netcash=-0.5 * ND24)}   # R3: half credit
SD_12M = S.INP["hist_sd12"]
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
df = pd.DataFrame(final); df.insert(2, "price", P0); df.insert(3, "shares_m", SH); df.insert(0, "section", "final")

# Earlier -> rerun bridge (no reversion and corrected reversion): (0) earlier run reproduced, (1) + price only (multiple re-struck on the
# earlier balance sheet and net debt path), (2) + latest net debt in today's multiple, (3) + re-rolled net debt path (= final)
def bridge(label, var, price, fwd, nc12, nc24):
    global P0
    keep = P0; P0 = price
    ov = {0: dict(price=price, fwd_mult=fwd, netcash=nc12), 1: dict(price=price, fwd_mult=fwd, netcash=nc24)}
    out = run(label, var, ov=ov); P0 = keep
    for r in out: r.update(section="bridge", price=price, shares_m=SH)
    return out
fm_price_only = (S.INP["price"] * SH - OLD["netcash"]) / FY1
br = []
for var, vl in (("a", "no reversion"), ("b", "corrected reversion")):
    br += bridge(f"{vl}: 0 earlier run reproduced", var, OLD["price"], OLD["fwd_mult"], OLD_NETCASH_12M, OLD_NETCASH_24M)
    br += bridge(f"{vl}: 1 + new price", var, S.INP["price"], fm_price_only, OLD_NETCASH_12M, OLD_NETCASH_24M)
    br += bridge(f"{vl}: 2 + latest net debt in today's multiple", var, S.INP["price"], S.INP["fwd_mult"], OLD_NETCASH_12M, OLD_NETCASH_24M)
    br += bridge(f"{vl}: 3 + net debt path re-rolled = rerun", var, S.INP["price"], S.INP["fwd_mult"], -0.5 * ND12, -0.5 * ND24)
basis = [("price, rerun [placeholder]", P0), ("price, earlier run [placeholder]", OLD["price"]), ("shares m [placeholder]", SH),
         ("net debt latest quarter [placeholder]", -S.INP["netcash"]), ("forward EV/EBITDA today (latest net debt)", S.INP["fwd_mult"]),
         ("forward EV/EBITDA earlier run", OLD["fwd_mult"]), ("Q4 capex = FY guide - 9M PP&E", CAPEX_Q4),
         ("Q3 CFO = 9M CFO - H1 CFO", CFO_Q3), ("Q4 CFO mid (H2 assumption less Q3) [inference]", CFO_Q4["mid"]), ("net debt year end (12m)", ND12),
         ("net debt 24m (+ next year's build)", ND24), ("net cash input 12m / 24m (half credit)", f"{-0.5 * ND12:.1f} / {-0.5 * ND24:.1f}"),
         ("FY EBITDA implied by Q4 guide lo / mid / hi [inference]", f"{FY26_GUIDE['lo']:.1f} / {FY26_GUIDE['mid']:.1f} / {FY26_GUIDE['hi']:.1f}"),
         ("FY1 EBITDA consensus [placeholder]", FY1), ("FY2 mode used at 12m", FY2[1]), ("sigma", S.INP["sigma"]),
         ("one method: (FY2 mode x today's multiple - half net debt 12m) / shares", (FY2[1] * S.INP["fwd_mult"] - 0.5 * ND12) / SH)]
bdf = pd.DataFrame([dict(section="basis", variant=k, value=v) for k, v in basis])
pd.concat([df, pd.DataFrame(br), bdf]).to_csv(S.TABLES / "amkr_final_1027.csv", index=False)

sens = []
for mode in list(AZ_MODES)[1:]:
    sens += run(f"no reversion, Arizona {mode}", "a", az=mode)
sens += run(f"no reversion, net debt full (no CIP credit: {-ND12:,.0f} / {-ND24:,.0f})", "a", ov={0: dict(netcash=-ND12), 1: dict(netcash=-ND24)})
sens += run("no reversion, net debt fully credited (latest net debt held)", "a", ov={0: dict(netcash=S.INP["netcash"]), 1: dict(netcash=S.INP["netcash"])})
sens += run(f"no reversion, Q4 CFO at the Q3 rate (half credit {-0.5 * ND12_Q3RATE:,.0f} / {-0.5 * (ND12_Q3RATE + BUILD_NEXT_YEAR):,.0f})", "a",
            ov={0: dict(netcash=-0.5 * ND12_Q3RATE), 1: dict(netcash=-0.5 * (ND12_Q3RATE + BUILD_NEXT_YEAR))})
sens += run("no reversion, first-estimate EBITDA basis (12m FY1, 24m FY2)", "a", ov={0: dict(ebitda12=S.INP["ebitda12"]), 1: dict(ebitda24=S.INP["ebitda24"])})
sens += run(f"reversion, resid {RESID_ALT[0]} (broad m4 trimmed)", "b", resid=RESID_ALT[0])
sens += run(f"reversion, resid {RESID_ALT[1]} (FY2 EPS growth control)", "b", resid=RESID_ALT[1])
sens += run(f"reversion {RESID} with own-history volatility", "b", own_vol=True)
sens += run("own-history volatility, 24m sd = 12m sd (audit convention)", "a", own_vol=True, sd={0: SD_12M, 1: SD_12M})
sens += run("own-history volatility, 24m sd = realised overlapping 24m (few independent windows)", "a", own_vol=True, sd={0: SD_12M, 1: SD_24M_REALISED})
sens += run("no reversion, phone leg EBITDA -6 to -12% (peer drop-through, red-team challenge)", "a", impact={"Smartphone second leg": dict(eb=(-0.12, -0.06), mult=(0.85, 0.95))})
pd.DataFrame(sens).to_csv(S.TABLES / "amkr_final_sensitivity_1027.csv", index=False)

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
print(df[cols].round(3).to_string()); print(pd.DataFrame(br)[cols].round(3).to_string()); print(pd.DataFrame(sens)[cols].round(3).to_string())
print(bdf.to_string())
