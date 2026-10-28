"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-atkins audit (2026-10-20): re-runs the ATRL cross-section, SOTP and Monte Carlo with documented corrections.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/audit_atkins.py
Inputs: atkins_simulate.py engine conventions (seed 20261020, 20,000 paths), tables/atrl_multiples_peer_inputs.csv [WRDS data],
company figures [company filing: FY2025 MD&A, Q2 2026 MD&A, Q2 2026 financial statements]. Corrections are [inference].
Outputs: tables/atrl_audit_sim.csv, tables/atrl_audit_sotp.csv, tables/atrl_audit_xsec.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from scipy.stats import norm
import atkins_simulate as S
from atkins_common import TABLES, ATRL_IN

# ---------- 1. Company facts used by the audit [company filing] ----------
H1 = dict(adj_ebitda=546.6, esr=429.4, nuc=169.4, corp=67.1, nuc_rev=1407.8)          # [company filing: Q2 2026 MD&A p.10, ESR and Nuclear sections]
FY25 = dict(adj_ebitda=1008.5, h1_adj=470.5, esr=870.9, esr_h1=393.3, nuc=279.5, nuc_netrev=1096.0, nuc_rev=2302.0,
            esr_netrev=860.9 + 2168.7 + 1539.1 + 775.1, esr_rev=7515.0)               # [company filing: FY2025 MD&A, ESR and Nuclear]; 1,008.5 total incl. Capital 29.3
JUN26 = dict(cash=833.0, recourse=696.4, nonrecourse=84.2, leases=96.6 + 444.5)         # [company filing: Q2 2026 financial statements] (C$ thousands / 1000)
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
price, shares = 100.0, 150.0                                   # [placeholder: market price C$, Compustat share count m]
QUANT_MID_REPORTED = 100.0                                     # [placeholder: per-share SOTP mid reported by the first quant pass]
# ===== END PLACEHOLDER INPUTS =====
mcap = price * shares

# FY2026 EBITDA build
h2h1 = (FY25["adj_ebitda"] - FY25["h1_adj"]) / FY25["h1_adj"]                          # 1.143 (H1'25 includes Capital, so conservative)
fy1_season = H1["adj_ebitda"] * (1 + h2h1)
esr_fy = H1["esr"] * (FY25["esr"] / FY25["esr_h1"])                                    # ESR H2/H1 seasonality FY25
nuc_fy = H1["nuc"] + (2700 - H1["nuc_rev"]) * H1["nuc"] / H1["nuc_rev"]                # guide 2.7bn at H1 EBITDA/revenue
other_fy = 2 * (H1["adj_ebitda"] - H1["esr"] - H1["nuc"] + H1["corp"])
fy1_bottom = esr_fy + nuc_fy + other_fy - 130.0
nd_jun = JUN26["recourse"] + JUN26["nonrecourse"] + JUN26["leases"] - JUN26["cash"]   # lease-inclusive, as Compustat dltt+dlc-che
print(f"H2/H1 FY25 {1+h2h1:.3f}; FY26 seasonal {fy1_season:.0f}; bottom-up ESR {esr_fy:.0f} + Nuc {nuc_fy:.0f} + other {other_fy:.0f} - corp 130 = {fy1_bottom:.0f}")
print(f"Nuclear EBITDA/gross revenue FY25 {FY25['nuc']/FY25['nuc_rev']:.3f}, H1'26 {H1['nuc']/H1['nuc_rev']:.3f}; net/gross FY25 {FY25['nuc_netrev']/FY25['nuc_rev']:.3f}")
print(f"ESR net/gross FY25 {FY25['esr_netrev']/FY25['esr_rev']:.3f}; Jun-26 lease-incl. net debt {nd_jun:.0f} vs quant {ATRL_IN['net_debt']:.0f}")
FY1 = 1171.0                                                                           # audited mode (seasonal and bottom-up agree within 15)
FY2 = 1295.0   # ESR net rev 5,720 x 1.06 x 17.5% = 1,061 + nuclear 2.9bn x 12.0% = 348 + other 20 - corp 135 [inference from 2027 targets]
FY3 = FY2 * 1.07                                                                       # 2028 extrapolated at 7% [inference]
ev_c = mcap + nd_jun; fm_c = ev_c / FY1
print(f"EV corrected {ev_c:.0f}; fwd multiple {fm_c:.2f}x on {FY1:.0f} (quant {S.FM:.2f}x on its FY1 mode; quant EV on {FY1:.0f} = {(mcap+ATRL_IN['net_debt'])/FY1:.2f}x)")
INP_Q = S.INP
# cash path: H2'26 FCF = (OCF 500 - 180.8) - (capex 187.5 - 79.0) - leases 50 = 160 (incl. LSTK); 2027 FCF 350, 2028 400 [inference]
nc12 = -(nd_jun - 160 - 350 * 10 / 12); nc24 = -(nd_jun - 160 - 350 - 400 * 10 / 12)
print(f"net cash 12m {nc12:.0f} (quant {INP_Q['netcash12']:.0f}), 24m {nc24:.0f} (quant {INP_Q['netcash24']:.0f})")

