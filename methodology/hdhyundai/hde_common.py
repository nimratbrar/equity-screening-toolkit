"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Shared loaders and inputs for the HD Hyundai Electric (HDE) quant scripts (methodology/hdhyundai/hde_*.py).
Reuses methodology/scenario/reg_common.py (paths, fx). Prices and accounts come from your own WRDS extract unless marked.

DATA ON DISK (what the scripts expect):
 - HDE and its grid peers in data/scenario/daily_prices.csv (built by methodology/scenario/pull_data.py). Check the last
   Korean close in your own file; holiday rows can lag other markets.
 - If no KOSPI series is in indices_daily.csv, the Korean market factor is a cap-weighted index of the Korean names in
   data/scenario/universe.csv (HDE excluded), static weights at the latest cap (csho x last price) [WRDS data, inference].
 - If fx_daily.csv has no CHF, the CHF line (ABB) is converted to USD with EUR as the proxy [inference].
 - I/B/E/S: only the current FY1/FY2 snapshot (deep dive Estimates sheet); no estimate history, so revisions are measured
   from reported quarters and the breadth field, not from a consensus time series.
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/hdhyundai/hde_common.py
"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "methodology/scenario"))
from reg_common import DATA, CACHE, fx  # noqa: E402,F401
TABLES = ROOT / "methodology/hdhyundai/tables"; TABLES.mkdir(parents=True, exist_ok=True)
DEEP = sorted((ROOT / "output").glob("hdhyundai_grid_peers_*/analysis.xlsx"))[-1]
HDE = "324210"
ASOF = pd.Timestamp("2026-10-16")   # set to the last Korean close in your own price file

# gvkey -> (short name, group, price currency) [WRDS data: deep dive Price performance / Valuation inputs]
PEERS = {
 "324210": ("HDE", "case", "KRW"), "327718": ("Hyosung HI", "korea", "KRW"), "207909": ("LS Electric", "korea", "KRW"),
 "202599": ("LS Corp", "korea", "KRW"), "246296": ("Doosan Enerbility", "korea", "KRW"),
 "005650": ("Hitachi", "japan", "JPY"), "019043": ("Mitsubishi Electric", "japan", "JPY"), "101851": ("Fuji Electric", "japan", "JPY"),
 "101771": ("Meidensha", "japan", "JPY"), "340153": ("Siemens Energy", "europe", "EUR"), "101336": ("Schneider", "europe", "EUR"),
 "210418": ("ABB", "europe", "CHF"), "277039": ("Legrand", "europe", "EUR"), "284521": ("Prysmian", "europe", "EUR"),
 "246217": ("Nexans", "europe", "EUR"), "045169": ("GE Vernova", "us", "USD"), "004199": ("Eaton", "us", "USD"),
 "005764": ("Hubbell", "us", "USD"), "008699": ("Powell", "us", "USD"),
}
PEER_LIST = [g for g in PEERS if g != HDE]
KOREA = [g for g, v in PEERS.items() if v[1] == "korea"]
TRANSFORMER = ["327718", "207909", "005650", "340153", "045169"]   # transformer peers: Hyosung, LS Electric, Hitachi, Siemens Energy, GEV
NAME = {g: v[0] for g, v in PEERS.items()}

