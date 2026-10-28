"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

reconcile-atkins (2026-10-20): ONE final ATRL simulation and sum of the parts on one stated basis.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_final.py   (about 20 s)
Output: methodology/atkins/tables/atrl_final.csv (the only headline table; supersedes atrl_sim_* and atrl_audit_* for headline use).

Authority: audit_atkins.py and the red-team challenge, with three corrections found when checking against the company filings:
  (1) same-date share count: the audit paired the Jun-26 net debt with a later Compustat share count, which already
      reflects shares bought back after 30 Jun; the cash for them is not in the Jun-26 net debt. Final basis is the
      30 Jun 2026 balance sheet: net debt 489.1 and 160.829m shares [company filing: Q2 2026 financial statements, notes 9A and 12].
  (2) Middle East scenario EBITDA impact: the audit text gave a narrower range than the one left in the audit run.
  (3) reversion residual re-based to the same-date EV; used only in the reversion variant.
Everything else is the audit central (row 5 of atrl_audit_sim.csv). Corrections and assumptions are [inference].

BASIS (stated once):
  Net debt = recourse 696.4 + non-recourse 84.2 + lease liabilities 541.1 - cash 833.0 = 489.1 at 30 Jun 2026
  [company filing: Q2 2026 financial statements]. Lease-inclusive because the peer multiples are Compustat EV = mcap + dltt + dlc - che
  over oibdp (atkins_multiples.py line 55); for IFRS filers (WSP, Stantec, Arcadis, Sweco, Afry, ATRL) Compustat debt
  carries IFRS 16 lease liabilities and EBITDA is before lease cost. Recourse-only net cash (833.0 - 696.4 = 137) is the
  company's leverage measure, not the valuation basis.
  FY2026 adj. EBITDA = 1,171 (seasonal: H1'26 546.6 x FY25 H2/H1 1.143); bottom-up 1,176 cross-check [company filing, inference].
  Shares 160.829m at 30 Jun 2026 [company filing]; price is a placeholder below (use your own market data).
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import norm
import atkins_simulate as S
from atkins_common import TABLES, ATRL_IN

# ---------- 1. Facts [company filing: FY2025 MD&A, Q2 2026 MD&A, Q2 2026 financial statements] ----------
H1 = dict(adj_ebitda=546.6, esr=429.4, nuc=169.4, corp=67.1, nuc_rev=1407.8, other_seg=10.3)
FY25 = dict(adj_ebitda=1008.5, h1_adj=470.5, esr=870.9, esr_h1=393.3, nuc=279.5, nuc_rev=2302.0, nuc_netrev=1096.0,
            esr_netrev=5343.8, esr_rev=7515.0, seg_ebitda_total=1210.1, nuc_ebit=258.1, seg_ebit_ex_lstk_cap=1038.0, seg_ebit_total=972.6)
JUN26 = dict(cash=833.0, recourse=696.4, nonrecourse=84.2, leases=96.6 + 444.5, shares=160.829)
SH_JUL27 = 160.034                                   # shares m, 27 Jul 2026 [company filing]
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
SH_WRDS = 150.0                                      # [placeholder: latest Compustat share count, m]
PRICE = 100.0                                        # [placeholder: market price, C$]
# ===== END PLACEHOLDER INPUTS =====
H1_BUYBACK = 325.8   # 3,682,948 shares; cash outflow 345.6 incl. 18.3 tax and costs [company filing: Q2 2026 financial statements note 9B, cash flow]

h2h1 = (FY25["adj_ebitda"] - FY25["h1_adj"]) / FY25["h1_adj"]
fy1_season = H1["adj_ebitda"] * (1 + h2h1)
esr_fy = H1["esr"] * FY25["esr"] / FY25["esr_h1"]
nuc_h2_rev = 2700 - H1["nuc_rev"]; nuc_fy = H1["nuc"] + nuc_h2_rev * H1["nuc"] / H1["nuc_rev"]
other_fy = 2 * (H1["adj_ebitda"] - H1["esr"] - H1["nuc"] + H1["corp"])
fy1_bottom = esr_fy + nuc_fy + other_fy - 130.0
nd = JUN26["recourse"] + JUN26["nonrecourse"] + JUN26["leases"] - JUN26["cash"]
FY1 = 1171.0; FY2 = 1295.0; FY3 = FY2 * 1.07           # FY2/FY3 as audit_atkins.py [inference from 2027 targets]
print(f"FY26 EBITDA: seasonal {fy1_season:.1f} (H2/H1 {h2h1:.3f}); bottom-up ESR {esr_fy:.1f} + nuclear {nuc_fy:.1f} + other {other_fy:.1f} - corp 130 = {fy1_bottom:.1f}; used {FY1:.0f}")
print(f"Nuclear EBITDA / gross revenue FY25 {FY25['nuc']/FY25['nuc_rev']:.3f}, H1'26 {H1['nuc']/H1['nuc_rev']:.3f}; / net revenue FY25 {FY25['nuc']/FY25['nuc_netrev']:.3f}")
print(f"Nuclear share: FY25 seg EBITDA {FY25['nuc']/FY25['seg_ebitda_total']:.3f}, FY25 seg EBIT ex LSTK/Capital {FY25['nuc_ebit']/FY25['seg_ebit_ex_lstk_cap']:.3f}, "
      f"FY25 seg EBIT incl LSTK loss {FY25['nuc_ebit']/FY25['seg_ebit_total']:.3f}, FY26e seg EBITDA {nuc_fy/(esr_fy+nuc_fy+other_fy):.3f}")
print(f"Net debt 30 Jun 2026 lease-incl. {nd:.1f}; recourse-only net cash {JUN26['cash']-JUN26['recourse']:.1f}")

# ---------- 2. Share-count basis check ----------
post_jun = JUN26["shares"] - SH_WRDS                                 # shares retired after 30 Jun to the Oct WRDS count [inference]
mcap = PRICE * JUN26["shares"]; ev = mcap + nd; fm = ev / FY1
ev_alt = PRICE * SH_WRDS + nd + post_jun * PRICE                     # Oct count plus cash spent at about today's price [inference]
ev_audit = PRICE * SH_WRDS + nd
print(f"EV same-date {ev:.0f} = {fm:.2f}x; Oct count + buyback cash {ev_alt:.0f}; audit mix {ev_audit:.0f} = {ev_audit/FY1:.2f}x (understated by {ev-ev_audit:.0f})")
RESID_F = S.RESID + np.log(ev / (PRICE * SH_WRDS + ATRL_IN["net_debt"]))  # broad-model residual re-based to the same-date EV
nc12 = -(nd - 160 - 350 * 10 / 12); nc24 = -(nd - 160 - 350 - 400 * 10 / 12)   # H2'26 FCF 160 incl. LSTK, 2027 350, 2028 400 [audit, inference]

# ---------- 3. Simulation (audit engine, parametrised) ----------
INP = dict(S.INP); INP["sigma"] = float(pd.read_csv(TABLES / "atrl_sim_inputs.csv").sigma_main.iloc[0])
t = lambda lo, hi, m: (1 + lo / m, 1 + hi / m)
def scen_final(m, me_fix):
    sc = {k: dict(v) for k, v in S.SCEN.items()}
    for k in sc: sc[k]["mult"] = t(*{"2": (1.0, 2.0), "3": (1.5, 3.0), "4": (-2.0, -1.0), "5": (-1.0, -0.5), "6": (-2.0, -1.0), "7": (-4.0, -2.0), "8": (-2.5, -1.5)}[k[0]], m)
    sc["2 Nuclear renaissance, CANDU exports"]["ebitda"] = (280 * .12 / FY2, 560 * .12 / FY2)
    sc["3 Ontario new-build go-ahead"].update(prob=(0.20, 0.40), ebitda=(100 * .12 / FY2, 300 * .12 / FY2))
    sc["7 Nuclear incident or policy reversal"]["ebitda"] = (-540 * .12 / FY2, -270 * .12 / FY2)
    sc["8 Rate or recession shock"]["ebitda"] = (-0.12, -0.04)
    if me_fix: sc["5 Middle East slowdown deepens"]["ebitda"] = (-0.026, -0.016)   # Saudi 982 x 25 to 40% x AMEA 7.7% [company filing, inference]
    return sc
other = lambda m: dict(prob=(0.12, 0.28), ebitda=(0.0, 0.0), mult=t(-1.5, -0.5, m))

def sim(hz, variant, m, shares, resid, scen, nc):
    rng = np.random.default_rng(S.SEED + hz); years = 1.0 if hz == 0 else 2.0
    slope = 0.0 if variant == "a" else S.SLOPE; es = 0.5 if hz == 0 else 1.0
    names = list(scen); L = np.linalg.cholesky(S.corr_matrix(names, {k: v for k, v in S.CORR.items() if k[0] in names and k[1] in names}, False))
    z = rng.standard_normal((S.N, len(names))) @ L.T; on = {}; allsc = dict(scen); allsc["3b Ontario picks another design"] = other(m)
    for i, s in enumerate(names):
        p = scen[s]["prob"][hz]; on[s] = z[:, i] < norm.ppf(p)
        if s.startswith("3 "):
            po = allsc["3b Ontario picks another design"]["prob"][hz]; on["3b Ontario picks another design"] = (z[:, i] >= norm.ppf(p)) & (z[:, i] < norm.ppf(p + po))
    lo, md, hi = (FY2 * .94, FY2, FY2 * 1.06) if hz == 0 else (FY3 * .94, FY3, FY3 * 1.06)
    base_eb = rng.triangular(lo, md, hi, S.N); base_m = m * rng.triangular(0.8, 1.0, 1.2, S.N)
    eb_fac, m_fac = np.ones(S.N), np.ones(S.N)
    for s, d in allsc.items():
        k = on[s]; n = int(k.sum()); eb_fac[k] *= 1 + es * rng.uniform(*d["ebitda"], n); m_fac[k] *= rng.uniform(*d["mult"], n)
    sig = INP["sigma"] * np.sqrt(years)
    ebitda = base_eb * eb_fac * np.exp(rng.normal(-0.5 * sig ** 2, sig, S.N))
    value = (ebitda * base_m * m_fac * np.exp(-slope * years * resid) + nc[hz]) / shares
    p_none = float(np.mean(~np.any(np.column_stack(list(on.values())), axis=1)))
    return value, (1 + S.HURDLE) ** years - 1, p_none

STEPS = [  # label, multiple, shares, residual, Middle East fix
    ("A audit central reproduced (Compustat share count)", ev_audit / FY1, SH_WRDS, S.RESID, False),
    ("B + same-date shares (30 Jun filing), residual re-based", fm, JUN26["shares"], RESID_F, False),
    ("C FINAL: + Middle East -1.6 to -2.6%", fm, JUN26["shares"], RESID_F, True),
]
rows = []
for lab, m, sh, rs, me in STEPS:
    for var, vlab in (("a", "no reversion (headline)"), ("b", "reversion")):
        for hz, hlab in ((0, "12m"), (1, "24m")):
            v, h, pn = sim(hz, var, m, sh, rs, scen_final(m, me), (nc12, nc24)); r = v / PRICE - 1
            q35, m15 = np.quantile(v, 0.35), v.mean() / 1.15
            rows.append(dict(section="simulation", case=lab, variant=vlab, horizon=hlab, exp_return=r.mean(), p_loss_raw=(r < 0).mean(),
                             p_below_hurdle=(r < h).mean(), hurdle=h, ret_p05=np.quantile(r, .05), ret_p50=np.median(r), ret_p95=np.quantile(r, .95),
                             value_p05=np.quantile(v, .05), value_p50=np.median(v), value_p95=np.quantile(v, .95), p_gt15=(r > .15).mean(),
                             entry_price=min(q35, m15), p_no_overlay=pn, entry_rule="min(value q35 [raw P(loss)<35%], mean/1.15 [E>15%])"))

# ---------- 4. SOTP on FY2026e, same basis ----------
cons = pd.read_csv(TABLES / "atrl_multiples_peer_inputs.csv", dtype={"gvkey": str})
med_c = cons.query("group=='consult'").mult_used.median()                     # consultancy forward median [computed from your WRDS peer table]
med_n = float(np.median(cons.query("name in ['BWXT','Curtiss-Wright','Mirion']").mult_used)); mid_n = (med_c + med_n) / 2
LSTK = 60.0; CORP = 130.0
other_turns = 1.0 * FY1 / nuc_fy                                       # other-design scenario midpoint -1 group turn, carried by the nuclear leg
def sotp(nm, shares=JUN26["shares"], netd=nd):
    return (esr_fy * med_c + nuc_fy * nm - CORP * med_c - netd - LSTK) / shares
s_cases = [("SOTP low: nuclear at consultancy median", med_c), ("SOTP mid: nuclear at midpoint to nuclear-product median", mid_n),
           ("SOTP Ontario-Monark: nuclear at nuclear-product median", med_n), ("SOTP Ontario other design: mid less 1 group turn", mid_n - other_turns)]
for lab, nm in s_cases:
    ps = sotp(nm); rows.append(dict(section="sotp", case=lab, nuclear_mult=nm, esr_mult=med_c, per_share=ps, vs_price=ps / PRICE - 1))
rows.append(dict(section="sotp", case="SOTP mid on audit share mix (Compustat count, reconciliation only)", nuclear_mult=mid_n, esr_mult=med_c, per_share=sotp(mid_n, SH_WRDS), vs_price=sotp(mid_n, SH_WRDS) / PRICE - 1))
imp_n = (mcap + nd + LSTK - esr_fy * med_c + CORP * med_c) / nuc_fy
rows += [dict(section="sotp", case="nuclear multiple implied by price (ESR at consultancy median)", nuclear_mult=imp_n, esr_mult=med_c),
         dict(section="sotp", case="C$ per share per nuclear turn", per_share=nuc_fy / JUN26["shares"])]

# ---------- 5. Cross-section at the final multiple (audit spec, ATRL left out) ----------
P = cons.set_index("gvkey")
for lab, drop in (("all 19", []), ("ex Cameco and Centrus", ["024370", "112759"])):
    d = P.drop(index=drop).copy(); d.loc["014352", "mult_used"] = fm; cols = ["rev_cagr_3y", "ebitda_margin", "nuclear", "trailing_flag"]
    for spec, dd in (("growth+margin+nuclear+flag", d), ("consult+nuclear only", d[d.group != "epc"])):
        est = dd.drop(index="014352"); mdl = sm.OLS(np.log(est.mult_used), sm.add_constant(est[cols])).fit(cov_type="HC1")
        fit = float(np.exp(mdl.predict(sm.add_constant(dd[cols], has_constant="add").loc[["014352"]])).iloc[0])
        rows.append(dict(section="multiple", case=f"{spec}, {lab} (ATRL left out)", atrl_mult=fm, fitted=fit, vs_price=fm / fit - 1, nuc_coef=mdl.params["nuclear"], nuc_t=mdl.tvalues["nuclear"]))
rows.append(dict(section="multiple", case="vs consultancy forward median", atrl_mult=fm, fitted=med_c, vs_price=fm / med_c - 1))

# ---------- 6. Basis rows ----------
basis = [("price C$ [placeholder]", PRICE), ("shares m, 30 Jun 2026 [company filing]", JUN26["shares"]), ("shares m, 27 Jul 2026 [company filing]", SH_JUL27),
         ("shares m, Compustat [placeholder]", SH_WRDS), ("net debt lease-incl. 30 Jun 2026 [company filing]", nd), ("recourse-only net cash 30 Jun 2026 [company filing]", JUN26["cash"] - JUN26["recourse"]),
         ("EV same-date", ev), ("FY26e adj. EBITDA seasonal [inference]", fy1_season), ("FY26e adj. EBITDA bottom-up [inference]", fy1_bottom), ("FY26e used", FY1),
         ("forward EV/EBITDA FY26e", fm), ("FY27e EBITDA mode [inference]", FY2), ("FY28e EBITDA mode [inference]", FY3), ("ESR EBITDA FY26e", esr_fy), ("nuclear EBITDA FY26e", nuc_fy),
         ("consultancy forward median x [WRDS data, your run]", med_c), ("nuclear-product median x [WRDS data, your run]", med_n), ("nuclear share of FY26e segment EBITDA", nuc_fy / (esr_fy + nuc_fy + other_fy)),
         ("net cash path 12m", nc12), ("net cash path 24m", nc24), ("reversion residual log (re-based)", RESID_F), ("H1'26 buybacks C$m [company filing]", H1_BUYBACK)]
rows += [dict(section="basis", case=k, value=v) for k, v in basis]
out = pd.DataFrame(rows); out.to_csv(TABLES / "atrl_final.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
sim_cols = ["case", "variant", "horizon", "exp_return", "p_loss_raw", "p_below_hurdle", "ret_p05", "ret_p50", "ret_p95", "value_p05", "value_p50", "value_p95", "p_gt15", "entry_price", "p_no_overlay"]
print(out.query("section=='simulation'")[sim_cols].round(3).to_string())
print(out.query("section=='sotp'")[["case", "esr_mult", "nuclear_mult", "per_share", "vs_price"]].round(3).to_string())
print(out.query("section=='multiple'")[["case", "atrl_mult", "fitted", "vs_price", "nuc_coef", "nuc_t"]].round(3).to_string())
print(out.query("section=='basis'")[["case", "value"]].round(3).to_string())
