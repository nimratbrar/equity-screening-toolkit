"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Shared loaders for the Amkor quant scripts (methodology/amkor/*.py). Reuses methodology/scenario/reg_common.py.
Builds data/scenario/cache/prices_osat.csv (Amkor + 16 OSAT peers, daily) and cache/us_market_proxy.csv
(cap-weighted daily log return of the 300 largest US names in the price file: no S&P 500 or Nasdaq series is on disk,
so this is the market factor [WRDS data, inference]). All market data [WRDS data].
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/amkor/amkor_common.py
"""
import sys, json
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "methodology/scenario"))
from reg_common import DATA, CACHE, indices, fx, to_usd_rate, ASOF  # noqa: E402
TABLES = ROOT / "methodology/amkor/tables"; TABLES.mkdir(parents=True, exist_ok=True)   # local outputs, git-ignored
AMKR = "110039"   # Compustat gvkey of the case company (an identifier, not a data value); look it up in your own data
PEER_CSV = sorted(   # latest deep-dive run from pipeline.py --config pipelines/amkor_osat_peers.json (regenerate with your own WRDS access)
    (ROOT / "output").glob("amkor_osat_peers_*/amkor_osat_peers_*.csv"))[-1]
XLSX = PEER_CSV.parent / "analysis.xlsx"

def osat_set() -> pd.DataFrame:
    """17 names (Amkor + 16 peers) with gvkey, from the WRDS deep-dive CSV mapped by ISIN/ticker [WRDS data]."""
    pc = pd.read_csv(PEER_CSV, dtype={"gvkey": str}, low_memory=False)
    names = json.load(open(ROOT / "pipelines/amkor_osat_peers.json"))["analysis"]["names"]
    m = pc[pc.tic.isin(names) | pc["isin"].isin(names)][["gvkey", "conm", "tic", "isin", "loc", "curcd", "gsubind", "region"]].copy()
    m["gvkey"] = m.gvkey.str.zfill(6); m["is_amkor"] = m.gvkey == AMKR
    return m.reset_index(drop=True)

def build_cache():
    core = osat_set(); keep = set(core.gvkey)
    lp = pd.read_csv(CACHE / "last_price_all.csv", dtype={"gvkey": str}); lp["gvkey"] = lp.gvkey.str.zfill(6)
    a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, usecols=["gvkey", "fyear", "indfmt", "csho", "curcd"], low_memory=False)
    a["gvkey"] = a.gvkey.str.zfill(6)
    a = a[(a.indfmt == "INDL") & (a.fyear >= 2024)].sort_values("fyear").groupby("gvkey").tail(1)
    u = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); u["gvkey"] = u.gvkey.str.zfill(6)
    us = u[(u.region == "na") & (u.loc == "USA") & (u.curcd == "USD")].merge(a[["gvkey", "csho"]], on="gvkey").merge(lp[["gvkey", "price"]], on="gvkey")
    us["cap"] = us.csho * us.price; us = us[us.gvkey != AMKR].sort_values("cap", ascending=False).head(300)
    big = set(us.gvkey); w = dict(zip(us.gvkey, us.cap / us.cap.sum()))
    parts, mk = [], []
    for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "price", "ajexdi", "trfd", "curcdd"], chunksize=2_000_000):
        ch["gvkey"] = ch.gvkey.str.zfill(6)
        parts.append(ch[ch.gvkey.isin(keep)]); mk.append(ch[ch.gvkey.isin(big)])
    px = pd.concat(parts).sort_values(["gvkey", "datadate"]); px.to_csv(CACHE / "prices_osat.csv", index=False)
    m = pd.concat(mk).dropna(subset=["price"]); m["tri"] = m.price / m.ajexdi.fillna(1) * m.trfd.fillna(1)
    wide = m.pivot_table(index="datadate", columns="gvkey", values="tri").sort_index()
    lr = np.log(wide).diff(); W = pd.Series(w).reindex(lr.columns).fillna(0)
    ok = lr.notna(); r = (lr.fillna(0) * W).sum(axis=1) / (ok * W).sum(axis=1)   # renormalise over names priced that day
    proxy = pd.DataFrame({"us_mkt_logret": r, "n_names": ok.sum(axis=1)}); proxy.index = pd.to_datetime(proxy.index); proxy.index.name = "datadate"
    proxy = proxy[proxy.n_names >= 100]; proxy.to_csv(CACHE / "us_market_proxy.csv")
    return px

def prices_osat() -> pd.DataFrame:
    f = CACHE / "prices_osat.csv"
    px = pd.read_csv(f, dtype={"gvkey": str}) if f.exists() else build_cache()
    px = px.dropna(subset=["price"]).copy(); px["datadate"] = pd.to_datetime(px.datadate)
    px["tri"] = px.price / px.ajexdi.fillna(1.0) * px.trfd.fillna(1.0)
    return px

def tri_osat() -> pd.DataFrame:
    return prices_osat().pivot_table(index="datadate", columns="gvkey", values="tri").sort_index()

def us_market() -> pd.Series:
    f = CACHE / "us_market_proxy.csv"
    if not f.exists(): build_cache()
    p = pd.read_csv(f, parse_dates=["datadate"]).set_index("datadate")
    return p["us_mkt_logret"]

# Event dummies: dates and labels are public news, policy announcements and company filings (sign = expected effect on AMKR)
# [source: public news and company filings, dates as listed; signs are inference]. Compiled in the original scenario file (not published).
EVENTS_AMKR = [
 ("2024-07-26", "CHIPS preliminary terms, Peoria", "+", "chips"), ("2024-12-02", "BIS SME and HBM controls", "-", "china"),
 ("2024-12-13", "TSMC CoWoS 35k to 90k plan reported", "+", "ai"), ("2024-12-20", "CHIPS award USD 407m signed", "+", "chips"),
 ("2025-01-16", "BIS OSAT due-diligence rule", "+", "china"), ("2025-04-02", "Reciprocal tariffs announced (Vietnam 46%)", "-", "tariff"),
 ("2025-07-02", "Vietnam 20% framework", "+", "tariff"), ("2025-08-06", "Apple USD 600bn US program names Amkor", "+", "apple"),
 ("2025-08-28", "Peoria site move, production early 2028", "0", "chips"), ("2025-10-06", "Peoria groundbreaking", "+", "chips"),
 ("2025-10-26", "Malaysia reciprocal deal, chips exempt", "+", "tariff"), ("2025-11-10", "US-China one-year truce", "+", "china"),
 ("2025-12-03", "Intel reportedly outsources AI packaging to Amkor Incheon", "+", "ai"), ("2026-01-15", "Section 232 chip tariff 25% effective", "-", "tariff"),
 ("2026-02-20", "Supreme Court strikes IEEPA tariffs", "+", "tariff"), ("2026-02-24", "Section 122 10% surcharge starts", "-", "tariff"),
 ("2026-04-10", "ASE Kaohsiung test fab groundbreaking", "-", "ai"), ("2026-06-02", "IDC PC -11.3%; WSTS +90%", "m", "cycle"),
 ("2026-06-15", "CoWoS gap seen narrowing 20% to 10%", "-", "ai"), ("2026-06-16", "TSMC-Amkor 10-year Arizona agreement", "+", "chips"),
 ("2026-07-23", "Nvidia USD 1.5bn prepaid agreement", "+", "apple"), ("2026-07-24", "Section 122 expires; Section 301 VN 12.5%, MY 10%", "0", "tariff"),
 ("2026-07-28", "2Q26 results, 3Q guide below consensus", "-", "co"), ("2026-08-05", "TSMC expands CoW outsourcing to OSATs", "+", "ai"),
 ("2026-08-11", "China unit stake sale report", "+", "china"), ("2026-08-26", "IDC smartphones -16.7%", "-", "cycle"),
]
# Amkor results windows [inference]: Amkor reports in the last week of Jan, Apr, Jul and Oct (per the company's published results calendar);
# a trading day inside these windows is classed "results window" when identifying the largest daily moves.
RESULT_WINDOWS = [("01-25", "02-08"), ("04-24", "05-06"), ("07-24", "08-06"), ("10-24", "11-06")]

if __name__ == "__main__":
    core = osat_set(); print(core.to_string())
    px = prices_osat(); print(px.groupby("gvkey").datadate.agg(["min", "max", "count"]).to_string())
    m = us_market(); print(m.index.min(), m.index.max(), len(m), m.describe())