# ---- HDE inputs, KRW bn unless stated ----
# ===== PLACEHOLDER INPUTS: ILLUSTRATIVE ONLY =====
# Real values must come from your own licensed data (I/B/E/S, Compustat, Capital IQ) or the company's filings.
HDE_IN = dict(
    price=400000.0, price_date="2026-10-16",                    # [placeholder: last close, Compustat g_secd]
    shares_jun26=35.992704,                                     # issued less treasury, m shares [company filing: Jun-26 report]
    shares_issued=36.0,                                         # [placeholder: Compustat cshoc]
    # net debt = dltt + dlc - che from the latest Compustat quarter (lease-inclusive basis)
    dltt_jun26=50.0, dlc_jun26=100.0, che_jun26=650.0,          # [placeholder: Compustat fundq dlttq, dlcq, cheq]
    netcash_company_jun26=895.5,                                # cash less debt, ex leases [company filing]; NOT the valuation basis
    ebitda_fy1_cons=1000.0,                                     # [placeholder: I/B/E/S FY1 EBITDA]
    eps_fy1=20000.0, eps_fy2=25000.0, n_analysts=20, revision_breadth=0.0,   # [placeholder: I/B/E/S EPS FY1, FY2, count, breadth]
    sales_fy1_cons=4000.0,                                      # [placeholder: I/B/E/S FY1 sales, KRW bn]
    sales_guide_2026=4350.0, sales_target_2027=4740.0,          # [company filing: 2026 guidance disclosure, value-up plan]
    backlog_usd_m=8490.0, backlog_krw=12310.5, ltm_sales=4336.9, # [company filing: Jun-26 report]
    capex_remaining=462.5, dps_q=1300.0, payout_fy25=0.349,     # [company filing]
)
# KRW per USD reference rates used by the EBITDA and simulation scripts. Real values: FRED DEXKOUS or your own FX source.
FX = dict(
    avg_1h26=1450.0,      # [placeholder: average KRW/USD over the first half of the latest fiscal year]
    avg_q3=1400.0,        # [placeholder: average KRW/USD over the latest reported quarter]
    spot=1350.0,          # [placeholder: spot KRW/USD at the analysis date]
    spot_new=1350.0,      # [placeholder: spot KRW/USD at the rerun date]
    avg_ytd=1450.0,       # [placeholder: year-to-date average KRW/USD]
)
# Half-year facts for the currency-split EBITDA model (KRW bn). Sales, OP and Korea sales are public [company filing: 1H26 report];
# D&A is a placeholder because the original came from Compustat (oibdpq - oiadpq).
H1 = dict(sales=2178.3, op=545.3, da=40.0, korea_sales=471.7)  # da: [placeholder: Compustat oibdpq - oiadpq]
FWD_USD_M, FWD_RATE = 522.6, 1446.87                            # USD forwards sold and their average rate [company filing: 1H26 report]
# ===== END PLACEHOLDER INPUTS =====
HDE_IN["net_debt_jun26"] = HDE_IN["dltt_jun26"] + HDE_IN["dlc_jun26"] - HDE_IN["che_jun26"]
HDE_IN["mcap"] = HDE_IN["price"] * HDE_IN["shares_jun26"] / 1000.0            # KRW bn
HDE_IN["ev"] = HDE_IN["mcap"] + HDE_IN["net_debt_jun26"]
HDE_IN["fwd_mult"] = HDE_IN["ev"] / HDE_IN["ebitda_fy1_cons"]


def deep(sheet):
    d = pd.read_excel(DEEP, sheet_name=sheet, dtype={"gvkey": str})
    if "gvkey" in d.columns: d["gvkey"] = d.gvkey.str.zfill(6)
    return d


