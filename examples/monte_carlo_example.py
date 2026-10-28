"""Self-contained Monte Carlo example of the toolkit's valuation conventions (no WRDS needed).

    uv run python examples/monte_carlo_example.py [--inputs examples/inputs_example.json] [--paths 20000] [--seed 7]

Uses ILLUSTRATIVE inputs for a fictional company. Replace them with your own licensed data and filings.
Conventions (see docs/METHODOLOGY.md, section 6):
  1. Forward multiple, struck today on the first fiscal year NOT yet reported today:
       fwd = (price x shares - net cash) / EBITDA_mode(first unreported FY)
     At horizon h, value = EBITDA of the first fiscal year still unreported at h x the multiple + net cash at h.
     No extra discounting: the forward multiple already prices the forward year.
  2. Scenarios: mutually exclusive states (base takes the residual probability) plus independent, two-sided overlays.
  3. Reversion rule (variant b): the log multiple residual versus a cross-section fit closes at `slope` per year,
     capped at full closure: multiple x exp(-min(1, slope x years) x residual). Variant a: no reversion.
  4. Report raw P(loss) = P(value < price) NEXT TO P(return < hurdle), never one labelled as the other.
  5. Entry price rule: min(35th percentile of value, mean value / 1.15), i.e. the price at which raw P(loss) < 35%
     and expected return > 15%.
  6. Cross-check: rescale the log-value dispersion to the stock's own-history 12m volatility x sqrt(years).
"""
from __future__ import annotations

import argparse
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent


def first_unreported(ebitda: dict, when: date, report_lag_days: int = 60) -> str:
    """First fiscal year whose results are not yet published at `when` (FY end plus a reporting lag)."""
    for fy, d in sorted(ebitda.items(), key=lambda kv: kv[1]["fiscal_year_end"]):
        if date.fromisoformat(d["fiscal_year_end"]) + timedelta(days=report_lag_days) > when:
            return fy
    raise ValueError("add a later fiscal year to ebitda_m: every year is reported by the horizon")


def draw_scenarios(rng, inp, hz, n):
    """Returns EBITDA factor, multiple factor and the state label per path."""
    states = {k: v for k, v in inp["states"].items() if not k.startswith("_")}
    probs = np.array([v["prob"][hz] for v in states.values()])
    if probs.sum() >= 1:
        raise ValueError("state probabilities must leave room for the base state")
    names = list(states) + ["Base"]
    pick = rng.choice(len(names), size=n, p=np.append(probs, 1 - probs.sum()))
    eb, mu = np.ones(n), np.ones(n)
    for i, s in enumerate(states.values()):
        k = pick == i
        eb[k] *= 1 + rng.uniform(*s["ebitda"], k.sum())
        mu[k] *= rng.uniform(*s["multiple"], k.sum())
    for o in (v for k, v in inp["overlays"].items() if not k.startswith("_")):
        k = rng.uniform(size=n) < o["prob"][hz]
        eb[k] *= 1 + rng.uniform(*o["ebitda"], k.sum())
        mu[k] *= rng.uniform(*o["multiple"], k.sum())
    return eb, mu, np.array(names)[pick]


def simulate(inp, hz, variant, n, seed):
    rng = np.random.default_rng(seed + hz)
    years = (1.0, 2.0)[hz]
    today = date.fromisoformat(inp["analysis_date"])
    horizon = today + timedelta(days=int(365 * years))
    fy_now, fy_h = first_unreported(inp["ebitda_m"], today), first_unreported(inp["ebitda_m"], horizon)
    cap = inp["price"] * inp["shares_m"]
    fwd = (cap - inp["net_cash_m"]["now"]) / inp["ebitda_m"][fy_now]["mode"]
    e = inp["ebitda_m"][fy_h]
    base_eb = rng.triangular(e["low"], e["mode"], e["high"], n)
    sp = inp["multiple_spread"]
    mult = fwd * rng.triangular(sp["low_ratio"], 1.0, sp["high_ratio"], n)
    eb_f, mu_f, state = draw_scenarios(rng, inp, hz, n)
    sig = inp["idiosyncratic_sigma_12m"] * np.sqrt(years)
    ebitda = base_eb * eb_f * np.exp(rng.normal(-0.5 * sig ** 2, sig, n))
    if variant == "b":
        mult = mult * np.exp(-min(1.0, inp["reversion_slope_per_year"] * years) * inp["multiple_residual_log"])
    value = (ebitda * mult * mu_f + inp["net_cash_m"][("12m", "24m")[hz]]) / inp["shares_m"]
    return dict(value=value, years=years, fwd=fwd, fy_now=fy_now, fy_h=fy_h, state=state)


def summarize(inp, r, label):
    v, p, yrs = r["value"], inp["price"], r["years"]
    ret = v / p - 1
    hurdle = (1 + inp["hurdle_per_year"]) ** yrs - 1
    rule = inp["entry_rule"]
    entry = min(np.quantile(v, rule["max_raw_p_loss"]), v.mean() / (1 + rule["min_expected_return"]))
    # own-history volatility cross-check: same median, log dispersion = own 12m sd x sqrt(years)
    lv = np.log(v / p)
    target = inp["own_history_sd_12m_log"] * np.sqrt(yrs)
    resc = np.exp(np.median(lv) + (lv - np.median(lv)) * target / lv.std()) - 1
    q = np.quantile(v, [0.05, 0.5, 0.95])
    print(f"{label:<34} {r['fy_h']:>4} @ {r['fwd']:5.2f}x | E[ret] {ret.mean():+6.1%} | raw P(loss) {np.mean(ret < 0):5.1%} | "
          f"P(ret < {hurdle:.1%} hurdle) {np.mean(ret < hurdle):5.1%} | value p5/p50/p95 {q[0]:.1f}/{q[1]:.1f}/{q[2]:.1f} | "
          f"entry {entry:.1f} | own-vol: E[ret] {resc.mean():+6.1%}, raw P(loss) {np.mean(resc < 0):5.1%}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", default=str(HERE / "inputs_example.json"))
    ap.add_argument("--paths", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    inp = json.loads(Path(a.inputs).read_text())
    if "ILLUSTRATIVE" in inp.get("_note", ""):
        print("*** ILLUSTRATIVE INPUTS for a fictional company: results show the method, not a view on any security ***\n")
    print(f"{inp['company']}: price {inp['price']} {inp['currency']}, {a.paths:,} paths, seed {a.seed}")
    for hz, h in ((0, "12m"), (1, "24m")):
        for var, lab in (("a", "no reversion"), ("b", "reversion")):
            summarize(inp, simulate(inp, hz, var, a.paths, a.seed), f"{h}, variant {var} ({lab})")
    r = simulate(inp, 0, "a", a.paths, a.seed)
    ret = r["value"] / inp["price"] - 1
    print("\nScenario tree, 12m variant a (exclusive states: P x E[ret | state]):")
    for s in np.unique(r["state"]):
        k = r["state"] == s
        print(f"  {s:<10} P {k.mean():5.1%}  E[ret | state] {ret[k].mean():+6.1%}  contribution {k.mean() * ret[k].mean():+6.2%}")


if __name__ == "__main__":
    main()