# ---------- 2. Monte Carlo (copy of S.simulate with escale, FY basis and Ontario split exposed) ----------
INP = dict(S.INP); INP["sigma"] = float(pd.read_csv(TABLES / "atrl_sim_inputs.csv").sigma_main.iloc[0])
def sim(hz, variant="b", scen=None, corr=None, eb=None, nc=None, fm=None, escale=None, ont_other=None, seed=S.SEED):
    scen = scen or S.SCEN; corr = corr or S.CORR; fm = fm or S.FM
    rng = np.random.default_rng(seed + hz); years = 1.0 if hz == 0 else 2.0
    slope = 0.0 if variant == "a" else S.SLOPE; es = escale if escale is not None else (0.5 if hz == 0 else 1.0)
    names = list(scen); L = np.linalg.cholesky(S.corr_matrix(names, {k: v for k, v in corr.items() if k[0] in names and k[1] in names}, variant == "c"))
    z = rng.standard_normal((S.N, len(names))) @ L.T; on = {}
    for i, s in enumerate(names):
        p = scen[s]["prob"][hz]; on[s] = z[:, i] < norm.ppf(p)
        if ont_other and s.startswith("3 "):
            po = ont_other["prob"][hz]; on["3b Ontario picks another design"] = (z[:, i] >= norm.ppf(p)) & (z[:, i] < norm.ppf(p + po))
    lo, md, hi = eb if eb else (INP["ebitda12"] if hz == 0 else INP["ebitda24"])
    base_eb = rng.triangular(lo, md, hi, S.N); base_m = fm * rng.triangular(0.8, 1.0, 1.2, S.N)
    eb_fac, m_fac = np.ones(S.N), np.ones(S.N)
    allsc = dict(scen); 
    if ont_other: allsc["3b Ontario picks another design"] = ont_other
    for s, d in allsc.items():
        k = on[s]; m = int(k.sum()); eb_fac[k] *= 1 + es * rng.uniform(*d["ebitda"], m); m_fac[k] *= rng.uniform(*d["mult"], m)
    sig = INP["sigma"] * np.sqrt(years)
    ebitda = base_eb * eb_fac * np.exp(rng.normal(-0.5 * sig ** 2, sig, S.N))
    mult = base_m * m_fac * np.exp(-slope * years * S.RESID)
    netc = nc if nc is not None else (INP["netcash12"] if hz == 0 else INP["netcash24"])
    ret = (ebitda * mult + netc) / shares / price - 1
    return ret, ebitda
def row(label, var, **kw):
    out = dict(variant=label, reversion=var)
    for hz, lab in ((0, "12m"), (1, "24m")):
        k = {kk: (v[hz] if isinstance(v, tuple) and len(v) == 2 and kk in ("eb", "nc", "escale") else v) for kk, v in kw.items()}
        r, e = sim(hz, var, **k)
        out[f"E_{lab}"] = r.mean(); out[f"med_{lab}"] = np.median(r); out[f"Ploss_{lab}"] = (r < 0).mean(); out[f"Pgt15_{lab}"] = (r > 0.15).mean()
    return out