def build_cache():
    """One chunked pass: the grid names' daily rows and the Korean universe for the market proxy."""
    u = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); u["gvkey"] = u.gvkey.str.zfill(6)
    kr = u[(u["loc"] == "KOR") & (u.curcd == "KRW")]
    a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, usecols=["gvkey", "fyear", "indfmt", "csho"], low_memory=False)
    a["gvkey"] = a.gvkey.str.zfill(6); a = a[(a.indfmt == "INDL") & (a.fyear >= 2024)].sort_values("fyear").groupby("gvkey").tail(1)
    keep, krset = set(PEERS), set(kr.gvkey) - {HDE}
    parts, mk = [], []
    for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "price", "ajexdi", "trfd", "cshtrd", "curcdd"], chunksize=2_000_000):
        ch["gvkey"] = ch.gvkey.str.zfill(6); parts.append(ch[ch.gvkey.isin(keep)]); mk.append(ch[ch.gvkey.isin(krset) & (ch.curcdd == "KRW")])
    px = pd.concat(parts).sort_values(["gvkey", "datadate"]); px.to_csv(CACHE / "prices_hde.csv", index=False)
    m = pd.concat(mk).dropna(subset=["price"]); m["tri"] = m.price / m.ajexdi.fillna(1) * m.trfd.fillna(1)
    last = m.sort_values("datadate").groupby("gvkey").tail(1).set_index("gvkey")
    cap = (a.set_index("gvkey").csho.reindex(last.index) * last.price).dropna(); cap = cap[cap > 0]
    wide = m[m.gvkey.isin(cap.index)].pivot_table(index="datadate", columns="gvkey", values="tri").sort_index()
    lr = np.log(wide).diff()
    lr = lr.where(lr.abs() < 0.35)                                       # drop bad ticks (Korean daily limit is 30%)
    W = (cap / cap.sum()).reindex(lr.columns).fillna(0); ok = lr.notna()
    r = (lr.fillna(0) * W).sum(axis=1) / (ok * W).sum(axis=1)
    ew = lr.mean(axis=1, skipna=True)                                    # equal-weight robustness factor
    top = (cap / cap.sum()).sort_values(ascending=False).head(5)
    print("KR proxy top weights:", {g: round(w, 3) for g, w in top.items()})
    proxy = pd.DataFrame({"kr_mkt_logret": r, "kr_ew_logret": ew, "n_names": ok.sum(axis=1)}); proxy.index = pd.to_datetime(proxy.index); proxy.index.name = "datadate"
    proxy = proxy[proxy.n_names >= 100]; proxy.to_csv(CACHE / "kr_market_proxy.csv")
    return px


def prices():
    f = CACHE / "prices_hde.csv"
    px = pd.read_csv(f, dtype={"gvkey": str}) if (f.exists() and (CACHE / "kr_market_proxy.csv").exists()) else build_cache()
    px["gvkey"] = px.gvkey.astype(str).str.zfill(6)
    px = px.dropna(subset=["price"]).copy(); px["datadate"] = pd.to_datetime(px.datadate)
    px["tri"] = px.price / px.ajexdi.fillna(1.0) * px.trfd.fillna(1.0)
    return px


def drop_stale(w):
    """Korean/Japanese holiday rows repeat the prior close with no volume; keep them (zero return) but they are flagged in hde_returns."""
    return w


def tri_wide(col="tri"):
    return prices().pivot_table(index="datadate", columns="gvkey", values=col).sort_index()


def kr_market(col="kr_mkt_logret"):
    f = CACHE / "kr_market_proxy.csv"
    if not f.exists(): build_cache()
    return pd.read_csv(f, parse_dates=["datadate"]).set_index("datadate")[col]


def us_market():
    f = CACHE / "us_market_proxy.csv"   # built by methodology/amkor/amkor_common.py (300 largest US names, cap-weighted)
    return pd.read_csv(f, parse_dates=["datadate"]).set_index("datadate")["us_mkt_logret"]


def usd_per_local():
    """Daily USD per unit of each price currency, from fx_daily (per GBP). CHF proxied by EUR [inference]."""
    f = fx()
    out = pd.DataFrame({c: f["USD"] / f[c] for c in ["KRW", "JPY", "EUR"]}); out["USD"] = 1.0; out["CHF"] = out["EUR"]
    return out


def tri_usd():
    t = tri_wide(); u = usd_per_local().reindex(t.index).ffill()
    return pd.DataFrame({g: t[g] * u[PEERS[g][2]] for g in t.columns})


def usdkrw():
    """KRW per USD: FRED DEXKOUS (daily, noon NY) [source: FRED]."""
    s = pd.read_csv(DATA / "external/fred_DEXKOUS.csv", parse_dates=["observation_date"])
    return pd.to_numeric(s.set_index("observation_date")["DEXKOUS"], errors="coerce").dropna()


def fred(name, col):
    s = pd.read_csv(DATA / "external" / f"fred_{name}.csv", parse_dates=["observation_date"])
    return pd.to_numeric(s.set_index("observation_date")[col], errors="coerce").dropna()


