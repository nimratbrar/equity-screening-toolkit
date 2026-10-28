"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Shared loaders and inputs for the AtkinsRéalis quant scripts (methodology/atkins/atkins_*.py).
Reuses methodology/scenario/reg_common.py (indices, fx) and the Amkor US market proxy (cap-weighted 300 largest US names,
data/scenario/cache/us_market_proxy.csv) because no S&P 500 or S&P/TSX series is in data/scenario/indices_list.csv.

DATA LIMITS (as found in the original run):
 - ATRL (gvkey 014352) and WSP (277846) are absent from data/scenario/daily_prices.csv and fundamentals_annual.csv
   (price-issue bug in the pull, fixed in the client, pull not re-run). The deep dive's Price performance sheet holds
   only 1m/3m/6m/12m returns and 1y volatility, no daily series, so NO return regression can be run on ATRL itself.
   The weekly regressions use Stantec (029985, NYSE USD line) as the nearest Canadian consultancy proxy plus the baskets.
 - No I/B/E/S for the Canadian names: ATRL FY1/FY2 EBITDA are built from company guidance [company filing] below.
 - fx_daily.csv has no CAD; USD/CAD comes from FRED DEXCAUS (data/scenario/external/fred_DEXCAUS.csv) [source: FRED].
 - No Canadian 10y series on disk; the US 10y (FRED DGS10) is the rate factor [source: FRED].
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/atkins_common.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "methodology/scenario"))
from reg_common import DATA, CACHE, fx, to_usd_rate, ASOF  # noqa: E402,F401
TABLES = ROOT / "methodology/atkins/tables"; TABLES.mkdir(parents=True, exist_ok=True)
# Latest deep-dive workbook from pipeline.py --config pipelines/atkins_eng_nuclear_peers.json (your own WRDS run; None until it exists)
DEEP = (sorted((ROOT / "output").glob("atkins_eng_nuclear_peers_*/analysis.xlsx")) or [None])[-1]
ATRL = "014352"

# gvkey -> (short name, group): example peer set; identifiers as in your Compustat deep dive
PEERS = {
 "014352": ("ATRL", "case"), "277846": ("WSP", "consult"), "029985": ("Stantec", "consult"), "006216": ("Jacobs", "consult"),
 "147988": ("AECOM", "consult"), "024783": ("Tetra Tech", "consult"), "029789": ("Arcadis", "consult"), "229521": ("Sweco", "consult"),
 "103051": ("Afry", "consult"), "004818": ("Fluor", "epc"), "174310": ("KBR", "epc"), "035158": ("Parsons", "epc"),
 "050688": ("Amentum", "epc"), "254665": ("Worley", "epc"), "185229": ("BWXT", "nuclear"), "003662": ("Curtiss-Wright", "nuclear"),
 "039935": ("Mirion", "nuclear"), "024370": ("Cameco", "nuclear"), "112759": ("Centrus", "nuclear"),
}
CONSULT = [g for g, (n, grp) in PEERS.items() if grp == "consult"]
NUCLEAR = [g for g, (n, grp) in PEERS.items() if grp == "nuclear"]

# ---- ATRL inputs, C$ millions [company filing unless marked] ----
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
ATRL_IN = dict(
    price=100.0, price_date="YYYY-MM-DD", shares=150.0,            # [placeholder: market price and Compustat share count]
    net_debt=100.0,                                                # [placeholder: Compustat FY net debt, dltt+dlc-che]
    ebitda_trailing_compustat=1000.0,                              # [placeholder: Compustat trailing oibdp]
    ret_12m=0.0, vol_1y=0.30,                                      # [placeholder: 12m return and 1y realised volatility from your price data]
)
# ===== END PLACEHOLDER INPUTS =====
ATRL_IN.update(
    ebitda_fy25_adj=979.2,                                         # [company filing, PS&PM basis]
    # FY2026 adj. EBITDA (FY1): H1'26 546.6 x 2 = 1,093 as mode [company filing, annualised: inference]; low/high +/-4%
    ebitda_fy1=(1050.0, 1093.0, 1136.0),
    # FY2027 (FY2) from 2025-2027 targets [company filing: ESR organic 5-7%, ESR EBITDA margin 17-18% by 2027,
    # nuclear 2.6-3.0bn at 11-13% EBIT]: segment build below gives about 1,195 [inference]
    ebitda_fy2=(1120.0, 1195.0, 1270.0),
    # segment EBITDA split FY2026e [inference from filings]
    seg_fy1=dict(ESR=870.0, Nuclear=340.0, Other=13.0, Corporate=-130.0),
    seg_fy2=dict(ESR=955.0, Nuclear=365.0, Other=10.0, Corporate=-135.0),
    lstk_cash_drag_2026=(100.0, 150.0),                            # [company filing: Q4 2025 earnings call]
)
ATRL_IN["mcap"] = ATRL_IN["price"] * ATRL_IN["shares"]
ATRL_IN["ev"] = ATRL_IN["mcap"] + ATRL_IN["net_debt"]
ATRL_IN["fwd_mult"] = ATRL_IN["ev"] / ATRL_IN["ebitda_fy1"][1]

def deep(sheet):
    d = pd.read_excel(DEEP, sheet_name=sheet, dtype={"gvkey": str})
    if "gvkey" in d.columns: d["gvkey"] = d.gvkey.str.zfill(6)
    return d

def build_cache():
    keep = set(PEERS); parts = []
    for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "price", "ajexdi", "trfd", "curcdd"], chunksize=2_000_000):
        ch["gvkey"] = ch.gvkey.str.zfill(6); parts.append(ch[ch.gvkey.isin(keep)])
    px = pd.concat(parts).sort_values(["gvkey", "datadate"]); px.to_csv(CACHE / "prices_atkins.csv", index=False); return px

