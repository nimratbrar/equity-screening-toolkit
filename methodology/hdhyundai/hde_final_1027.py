"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

RERUN of hde_final.py one week later. Engine (hde_simulate.py), states, overlays, sigma, residual, FY+1 basis (audit; the
quarterly scorecard did not trigger the pre-committed re-base) and entry rule UNCHANGED. Inputs:
 H1 New price [placeholder; original from the WRDS refresh run].
 H2 Same-date balance sheet at the new quarter end. Shares unchanged [company filing: dividend notice]. The change in the
    company's own net cash between quarters [company filing: results deck] is applied to the lease-inclusive Compustat basis,
    so new net cash = Compustat basis + company change [inference]; the company figure itself is a sensitivity row.
 H3 Current-year EBITDA on the audit's own bridge (audit_hde.py ebitda(), constants shared through hde_common): H1 actual +
    Q3 actual OP [company filing] + quarterly D&A + Q4 modelled as the audit's quarter at the new spot rate instead of the old.
 H4 Net cash at horizon, F3 re-anchored: the old path accrues (12m net cash - today's net cash - forward gain) / 5 quarters a
    quarter [inference]; new 12m = new net cash + 4 quarters of accrual + forward MTM at the new spot; 24m = 12m + (old 24m - old 12m).
 Forward multiple on own current-year EBITDA (F2 convention) = EV(new price x shares - net cash) / current-year EBITDA.
Output: tables/hde_final_1027.csv (sections final, bridge, sensitivity, basis).
"""
import numpy as np, pandas as pd
import hde_common as C
from hde_common import HDE_IN, TABLES, FX, H1, FWD_USD_M, FWD_RATE
OLD = dict(price=HDE_IN["price"], ev=HDE_IN["ev"], fm_cons=HDE_IN["fwd_mult"])        # 20 Oct basis, for the bridge
# H1, H2: re-date price and balance sheet BEFORE the engine reads HDE_IN at import
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
NC_COMPANY_SEP26 = 706.6                 # company net cash, ex leases, at the new quarter end [company filing: Q3 deck]
NEW_PRICE = 380000.0                     # [placeholder: close at the rerun date, Compustat g_secd]
NC_OLD = {0: 900.0, 1: 1200.0}           # [placeholder: the previous run's 12m / 24m net cash path, as in hde_final.NC_F]
NC_CONS_OLD = {0: 950.0, 1: 1300.0}      # [placeholder: the previous run's consensus-path net cash, as in hde_final.NC_CONS]
FWD_GAIN_OLD = 50.0                      # [placeholder: forward settlement gain inside the previous 12m path]
FY27_AT_WEAK_WON, FY27_AT_STRONG_WON = 1150.0, 850.0   # [placeholder: audit-model FY+1 EBITDA central at KRW/USD 1,450 and 1,250]
# ===== END PLACEHOLDER INPUTS =====
NC_SEP26 = -HDE_IN["net_debt_jun26"] - (HDE_IN["netcash_company_jun26"] - NC_COMPANY_SEP26)   # Compustat basis + company change [inference]
HDE_IN.update(price=NEW_PRICE, price_date="rerun date")
HDE_IN["mcap"] = HDE_IN["price"] * HDE_IN["shares_jun26"] / 1000.0
HDE_IN["ev"] = HDE_IN["mcap"] - NC_SEP26
HDE_IN["fwd_mult"] = HDE_IN["ev"] / HDE_IN["ebitda_fy1_cons"]
import hde_simulate as S   # noqa: E402

# H3: audit EBITDA bridge (constants and function as in audit_hde.py) [company filing inputs; inference]
F1H, FQ3, SPOT_OLD, SPOT_NEW = FX["avg_1h26"], FX["avg_q3"], FX["spot"], FX["spot_new"]   # [placeholders in hde_common.FX]
S1H, OP1H, DA1H, KR1H = H1["sales"], H1["op"], H1["da"], H1["korea_sales"]
EX1H_USD = (S1H - KR1H) / F1H * 1000; M1H = (OP1H + DA1H) / S1H
def a_ebitda(kr, ex_usd, fx, m_ref, c):
    r_ref = kr + ex_usd * F1H / 1000; c_ref = (1 - m_ref) * r_ref
    r = kr + ex_usd * fx / 1000; cost = c_ref * ((1 - c) + c * fx / F1H); return r, r - cost
quarter = lambda fx: a_ebitda(245.0, EX1H_USD * 1.09 / 2, fx, M1H + 0.003, 0.40)   # audit quarter assumptions [inference, illustrative]
Q3_MODEL_EB, Q4_OLD_EB, Q4_NEW_EB = quarter(FQ3)[1], quarter(SPOT_OLD)[1], quarter(SPOT_NEW)[1]
Q3_ACT_OP, DA_Q = 284.5, DA1H / 2          # Q3 actual OP [company filing: Q3 results disclosure]; D&A = half of half-year D&A
FY26_AUDIT = OP1H + DA1H + Q3_MODEL_EB + Q4_OLD_EB
FY26_NEW = OP1H + DA1H + (Q3_ACT_OP + DA_Q) + Q4_NEW_EB
# H4: net cash path
ACC_Q = (NC_OLD[0] - (-HDE_IN["net_debt_jun26"]) - FWD_GAIN_OLD) / 5; FWD_MTM = FWD_USD_M * (FWD_RATE - SPOT_NEW) / 1000
NC12 = NC_SEP26 + 4 * ACC_Q + FWD_MTM; NC24 = NC12 + (NC_OLD[1] - NC_OLD[0])
print(f"FY26e: audit {FY26_AUDIT:.1f} (Q3 model EBITDA {Q3_MODEL_EB:.1f} = OP {Q3_MODEL_EB - DA_Q:.1f}; Q4 at old spot {Q4_OLD_EB:.1f}) -> "
      f"{FY26_NEW:.1f} (Q3 actual {Q3_ACT_OP + DA_Q:.1f}; Q4 at new spot {Q4_NEW_EB:.1f}); net cash new quarter {NC_SEP26:.1f}, 12m {NC12:.1f}, 24m {NC24:.1f}")

E = pd.read_csv(TABLES / "hde_audit_ebitda.csv").set_index("item")
FY27 = (float(E.loc["ebitda27", "p05"]), float(E.loc["ebitda27", "central"]), float(E.loc["ebitda27", "p95"]))
FY26_FILE = float(E.loc["ebitda26", "central"]); assert abs(FY26_FILE - FY26_AUDIT) < 0.5, (FY26_FILE, FY26_AUDIT)
FY26 = FY26_NEW
FM_OWN, FM_CONS = HDE_IN["ev"] / FY26, S.FM
NC_F = {0: NC12, 1: NC24}
BASE = dict(fy2=FY27, fm=FM_OWN, nc=NC_F, p_tariff=(0.45, 0.60))

def mult_mean(ov):
    """E[exit multiple] / fm under variant a, to test the built-in de-rating drift of the state and overlay multiple factors."""
    o = dict(ov); r = S.simulate(0, "a", ov=o); impl = (r["value"] * S.SH - o["nc"][0]) / r["eb"]
    return float(impl.mean() / o["fm"])

def rows(label, section, ov, variant="a", own=None):
    out = []
    for hz in (0, 1):
        r = S.simulate(hz, variant, ov=ov); v = r["value"]
        if own: v = S.own_vol(v, own[hz])
        x = S.summ(label, hz, v, r["hurdle"]); x["section"] = section; out.append(x)
    return out

res = []
res += rows("audited basis, no reversion [HEADLINE]", "final", BASE)
res += rows(f"audited basis, reversion (resid {S.RESID:+.3f}, slope -0.25)", "final", BASE, "b")
res += rows("audited basis, own-history volatility (sd per hde_simulate.SD_OWN)", "final", BASE, own=S.SD_OWN)
# 20 Oct -> 27 Oct bridge, variants a and b
def brow(label, var, p0, fm, nc):
    keep = S.P0; S.P0 = p0 / 1000.0
    out = rows(label, "bridge", dict(BASE, fm=fm, nc=nc), var); S.P0 = keep; return out
sh = HDE_IN["shares_jun26"]
for var, vl in (("a", "no reversion"), ("b", "reversion")):
    res += brow(f"{vl}: 0 previous run reproduced", var, OLD["price"], OLD["ev"] / FY26_AUDIT, NC_OLD)
    res += brow(f"{vl}: 1 + new price (old balance sheet)", var, HDE_IN["price"], (HDE_IN["price"] * sh / 1000 + HDE_IN["net_debt_jun26"]) / FY26_AUDIT, NC_OLD)
    res += brow(f"{vl}: 2 + new-quarter net cash in EV and path", var, HDE_IN["price"], HDE_IN["ev"] / FY26_AUDIT, NC_F)
    res += brow(f"{vl}: 3 + Q3 actual and Q4 at new spot in current-year EBITDA (= rerun)", var, HDE_IN["price"], FM_OWN, NC_F)
mm = mult_mean(BASE)
sens = [
    (f"consensus path at the consensus multiple {FM_CONS:.2f}x (consistent consensus basis; consensus net cash less the new-quarter shortfall)",
     dict(BASE, fy2=(S.FY2_CONS * 0.92, S.FY2_CONS, S.FY2_CONS * 1.05), fm=FM_CONS, nc={0: NC_CONS_OLD[0] - (NC_OLD[0] - NC12), 1: NC_CONS_OLD[1] - (NC_OLD[0] - NC12)})),
    (f"audited FY+1 at {FM_CONS:.2f}x (consensus still to be cut: mixed basis, the quant's convention)", dict(BASE, fm=FM_CONS)),
    (f"quant first-estimate engine defaults at rerun inputs ({FM_CONS:.2f}x, net cash not re-anchored, tariff 20/40)", dict()),
    ("audited basis, tariff step at quant P 20 / 40", dict(BASE, p_tariff=(0.20, 0.40))),
    ("audited basis, won at 1,450 (FY+1 rescaled, current year unchanged)", dict(BASE, fy2=tuple(x * FY27_AT_WEAK_WON / FY27[1] for x in FY27))),
    ("audited basis, won at 1,250 (FY+1 rescaled)", dict(BASE, fy2=tuple(x * FY27_AT_STRONG_WON / FY27[1] for x in FY27))),
    (f"audited basis, state and overlay multiple factors rescaled to mean 1 (built-in drift {mm - 1:+.1%})", dict(BASE, fm=FM_OWN / mm)),
    ("audited basis, tariff statutory (P 100% at 24m, no relief)", dict(BASE, p_tariff=(0.45, 0.999), p_tariff_up=0)),
    ("audited basis, one-sided overlays (no relief, no weak won, no Gulf upside)", dict(BASE, p_tariff_up=0, p_won_up=0, p_gulf_up=0)),
    (f"audited basis, multiple on the mean of own and consensus bases ({(FM_OWN + FM_CONS) / 2:.2f}x)", dict(BASE, fm=(FM_OWN + FM_CONS) / 2)),
    ("audited basis, new-quarter net cash at the company figure (ex leases) in EV and path",
     dict(BASE, fm=(HDE_IN["mcap"] - NC_COMPANY_SEP26) / FY26, nc={0: NC12 + NC_COMPANY_SEP26 - NC_SEP26, 1: NC24 + NC_COMPANY_SEP26 - NC_SEP26})),
    ("audited basis, current-year EBITDA at the simple swap audit + (Q3 actual - Q3 model) (Q4 FX not updated)",
     dict(BASE, fm=HDE_IN["ev"] / (FY26_AUDIT + Q3_ACT_OP + DA_Q - Q3_MODEL_EB))),
]
for lab, ov in sens: res += rows(lab, "sensitivity", ov)
res += rows("audited basis, own-history vol at last-1y daily vol", "sensitivity", BASE, own={0: S.SD_LAST1Y, 1: S.SD_LAST1Y * np.sqrt(2)})
df = pd.DataFrame(res)
df.insert(0, "section", df.pop("section"))
df["entry_rule"] = "min(value q35 [raw P(loss)<35%], mean/1.15 [E>15%])"
basis = pd.DataFrame([dict(section="basis", variant=k, exp_return=v) for k, v in [
    ("price KRW, rerun [placeholder]", S.P0 * 1000), ("price KRW, previous run [placeholder]", OLD["price"]),
    ("shares m [company filing]", S.SH), ("net cash new quarter, lease-incl. [inference on placeholder]", NC_SEP26),
    ("EV KRW bn, new quarter", HDE_IN["ev"]), ("FY2026e EBITDA audit (previous run)", FY26_AUDIT), ("Q3 EBITDA audit model / actual (OP + D&A)", f"{Q3_MODEL_EB:.1f} / {Q3_ACT_OP + DA_Q:.1f}"),
    ("Q4 EBITDA audit model at old / new spot", f"{Q4_OLD_EB:.1f} / {Q4_NEW_EB:.1f}"), ("FY2026e EBITDA rerun", FY26),
    ("one method: (FY+1 central x own multiple + net cash 12m) / shares, KRW", (FY27[1] * FM_OWN + NC12) / S.SH * 1000), ("FY2026 EBITDA I/B/E/S FY1 [placeholder]", HDE_IN["ebitda_fy1_cons"]), ("forward multiple, own FY2026e (headline)", FM_OWN),
    ("forward multiple, consensus FY1 (quant)", FM_CONS), ("FY2027e EBITDA p5 / central / p95", f"{FY27[0]:.0f} / {FY27[1]:.0f} / {FY27[2]:.0f}"),
    ("FY2027 consensus path", S.FY2_CONS), ("net cash 12m / 24m (previous run in NC_OLD)", f"{NC12:,.1f} / {NC24:,.1f}"), ("idiosyncratic sigma", S.SIGMA), ("E[multiple factor] built in, 12m", mm)]])
pd.concat([df, basis]).to_csv(TABLES / "hde_final_1027.csv", index=False)

pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 95)
cols = ["section", "variant", "horizon", "exp_return", "median_return", "p_loss_raw", "p_below_hurdle", "ret_p05", "ret_p95", "value_p05_krw", "value_p50_krw", "value_p95_krw", "entry_price_krw", "entry_vs_price"]
print(df[cols].round(3).to_string()); print(basis.to_string())
