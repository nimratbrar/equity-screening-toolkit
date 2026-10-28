"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

AtkinsRéalis analysis 3: driver sensitivities and cycle base rates.
(a) Peer revenue growth (10 engineering names, FY2014 to FY2025, data/atkins/peer_cycle_wrds.csv, your own Compustat extract [WRDS data, not included]; the four
    non-engineering rows in the original extract, Do-Fluoride, Gujarat Fluorochemicals, Navin Fluorine, Sonaecom, are name-match errors and
    are dropped) on rate drivers: annual change in the US 10y (FRED DGS10) and fed funds (FRED FEDFUNDS), t0 and t-1, firm fixed
    effects, year-clustered and firm-clustered t. No public infrastructure spending time series is on disk (nuclear_series.csv holds
    single hand-entered points), so the spending leg is NOT estimated; this is stated, not proxied.
(b) ATRL nuclear revenue vs an identified CANDU spend profile built from budget points in nuclear_series.csv [source] and
    straight-line phasing [inference]: n = 4, descriptive only.
(c) EBITDA drop-through in peer down years and the distribution of year-on-year EBITDA changes (sigma calibration input).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_drivers.py
Outputs (methodology/atkins/tables/): atrl_driver_panel.csv, atrl_candu_vs_nuclear.csv, atrl_peer_dropthrough.csv, atrl_ebitda_falls.csv
"""
import numpy as np, pandas as pd, statsmodels.api as sm
from atkins_common import ROOT, TABLES, us10y, fedfunds

ENG = ["AECOM", "AFRY AB", "ARCADIS NV", "FLUOR CORP", "JACOBS SOLUTIONS INC", "KBR INC", "STANTEC INC", "SWECO AB", "TETRA TECH INC", "WORLEY LTD"]
CONS = ["AECOM", "AFRY AB", "ARCADIS NV", "JACOBS SOLUTIONS INC", "STANTEC INC", "SWECO AB", "TETRA TECH INC"]
pc = pd.read_csv(ROOT / "data/atkins/peer_cycle_wrds.csv")   # columns: co, fyear, sale, margin, rev_g, dm
pc = pc[pc.co.isin(ENG)].copy().sort_values(["co", "fyear"])
pc["ebitda"] = pc.margin * pc.sale; pc["ebitda_l"] = pc.groupby("co").ebitda.shift(1); pc["sale_l"] = pc.groupby("co").sale.shift(1)
pc["ebitda_g"] = pc.ebitda / pc.ebitda_l - 1

# (a) rate drivers, annual averages
y10 = us10y().resample("YE").mean(); ff = fedfunds().resample("YE").mean()
drv = pd.DataFrame({"d10y": y10.diff(), "dff": ff.diff()}); drv.index = drv.index.year
drv["d10y_l1"] = drv.d10y.shift(1); drv["dff_l1"] = drv.dff.shift(1); drv["lvl10y"] = y10.set_axis(y10.index.year)
pn = pc.merge(drv, left_on="fyear", right_index=True).dropna(subset=["rev_g"])
rows = []
def panel(dep, xs, label, sample):
    s = pn[pn.co.isin(sample)].dropna(subset=[dep] + xs)
    X = pd.concat([s[xs], pd.get_dummies(s.co, drop_first=True, dtype=float)], axis=1); X = sm.add_constant(X)
    my = sm.OLS(s[dep], X).fit(cov_type="cluster", cov_kwds={"groups": s.fyear}); mf = sm.OLS(s[dep], X).fit(cov_type="cluster", cov_kwds={"groups": s.co.astype("category").cat.codes})
    for x in xs:
        rows.append(dict(dependent=dep, sample=label, regressor=x, beta=my.params[x], t_year_cl=my.tvalues[x], t_firm_cl=mf.tvalues[x], n=int(my.nobs), n_firms=s.co.nunique(), n_years=s.fyear.nunique(), r2_within=my.rsquared))
for dep in ["rev_g", "dm"]:
    for xs in [["d10y", "d10y_l1"], ["dff", "dff_l1"]]:
        panel(dep, xs, "10 engineering", ENG); panel(dep, xs, "7 consultancies", CONS)
dp = pd.DataFrame(rows); dp.to_csv(TABLES / "atrl_driver_panel.csv", index=False)

# (b) CANDU identified spend profile, C$bn per year [inference: straight-line phasing of sourced budgets]
# Darlington 12.8bn 2016-2026 (finished Feb 2026); Bruce MCR 13bn 2020-2033; Pickering: CanAtom early engineering 2.1bn 2024-2026, execution 26.8bn 2027-2035;
# Cernavoda 1 EUR 1.9bn (C$2.9bn at 1.5) 2027-2030; Cernavoda 3 and 4 EUR 3.2bn (C$4.8bn) 2027-2031 [source: nuclear_series.csv rows]
yrs = list(range(2020, 2031)); spend = pd.DataFrame(index=yrs, data={"darlington": 0.0, "bruce": 0.0, "pickering": 0.0, "cernavoda": 0.0})
for y in yrs:
    spend.loc[y, "darlington"] = 12.8 / 10 if y <= 2025 else (12.8 / 10 * 0.15 if y == 2026 else 0.0)
    spend.loc[y, "bruce"] = 13.0 / 14
    spend.loc[y, "pickering"] = 2.1 / 3 if 2024 <= y <= 2026 else (26.8 / 9 if y >= 2027 else 0.0)
    spend.loc[y, "cernavoda"] = (2.9 / 4 + 4.8 / 5) if y >= 2027 else 0.0
spend["candu_total"] = spend.sum(axis=1)
nuc = pd.Series({2023: 1044.0, 2024: 1489.0, 2025: 2302.0, 2026: 2700.0}, name="atrl_nuclear_rev_cad_m")   # [company filing; 2026 = guidance]
cv = spend.join(nuc); cv["atrl_rev_over_candu_spend"] = cv.atrl_nuclear_rev_cad_m / (cv.candu_total * 1000); cv.to_csv(TABLES / "atrl_candu_vs_nuclear.csv")
cv4 = cv.dropna(); corr = np.corrcoef(cv4.candu_total, cv4.atrl_nuclear_rev_cad_m)[0, 1]

# (c) drop-through and EBITDA fall base rates
down = pc[(pc.rev_g < 0) & pc.ebitda_l.notna()].copy(); down["drop_through"] = (down.ebitda - down.ebitda_l) / (down.sale - down.sale_l)
down[["co", "fyear", "rev_g", "dm", "ebitda_g", "drop_through"]].to_csv(TABLES / "atrl_peer_dropthrough.csv", index=False)
falls = []
for lab, s in [("10 engineering", pc), ("7 consultancies", pc[pc.co.isin(CONS)]), ("7 consultancies, down-revenue years", down[down.co.isin(CONS)])]:
    g = s.ebitda_g.dropna()
    falls.append(dict(sample=lab, firm_years=len(g), share_down=float((g < 0).mean()), gt10_down=float((g < -0.10).mean()), gt20_down=float((g < -0.20).mean()), gt30_down=float((g < -0.30).mean()),
                      p10=g.quantile(0.10), p25=g.quantile(0.25), median=g.median(), median_drop_through=s.drop_through.median() if "drop_through" in s else np.nan))
falls = pd.DataFrame(falls); falls.to_csv(TABLES / "atrl_ebitda_falls.csv", index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
print(dp.round(3).to_string()); print(cv.round(2).to_string()); print("corr CANDU spend vs ATRL nuclear revenue, n=4:", round(corr, 2))
print(down[["co", "fyear", "rev_g", "dm", "ebitda_g", "drop_through"]].round(3).to_string()); print(falls.round(3).to_string())