def prices() -> pd.DataFrame:
    f = CACHE / "prices_atkins.csv"
    px = pd.read_csv(f, dtype={"gvkey": str}) if f.exists() else build_cache()
    px = px.dropna(subset=["price"]).copy(); px["datadate"] = pd.to_datetime(px.datadate)
    px["tri"] = px.price / px.ajexdi.fillna(1.0) * px.trfd.fillna(1.0); return px

def tri_wide() -> pd.DataFrame:
    return prices().pivot_table(index="datadate", columns="gvkey", values="tri").sort_index()

def us_market() -> pd.Series:
    f = CACHE / "us_market_proxy.csv"
    if not f.exists():
        sys.path.insert(0, str(ROOT / "methodology/amkor")); import amkor_common; amkor_common.build_cache()
    return pd.read_csv(f, parse_dates=["datadate"]).set_index("datadate")["us_mkt_logret"]

def fred(name, col):
    s = pd.read_csv(DATA / "external" / f"fred_{name}.csv", parse_dates=["observation_date"])
    return pd.to_numeric(s.set_index("observation_date")[col], errors="coerce").dropna()

def usdcad(): return fred("DEXCAUS", "DEXCAUS")     # CAD per USD, daily
def us10y(): return fred("DGS10", "DGS10")           # percent, daily
def fedfunds(): return fred("FEDFUNDS", "FEDFUNDS")  # percent, monthly

# Event dummies: public news and policy events (date, label, expected sign for ATRL, for peers, class) [public sources; signs are inference, illustrative]
EVENTS = [
 ("2024-10-31", "CNSC accepts Monark", "+", "0", "nuclear_co"), ("2024-11-15", "Cernavoda 3 and 4 EPCM", "+", "0", "nuclear_co"),
 ("2024-12-15", "Cernavoda 1 EPC", "+", "0", "nuclear_co"), ("2024-12-20", "Bruce C referred to panel", "+", "0", "ontario"),
 ("2025-01-16", "IEA Path to a New Era", "+", "+", "nuclear_macro"), ("2025-01-23", "Ontario advances Pickering", "+", "0", "ontario"),
 ("2025-02-27", "Ontario election PC majority", "+", "0", "ontario"), ("2025-04-28", "Federal election Liberal minority", "0", "0", "canada"),
 ("2025-05-08", "Ontario approves Darlington SMR 1", "+", "+", "ontario"), ("2025-05-23", "US nuclear EOs", "+", "+", "nuclear_macro"),
 ("2025-06-11", "UK Spending Review Sizewell C", "+", "+", "infra"), ("2025-06-12", "Ontario Energy for Generations", "+", "0", "ontario"),
 ("2025-06-25", "NATO 3.5 percent", "+", "+", "infra"), ("2025-09-10", "EU court nuclear taxonomy", "+", "+", "nuclear_macro"),
 ("2025-10-28", "US Westinghouse USD 80bn", "0", "+", "nuclear_macro"), ("2025-11-04", "Canada Budget 2025 infrastructure", "+", "+", "infra"),
 ("2025-11-28", "Ontario approves Pickering execution", "+", "0", "ontario"), ("2025-12-11", "Bruce C directive", "+", "0", "ontario"),
 ("2026-01-15", "FT NEOM scaled back", "-", "-", "mideast"), ("2026-01-23", "FY26 appropriations ONE flat", "0", "0", "infra"),
 ("2026-02-02", "Darlington refurb complete", "+", "0", "nuclear_co"), ("2026-02-04", "Bruce 3 complete early", "+", "0", "nuclear_co"),
 ("2026-02-08", "Eglinton Crosstown opens", "+", "0", "company"), ("2026-02-17", "OPG Wesleyville agreement", "+", "0", "ontario"),
 ("2026-02-28", "Iran war begins", "-", "-", "mideast"), ("2026-04-13", "Liberal majority", "0", "0", "canada"),
 ("2026-04-30", "Brent peak 126", "-", "-", "macro"), ("2026-05-22", "BUILD America 250 committee", "+", "+", "infra"),
 ("2026-05-28", "IEA WEI 2026", "+", "+", "nuclear_macro"), ("2026-06-08", "Bruce 3 returns to service", "+", "0", "nuclear_co"),
 ("2026-06-16", "Argentina CANDU export", "+", "0", "nuclear_co"), ("2026-08-06", "ATRL Q2 2026 results", "co", "0", "company"),
 ("2026-09-16", "Fed hike", "-", "-", "macro"), ("2026-09-30", "IIJA extended to 11 Dec", "0", "-", "infra"),
 ("2026-10-12", "Hormuz tanker attacks", "-", "-", "mideast"),
]
# the four pending rows in the scenario file (28 Oct, 3 Nov, 5 Nov, 11 Dec 2026) are after the sample end and are not dummies

if __name__ == "__main__":
    px = prices(); print(px.groupby("gvkey").datadate.agg(["min", "max", "count"]).assign(name=lambda d: d.index.map(lambda g: PEERS[g][0])).to_string())
    print("missing from daily prices:", [PEERS[g][0] for g in PEERS if g not in set(px.gvkey)])
    print("ATRL fwd EV/EBITDA on FY1 mode:", round(ATRL_IN["fwd_mult"], 2), "EV", round(ATRL_IN["ev"], 1))
    print(us_market().tail(2)); print(usdcad().tail(2)); print(us10y().tail(2))
