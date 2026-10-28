"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Cross-case ranking after a rerun: one combined table for all cases, previous run vs rerun. Reads only the model output
tables written by the *_1027.py models (run those first), plus the placeholder block below.
Run:  ~/.venvs/equity-screening-toolkit/bin/python methodology/cross_case/ranking_1027.py
Output: methodology/cross_case/ranking_1027.csv (git-ignored). Simulated numbers are [inference]; prices [WRDS data in the
original; placeholders here]; scorecard results [company filing] come from the quarterly scorecards (q3_2026_arith.py).
Variant (a) = no reversion, (b) = reversion. Entry price = min(value q35, mean / 1.15), house rule, 12m.
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd

R = Path(__file__).resolve().parents[1]          # methodology/
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(R / "scenario"))
import simulate_v2_1027 as V  # noqa: E402  (inputs only; main() is not run)

rows = []

def add(company, ccy, p0, p1, m0, m1, e1, value, value_note, score, then_rank, now_rank, rule):
    """m0 / m1: dict variant -> horizon -> (E[ret], raw P(loss), P(below hurdle)); e1: variant -> 12m entry price."""
    r = dict(company=company, ccy=ccy, price_1020_run=p0, price_1027_run=p1, price_change=p1 / p0 - 1)
    for v in ("a", "b"):
        for h in ("12m", "24m"):
            r[f"exp_ret_{h}_{v}_then"] = m0[v][h][0]
            r[f"exp_ret_{h}_{v}_now"], r[f"p_loss_raw_{h}_{v}_now"], r[f"p_below_hurdle_{h}_{v}_now"] = m1[v][h]
        r[f"entry_12m_{v}_now"] = e1[v]
    r.update(p_loss_raw_12m_a_then=m0["a"]["12m"][1], p_below_hurdle_12m_a_then=m0["a"]["12m"][2],
             value_per_share_one_method=value, value_vs_price=(value / p1 - 1) if value else np.nan, value_method=value_note,
             scorecard=score, rank_1020=then_rank, rank_1027=now_rank, rule_applied=rule)
    rows.append(r)

# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
P_THEN = {"Nexans": 105.0, "Japan Material": 1600.0, "Organo": 2100.0, "Shin-Etsu": 5200.0,      # [placeholder: previous-run prices]
          "Amkor": 100.0, "AtkinsRealis": 100.0, "HD Hyundai Electric": 400000.0}
P_NOW = {"Amkor": 90.0, "AtkinsRealis": 101.0, "HD Hyundai Electric": 380000.0}                    # [placeholder: rerun prices, as in the *_final_1027.py placeholders]
NEX_TARGET_EBITDA, NEX_PENSIONS = 600.0, 100.0          # [placeholder: company medium-term EBITDA target; pension deficit, filing]
ORG_FY2, ORG_NETDEBT = 17.0, 0.0                        # [placeholder: FY2 EBITDA from I/B/E/S growth; net debt]
JM_FY2, JM_NETCASH = 13.5, 10.0                         # [placeholder]
SE_PARKED_VALUE = 5500.0                                # [placeholder: sum-of-the-parts midpoint, not refreshed]
# Ranks and rules are yours to fill in from your own decision document: (rank before rerun, rank after rerun, rule applied).
CASE_NAMES = ("Nexans", "Japan Material", "Organo", "Shin-Etsu", "Amkor", "AtkinsRealis", "HD Hyundai Electric")
RANK = {nm: (None, None, "fill in: the consequence your scorecard pre-committed for this case") for nm in CASE_NAMES}   # [placeholder]
# ===== END PLACEHOLDER INPUTS =====

# ---------- scenario names (simulate_v2_1027 / simulate_v2)
s0 = pd.read_csv(R / "scenario/tables/sim2_summary.csv"); s1 = pd.read_csv(R / "scenario/tables/sim_1027_summary.csv")
en = pd.read_csv(R / "scenario/tables/sim_1027_entry_prices.csv")
def sm(df, nm):
    d = df[(df.company == nm) & (df.sigma_label == "main")]
    return {v: {h: tuple(d[(d.variant == v) & (d.horizon == h)][["exp_return", "p_loss_raw", "p_below_hurdle"]].iloc[0]) for h in ("12m", "24m")} for v in ("a", "b")}
ent = lambda nm: {v: float(en[(en.company == nm) & (en.variant == v) & (en.horizon == "12m")].entry_price.iloc[0]) for v in ("a", "b")}