t = lambda lo, hi, fm: (1 + lo / fm, 1 + hi / fm)
def scen_set(fm, nuc_fix=False, ont=False, rec_fix=False):
    sc = {k: dict(v) for k, v in S.SCEN.items()}
    for k in sc: sc[k]["mult"] = t(*{"2": (1.0, 2.0), "3": (1.5, 3.0), "4": (-2.0, -1.0), "5": (-1.0, -0.5), "6": (-2.0, -1.0), "7": (-4.0, -2.0), "8": (-3.0, -2.0)}[k[0]], fm)
    if nuc_fix:   # nuclear revenue deltas at the filed 12.0% EBITDA/gross revenue, on FY2 1,295
        sc["2 Nuclear renaissance, CANDU exports"]["ebitda"] = (280 * .12 / FY2, 560 * .12 / FY2)
        sc["3 Ontario new-build go-ahead"]["ebitda"] = (100 * .12 / FY2, 300 * .12 / FY2)
        sc["7 Nuclear incident or policy reversal"]["ebitda"] = (-540 * .12 / FY2, -270 * .12 / FY2)
    if ont: sc["3 Ontario new-build go-ahead"]["prob"] = (0.20, 0.40)
    if rec_fix: sc["8 Rate or recession shock"].update(ebitda=(-0.12, -0.04), mult=t(-2.5, -1.5, fm))
    return sc
other = lambda fm: dict(prob=(0.12, 0.28), ebitda=(0.0, 0.0), mult=t(-1.5, -0.5, fm))
FM = S.FM
eb_q = (INP["ebitda12"], INP["ebitda24"]); eb_q_tc = (INP["ebitda24"], tuple(x * 1.07 for x in INP["ebitda24"]))
eb_c_tc = ((FY2 * .94, FY2, FY2 * 1.06), (FY3 * .94, FY3, FY3 * 1.06))
rows = []
for var in "ab":
    rows.append(row("0 reported (FY1 at 12m, FY2 at 24m)", var))
    rows.append(row("1 time-consistent: FY2 at 12m, FY3 at 24m", var, eb=eb_q_tc))
    rows.append(row("2 + filed EBITDA level (FY1 1,171) and lease-incl. net debt, FCF build", var, eb=eb_c_tc, fm=fm_c, nc=(nc12, nc24), scen=scen_set(fm_c)))
    rows.append(row("3 + nuclear scenario EBITDA at filed 12% margin", var, eb=eb_c_tc, fm=fm_c, nc=(nc12, nc24), scen=scen_set(fm_c, nuc_fix=True)))
    rows.append(row("4 + Ontario two-sided (Monark 20/40, other design 12/28)", var, eb=eb_c_tc, fm=fm_c, nc=(nc12, nc24), scen=scen_set(fm_c, True, True), ont_other=other(fm_c)))
    rows.append(row("5 + recession impact to base rate (-4 to -12%) [AUDITED CENTRAL]", var, eb=eb_c_tc, fm=fm_c, nc=(nc12, nc24), scen=scen_set(fm_c, True, True, True), ont_other=other(fm_c)))
    rows.append(row("5a central, escale 0.75 at 12m", var, eb=eb_c_tc, fm=fm_c, nc=(nc12, nc24), escale=(0.75, 1.0), scen=scen_set(fm_c, True, True, True), ont_other=other(fm_c)))
    rows.append(row("5b central, quant EBITDA level (FY2 / FY3 from the first pass)", var, eb=eb_q_tc, fm=FM, nc=(nc12, nc24), scen=scen_set(FM, True, True, True), ont_other=other(FM)))
au = pd.DataFrame(rows); au.to_csv(TABLES / "atrl_audit_sim.csv", index=False)
pd.set_option("display.width", 220); print(au.round(3).to_string())

