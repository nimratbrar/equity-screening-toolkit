"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-hde FINAL: ONE audited HD Hyundai Electric simulation on one stated basis. Supersedes hde_sim_summary.csv
for headline use. No separate reconciliation round.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_final.py   (about 1 min; run audit_hde.py first)
Output: tables/hde_final.csv (section 'final' = headline rows; 'sensitivity' = everything else). Every simulated number is [inference].

Engine: hde_simulate.py unchanged (states, overlays, copula, sigma calibration, own-vol rescaling, entry rule). Stated basis:
 F1 FY+1 EBITDA from audit_hde.py (currency-split model at spot): triangular(p5, central, p95) of the audit simulation,
    replacing the quant's first bottom-up range. Reason: the company's forwards are trading-purpose, so hedge gains sit in
    finance income and EBITDA takes spot in full; the first estimate halved the FX margin hit [company filing; inference].
 F2 Same-basis multiple: today's EV [WRDS data, latest-quarter balance sheet] / audited current-year EBITDA (own FY1), as in
    atkins_final.py. When consensus FY1 sits well above the audited current year (for example because its FX vintage is
    stale), applying the consensus multiple to an at-spot EBITDA mixes bases; it is kept as the 'consensus is still to be cut'
    sensitivity.
 F3 Net cash at horizon: today's net cash + FCF share of audit EBITDA - dividends (payout) + forward settlement gain [inference].
 F4 Tariff overlay: if a published proclamation sets the end date of a tariff cap inside the 24m horizon [source: the
    proclamation or a law-firm summary of it], the step is the default: P(step) is raised at both horizons, multiple only at 12m.
 Everything else as hde_simulate.py: states summing to 100%, two-sided won and Gulf overlays, reversion residual (broad m4
 minus grid median), own-vol rescaling, entry = min(q35, mean / 1.15), hurdle 9.0% / 18.8%.
"""
import numpy as np, pandas as pd
import hde_simulate as S
from hde_common import HDE_IN, TABLES

E = pd.read_csv(TABLES / "hde_audit_ebitda.csv").set_index("item")
FY27 = (float(E.loc["ebitda27", "p05"]), float(E.loc["ebitda27", "central"]), float(E.loc["ebitda27", "p95"]))
FY26 = float(E.loc["ebitda26", "central"])
FM_OWN, FM_CONS = HDE_IN["ev"] / FY26, S.FM
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
NC_F = {0: 900.0, 1: 1200.0}            # [placeholder: net cash at 12m / 24m on the audited EBITDA path, KRW bn]
NC_CONS = {0: 950.0, 1: 1300.0}         # [placeholder: net cash at 12m / 24m on the consensus EBITDA path, KRW bn]
FY27_AT_WEAK_WON, FY27_AT_STRONG_WON = 1150.0, 850.0   # [placeholder: audit-model FY+1 EBITDA central at KRW/USD 1,450 and 1,250]
SD_LAST1Y = S.SD_LAST1Y                 # [placeholder, set in hde_simulate.py]
# ===== END PLACEHOLDER INPUTS =====
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
mm = mult_mean(BASE)
sens = [
    ("consensus path at the consensus multiple (consistent consensus basis)", dict(BASE, fy2=(S.FY2_CONS * 0.92, S.FY2_CONS, S.FY2_CONS * 1.05), fm=FM_CONS, nc=NC_CONS)),
    ("audited FY+1 at the consensus multiple (consensus still to be cut: mixed basis, the quant's convention)", dict(BASE, fm=FM_CONS)),
    ("quant first estimate reproduced (engine defaults, tariff 20/40)", dict()),
    ("audited basis, tariff step at quant P 20 / 40", dict(BASE, p_tariff=(0.20, 0.40))),
    ("audited basis, won at 1,450 (FY+1 rescaled, current year unchanged)", dict(BASE, fy2=tuple(x * FY27_AT_WEAK_WON / FY27[1] for x in FY27))),
    ("audited basis, won at 1,250 (FY+1 rescaled)", dict(BASE, fy2=tuple(x * FY27_AT_STRONG_WON / FY27[1] for x in FY27))),
    (f"audited basis, state and overlay multiple factors rescaled to mean 1 (built-in drift {mm - 1:+.1%})", dict(BASE, fm=FM_OWN / mm)),
    ("audited basis, tariff statutory (P 100% at 24m, no relief)", dict(BASE, p_tariff=(0.45, 0.999), p_tariff_up=0)),
    ("audited basis, one-sided overlays (no relief, no weak won, no Gulf upside)", dict(BASE, p_tariff_up=0, p_won_up=0, p_gulf_up=0)),
    ("audited basis, multiple on the mean of own and consensus bases", dict(BASE, fm=(FM_OWN + FM_CONS) / 2)),
]
for lab, ov in sens: res += rows(lab, "sensitivity", ov)
res += rows("audited basis, own-history vol at last-1y daily vol", "sensitivity", BASE, own={0: SD_LAST1Y, 1: SD_LAST1Y * np.sqrt(2)})
df = pd.DataFrame(res)
df.insert(0, "section", df.pop("section"))
df["entry_rule"] = "min(value q35 [raw P(loss)<35%], mean/1.15 [E>15%])"
basis = pd.DataFrame([dict(section="basis", variant=k, exp_return=v) for k, v in [
    ("price KRW [placeholder]", S.P0 * 1000), ("shares m [company filing]", S.SH), ("EV KRW bn, latest-quarter net debt [placeholder]", HDE_IN["ev"]),
    ("FY2026e EBITDA audited", FY26), ("FY2026 EBITDA I/B/E/S FY1 [placeholder]", HDE_IN["ebitda_fy1_cons"]), ("forward multiple, own FY2026e (headline)", FM_OWN),
    ("forward multiple, consensus FY1 (quant)", FM_CONS), ("FY2027e EBITDA p5 / central / p95", f"{FY27[0]:.0f} / {FY27[1]:.0f} / {FY27[2]:.0f}"),
    ("FY2027 consensus path", S.FY2_CONS), ("net cash 12m / 24m", f"{NC_F[0]:,.0f} / {NC_F[1]:,.0f}"), ("idiosyncratic sigma", S.SIGMA), ("E[multiple factor] built in, 12m", mm)]])
pd.concat([df, basis]).to_csv(TABLES / "hde_final.csv", index=False)

pd.set_option("display.width", 260); pd.set_option("display.max_columns", 30); pd.set_option("display.max_colwidth", 95)
cols = ["section", "variant", "horizon", "exp_return", "median_return", "p_loss_raw", "p_below_hurdle", "ret_p05", "ret_p95", "value_p05_krw", "value_p50_krw", "value_p95_krw", "entry_price_krw", "entry_vs_price"]
print(df[cols].round(3).to_string()); print(basis.to_string())