# one-method values (one valuation method per case, fixed before the rerun) [inference]
I = V.INPUTS
nx = I["Nexans"]; fm_nx = nx["fwd_mult"]
nex_val = (NEX_TARGET_EBITDA * fm_nx - NEX_TARGET_EBITDA - NEX_PENSIONS) / nx["shares"] / 1.09 ** 2   # target year at today's multiple, net debt 1.0x EBITDA + pensions, 2y at the 9% hurdle
og = I["Organo"]; org_val = (ORG_FY2 * og["fwd_mult"] - ORG_NETDEBT) / og["shares"] * 1000   # FY2 growth leg one year out
jm = I["Japan Material"]; jm_val = (JM_FY2 * jm["fwd_mult"] + JM_NETCASH) / jm["shares"] * 1000
print(f"one-method: Nexans {nex_val:.1f} at {fm_nx:.3f}x; Organo {org_val:,.0f} at {og['fwd_mult']:.3f}x; Japan Material {jm_val:,.0f} at {jm['fwd_mult']:.3f}x")

SC = {nm: "scorecard result: fill in from your own quarterly scorecard (see q3_2026_arith.py)" for nm in CASE_NAMES}
add("Nexans", "EUR", P_THEN["Nexans"], nx["price"], sm(s0, "Nexans"), sm(s1, "Nexans"), ent("Nexans"), nex_val,
    "target-year EBITDA x today's multiple, less 1.0x net debt and pensions, / shares, discounted 2y at 9%", SC["Nexans"], *RANK["Nexans"])
add("Japan Material", "JPY", P_THEN["Japan Material"], jm["price"], sm(s0, "Japan Material"), sm(s1, "Japan Material"), ent("Japan Material"), jm_val,
    "FY2 x today's multiple + net cash, / shares (one year out, undiscounted)", SC["Japan Material"], *RANK["Japan Material"])
add("Organo", "JPY", P_THEN["Organo"], og["price"], sm(s0, "Organo"), sm(s1, "Organo"), ent("Organo"), org_val,
    "FY2 x today's multiple - net debt, / shares (one year out, undiscounted)", SC["Organo"], *RANK["Organo"])
add("Shin-Etsu", "JPY", P_THEN["Shin-Etsu"], I["Shin-Etsu"]["price"], sm(s0, "Shin-Etsu"), sm(s1, "Shin-Etsu"), ent("Shin-Etsu"), SE_PARKED_VALUE,
    "SOTP mid (not refreshed)", SC["Shin-Etsu"], *RANK["Shin-Etsu"])

# ---------- Amkor
a0 = pd.read_csv(R / "amkor/tables/amkr_final.csv"); a1 = pd.read_csv(R / "amkor/tables/amkr_final_1027.csv")
a1f = a1[a1.section == "final"]
AV = {"a": "no reversion", "b": "corrected reversion ("}   # label prefixes written by methodology/amkor/amkor_final*.py
am = lambda d: {v: {h: tuple(d[(d.variant.str.startswith(AV[v]) if v == "b" else d.variant == AV[v]) & (d.horizon == h)][["exp_return", "p_loss_raw", "p_below_hurdle"]].iloc[0]) for h in ("12m", "24m")} for v in ("a", "b")}
a_ent = {v: float(a1f[(a1f.variant.str.startswith(AV[v]) if v == "b" else a1f.variant == AV[v]) & (a1f.horizon == "12m")].entry_price.iloc[0]) for v in ("a", "b")}
a_val = float(a1[(a1.section == "basis") & a1.variant.str.startswith("one method")].value.iloc[0])
add("Amkor", "USD", P_THEN["Amkor"], P_NOW["Amkor"], am(a0), am(a1f), a_ent, a_val, "FY2 EBITDA x today's multiple - half the 12m net debt build, / shares",
    SC["Amkor"], *RANK["Amkor"])

# ---------- AtkinsRealis
t0 = pd.read_csv(R / "atkins/tables/atrl_final.csv"); t1 = pd.read_csv(R / "atkins/tables/atrl_final_1027.csv")
TV = {"a": "no reversion (headline)", "b": "reversion"}
def at(d):
    d = d[(d.section == "simulation") & d.case.str.startswith("C FINAL")]
    return {v: {h: tuple(d[(d.variant == TV[v]) & (d.horizon == h)][["exp_return", "p_loss_raw", "p_below_hurdle"]].iloc[0]) for h in ("12m", "24m")} for v in ("a", "b")}