# EBITDA-fall check vs base rate: share of 24m paths where EBITDA ends below FY1 (two-year fall)
r, e = sim(1, "b", eb=eb_q[1] and INP["ebitda24"]); print("reported 24m: P(FY2027 EBITDA < FY2026 mode) =", round(float((e < INP["ebitda12"][1]).mean()), 3), "(compare with the consultancy base rate in tables/atrl_ebitda_falls.csv)")

# ---------- 3. SOTP (FY2026 basis) ----------
cons = pd.read_csv(TABLES / "atrl_multiples_peer_inputs.csv", dtype={"gvkey": str})
med_c = cons.query("group=='consult'").mult_used.median()
med_n = float(np.median(cons.query("name in ['BWXT','Curtiss-Wright','Mirion']").mult_used)); mid_n = (med_c + med_n) / 2   # nuclear-product forward median
p75_c = cons.query("group=='consult'").mult_used.quantile(0.75)
def sotp(esr, nuc, nm, em=med_c, corp=130, nd=nd_jun, lstk=60):
    eq = esr * em + nuc * nm - corp * em - nd - lstk; return eq / shares
s_rows = [dict(case="quant mid (reported)", per_share=QUANT_MID_REPORTED),
          dict(case="audited mid: filed ESR and nuclear build, lease-incl. net debt, LSTK H2 60", per_share=sotp(esr_fy, nuc_fy, mid_n)),
          dict(case="audited Ontario only: nuclear to nuclear-product median, ESR at median", per_share=sotp(esr_fy, nuc_fy, med_n)),
          dict(case="quant 'high' with audited inputs (ESR at consultancy p75)", per_share=sotp(esr_fy, nuc_fy, med_n, em=p75_c)),
          dict(case="audited low: nuclear at consultancy median", per_share=sotp(esr_fy, nuc_fy, med_c))]
imp_n = (mcap + nd_jun + 60 - esr_fy * med_c + 130 * med_c) / nuc_fy
s_rows.append(dict(case="nuclear multiple implied by price (ESR at median)", per_share=imp_n))
s_rows.append(dict(case="C$ per share per turn on nuclear", per_share=nuc_fy / shares))
sd = pd.DataFrame(s_rows); sd["vs_price"] = np.where(sd.case.str.contains("implied|per turn"), np.nan, sd.per_share / price - 1)
sd.to_csv(TABLES / "atrl_audit_sotp.csv", index=False); print(sd.round(3).to_string())

# ---------- 4. Cross-section: corrected ATRL multiple, nuclear group without Cameco/Centrus ----------
P = cons.set_index("gvkey"); out = []
for lab, mult_atrl, drop in (("reported (first pass)", S.FM, []), ("audited", fm_c, []), ("audited, ex Cameco+Centrus", fm_c, ["024370", "112759"])):
    d = P.drop(index=drop).copy(); d.loc["014352", "mult_used"] = mult_atrl
    for spec, cols, sub in (("growth+margin+nuclear+flag", ["rev_cagr_3y", "ebitda_margin", "nuclear", "trailing_flag"], None),
                            ("consult+nuclear only", ["rev_cagr_3y", "ebitda_margin", "nuclear", "trailing_flag"], "noepc")):
        dd = d[d.group != "epc"] if sub else d; est = dd.drop(index="014352")
        m = sm.OLS(np.log(est.mult_used), sm.add_constant(est[cols])).fit(cov_type="HC1")
        fit = float(np.exp(m.predict(sm.add_constant(dd[cols], has_constant="add").loc[["014352"]])).iloc[0])
        out.append(dict(case=lab, spec=spec + " (ATRL left out)", n=int(m.nobs), atrl=mult_atrl, fitted=fit, resid=mult_atrl / fit - 1, nuc_coef=m.params["nuclear"], nuc_t=m.tvalues["nuclear"]))
    out.append(dict(case=lab, spec="vs consultancy forward median", n=int(cons.query("group=='consult'").mult_used.notna().sum()), atrl=mult_atrl, fitted=med_c, resid=mult_atrl / med_c - 1))
xs = pd.DataFrame(out); xs.to_csv(TABLES / "atrl_audit_xsec.csv", index=False); print(xs.round(3).to_string())
