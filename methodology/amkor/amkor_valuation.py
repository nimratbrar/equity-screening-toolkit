"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Amkor: one valuation method for the write-up. FY1 consensus EBITDA at today's forward multiple, plus the consensus growth leg
(FY2 at the same multiple), the reversion case shown separately, and an Arizona 2028 upside case (indicative).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_valuation.py -> tables/amkr_valuation.csv
"""
import numpy as np, pandas as pd
from amkor_common import TABLES

# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
price, shares, netcash = 100.0, 50.0, 25.0     # [placeholder: price and shares from Compustat; net cash from the latest company filing]
fy1 = 500.0                                     # [placeholder: I/B/E/S FY1 EBITDA consensus]
growth = 0.09                                   # [placeholder: FY2 and FY3 growth a year, inference]
resid = -0.30                                   # [placeholder: log residual of the case multiple vs a peer cross-section fit (amkor_multiples.py)]
slope = 0.25                                    # [placeholder: mean-reversion slope per year of the log multiple residual; estimate your own]
az_ebitda = (100.0, 140.0)                      # [placeholder: incremental Arizona Phase 1 EBITDA, low / high, inference from company targets]
target_rev, target_gm, target_da, target_sga = 4000.0, 0.175, 300.0, 100.0   # [placeholder: company medium-term targets, Investor Day; D&A and SG&A inference]
# ===== END PLACEHOLDER INPUTS =====

fy2 = fy1 * (1 + growth); fy3 = fy1 * (1 + growth) ** 2
mult = (price * shares - netcash) / fy1                 # today's forward multiple
rows = []
def row(label, ebitda, m, extra=0.0, note=""):
    v = (ebitda * m + netcash + extra) / shares; rows.append(dict(case=label, ebitda=ebitda, multiple=m, value_per_share=v, vs_price=v / price - 1, note=note))
row("1. FY1 consensus EBITDA x today's forward multiple (identity)", fy1, mult, note="= price by construction; shows what the price assumes")
row("2. Growth leg, 12m: FY2 EBITDA x same multiple", fy2, mult, note=f"FY2 = FY1 x {1 + growth:.2f} [inference]; no re-rating")
row("3. Growth leg, 24m: FY3 EBITDA x same multiple", fy3, mult, note=f"FY3 = FY1 x {1 + growth:.2f}^2 [inference]")
for lab, rs in [(f"4a. Reversion case, 12m: FY2 x multiple lifted by one step (slope -{slope} on residual {resid})", resid), (f"4b. Reversion case, 12m, half residual {resid / 2:.2f}", resid / 2)]:
    row(lab, fy2, mult * np.exp(-slope * rs), note=f"multiple {mult * np.exp(-slope * rs):.2f}x; fragile per the audit (slope is an upper bound)")
row("4c. Full reversion to the peer fitted multiple (not a forecast)", fy2, mult * np.exp(-resid), note=f"{mult * np.exp(-resid):.1f}x: the peer-implied level if the discount closed entirely")
# Arizona 2028 (indicative): Phase 1 revenue and gross margin per the company's Investor Day [company filing], here as placeholders
for lab, inc in [(f"5a. Arizona 2028, Phase 1 EBITDA +{az_ebitda[0]:.0f} on FY3 base", az_ebitda[0]), (f"5b. Arizona 2028, Phase 1 EBITDA +{az_ebitda[1]:.0f} on FY3 base", az_ebitda[1])]:
    row(lab, fy3 + inc, mult, note=f"2028 value at today's {mult:.2f}x; Phase 1 revenue x gross margin less SG&A plus D&A in COGS [inference, indicative]")
row(f"5c. Arizona 2028 at the Investor Day 2028 target: revenue {target_rev:,.0f} x {target_gm:.1%} GM", target_rev * target_gm + target_da - target_sga, mult,
    note="EBITDA = gross profit + D&A - SG&A/R&D [inference from company targets]")
df = pd.DataFrame(rows); df.to_csv(TABLES / "amkr_valuation.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120); print(f"today's forward multiple {mult:.3f}x"); print(df.round(3).to_string())