t1s = t1[(t1.section == "simulation") & t1.case.str.startswith("C FINAL")]
t_ent = {v: float(t1s[(t1s.variant == TV[v]) & (t1s.horizon == "12m")].entry_price.iloc[0]) for v in ("a", "b")}
t_val = float(t1[(t1.section == "sotp") & t1.case.str.startswith("SOTP mid:")].per_share.iloc[0])
add("AtkinsRealis", "CAD", P_THEN["AtkinsRealis"], P_NOW["AtkinsRealis"], at(t0), at(t1), t_ent, t_val, "SOTP mid on FY1 estimates (segment peer multiples), latest balance sheet",
    SC["AtkinsRealis"], *RANK["AtkinsRealis"])

# ---------- HD Hyundai Electric
h0 = pd.read_csv(R / "hdhyundai/tables/hde_final.csv"); h1 = pd.read_csv(R / "hdhyundai/tables/hde_final_1027.csv")
HV = {"a": "audited basis, no reversion [HEADLINE]", "b": "audited basis, reversion (resid "}   # label prefixes written by hde_final*.py
hd = lambda d: {v: {h: tuple(d[(d.section == "final") & d.variant.str.startswith(HV[v]) & (d.horizon == h)][["exp_return", "p_loss_raw", "p_below_hurdle"]].astype(float).iloc[0]) for h in ("12m", "24m")} for v in ("a", "b")}
h1f = h1[h1.section == "final"]
h_ent = {v: float(h1f[h1f.variant.str.startswith(HV[v]) & (h1f.horizon == "12m")].entry_price_krw.iloc[0]) for v in ("a", "b")}
h_val = float(h1[(h1.section == "basis") & h1.variant.str.startswith("one method")].exp_return.iloc[0])
add("HD Hyundai Electric", "KRW", P_THEN["HD Hyundai Electric"], P_NOW["HD Hyundai Electric"], hd(h0), hd(h1), h_ent, h_val,
    "FY2 operating profit x own forward multiple + net cash, / shares", SC["HD Hyundai Electric"], *RANK["HD Hyundai Electric"])

out = pd.DataFrame(rows)
out.to_csv(OUT / "ranking_1027.csv", index=False)

# ---------- labelled sensitivity, not the headline: reversion residual re-based for the own-price move only (peers held at 16 Oct)
sens = []
for nm, old_p in (("Nexans", P_THEN["Nexans"]), ("Organo", P_THEN["Organo"])):
    i = I[nm]; k = 1000.0 if i["ccy"] == "JPY" else 1.0
    ev_new = i["price"] * i["shares"] / k - i["netcash12"]; ev_old = old_p * i["shares"] / k - i["netcash12"]
    rs = i["resid"] + np.log(ev_new / ev_old)
    V.INPUTS[nm]["sigma"] = float(pd.read_csv(R / "scenario/tables/sim_1027_inputs.csv").set_index("company").sigma_main[nm])
    for hz, lab in ((0, "12m"), (1, "24m")):
        r = V.simulate(nm, hz, "b", overrides=dict(resid=rs))
        sens.append(dict(company=nm, horizon=lab, resid_1020=i["resid"], resid_rebased=rs, exp_return=r["ret"].mean(),
                         p_loss_raw=float((r["ret"] < 0).mean()), p_below_hurdle=float((r["ret"] < r["hurdle"]).mean())))
sens = pd.DataFrame(sens)
sens.to_csv(R / "scenario/tables/sim_1027_resid_rebased_sensitivity.csv", index=False)

pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60)
show = ["company", "price_1020_run", "price_1027_run", "price_change", "exp_ret_12m_a_then", "exp_ret_12m_a_now", "p_loss_raw_12m_a_now",
        "p_below_hurdle_12m_a_now", "exp_ret_12m_b_then", "exp_ret_12m_b_now", "p_loss_raw_12m_b_now", "p_below_hurdle_12m_b_now",
        "exp_ret_24m_a_now", "exp_ret_24m_b_now", "p_loss_raw_24m_a_now", "p_below_hurdle_24m_a_now", "p_loss_raw_24m_b_now", "p_below_hurdle_24m_b_now",
        "entry_12m_a_now", "entry_12m_b_now", "value_per_share_one_method", "value_vs_price", "rank_1020", "rank_1027"]
print(out[show].round(3).T.to_string())
print(sens.round(3).to_string())