def quarterly(gv=HDE):
    q = pd.read_csv(DATA / "fundamentals_quarterly.csv", dtype={"gvkey": str}, low_memory=False)
    q["gvkey"] = q.gvkey.str.zfill(6); q = q[q.gvkey == gv].copy(); q["datadate"] = pd.to_datetime(q.datadate)
    return q.sort_values("datadate").drop_duplicates("datadate", keep="last").set_index("datadate")


# Event dummies (date, label, sign HDE, sign peers, class): public news and policy events from the scenario file [source per that file; signs are inference].
# Pending rows (22 Oct 2026 onward) are after the sample end and are excluded.
EVENTS = [
 ("2024-07-10", "DOE LPT Resilience report", "0", "0", "us_demand"), ("2024-08-02", "ITC continues Korea LPT AD order", "-", "-", "trade"),
 ("2024-12-06", "Grid Strategies 128 GW", "+", "+", "us_demand"), ("2024-12-19", "LBNL data-center report", "+", "+", "us_demand"),
 ("2025-04-02", "US reciprocal tariffs (Korea 25%)", "-", "-", "trade"), ("2025-04-08", "AD 2022-23 final, HDE 0.00%", "+", "-", "trade"),
 ("2025-04-22", "HDE -9.75% margin peak-out fears", "co", "0", "company"), ("2025-07-30", "US-Korea 15% deal", "+", "+", "trade"),
 ("2025-08-14", "WoodMac 30% deficit", "+", "+", "us_demand"), ("2025-08-18", "Transformers on S232 derivative list", "-", "-", "trade"),
 ("2025-11-14", "Korea-US joint fact sheet", "+", "+", "trade"), ("2025-11-19", "Grid Strategies 166 GW", "+", "+", "us_demand"),
 ("2025-12-12", "Hyosung Memphis +50%", "-", "+", "supply"), ("2026-01-26", "Trump 25% threat on Korea", "-", "-", "trade"),
 ("2026-01-29", "NERC LTRA 224 GW", "+", "+", "us_demand"), ("2026-02-02", "GE Vernova completes Prolec buyout", "-", "-", "supply"),
 ("2026-02-06", "HDE FY2025 results", "co", "0", "company"), ("2026-02-20", "Supreme Court strikes IEEPA tariffs", "+", "+", "trade"),
 ("2026-02-28", "Iran war begins", "-", "-", "geo"), ("2026-03-06", "Alabama plant 2 groundbreaking", "+", "0", "supply"),
 ("2026-03-10", "Yellow Envelope Act in force", "-", "-", "korea"), ("2026-04-02", "S232 revision, transformers 15% to 2027", "+", "+", "trade"),
 ("2026-04-28", "HDE Q1 2026 results", "co", "0", "company"), ("2026-06-29", "Hitachi South Boston groundbreaking", "-", "-", "supply"),
 ("2026-06-30", "Won at 17-year low (1,555)", "+", "+", "fx"), ("2026-07-03", "KRW 1.12tn data-center deal", "+", "0", "us_demand"),
 ("2026-07-24", "Section 122 ends; S301 cap 12.5%", "0", "0", "trade"), ("2026-07-29", "HDE Q2 2026 results", "co", "0", "company"),
 ("2026-08-14", "AD 2023-24 final, HDE 0.00%", "+", "-", "trade"), ("2026-08-26", "EO 14420 bars Chinese bulk-power gear", "+", "+", "trade"),
 ("2026-08-31", "WoodMac 2026 deficit 15%", "-", "-", "supply"), ("2026-09-02", "HHI partial strikes begin", "-", "0", "korea"),
 ("2026-10-12", "North Korea missile launch", "-", "-", "korea"),
]

if __name__ == "__main__":
    px = prices()
    print(px.groupby("gvkey").datadate.agg(["min", "max", "count"]).assign(name=lambda d: d.index.map(NAME)).to_string())
    print("missing:", [NAME[g] for g in PEERS if g not in set(px.gvkey)])
    m = kr_market(); print("KR proxy", m.index.min().date(), m.index.max().date(), len(m), "ann. vol", round(m.std() * np.sqrt(250), 3))
    print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in HDE_IN.items()})
