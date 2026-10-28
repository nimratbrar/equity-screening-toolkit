"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Shared loaders for the quant-regression scripts (methodology/scenario/reg_*.py).

Builds data/scenario/universe_core.csv (the case-and-peer names from the three peer configs),
caches those names' daily prices (data/scenario/cache/prices_core.csv) and the latest price per gvkey for
the whole price file (data/scenario/cache/last_price_all.csv) so the 16mm-row file is read once.
All market data is [WRDS data]; event dates come from the macro agents' scenario files.
"""
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data/scenario"; CACHE = DATA / "cache"; CACHE.mkdir(parents=True, exist_ok=True)
TABLES = ROOT / "methodology/scenario/tables"; TABLES.mkdir(parents=True, exist_ok=True)   # git-ignored
ASOF = pd.Timestamp("2026-10-19")   # analysis date of the original run; set to your own data cut-off

CASES = {"246217": "Nexans", "220629": "Organo", "311307": "Japan Material", "100697": "Shin-Etsu"}
import json as _json
# Peer groups come from the watchlist configs pipelines/peers_<group>.json ("analysis.names"); keep those lists short.
SHORTLISTS = {g: _json.loads((ROOT / f"pipelines/peers_{g}.json").read_text())["analysis"]["names"]
              for g in ("cable_grid", "fab_water_facility", "chip_materials_and_chem")}

def universe_core() -> pd.DataFrame:
    f = DATA / "universe_core.csv"
    if f.exists():
        return pd.read_csv(f, dtype={"gvkey": str})
    u = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str})
    rows = []
    for g, tics in SHORTLISTS.items():
        m = u[u.tic.isin(tics)].copy(); m["group"] = g; rows.append(m)
    core = pd.concat(rows).drop_duplicates("gvkey")
    core["gvkey"] = core.gvkey.str.zfill(6); core["case"] = core.gvkey.isin(CASES)
    core = core[["gvkey","conm","tic","loc","region","curcd","gsubind","group","case"]].reset_index(drop=True)
    core.to_csv(f, index=False); return core

def build_price_cache():
    """One chunked pass over daily_prices.csv: the core names' full history, every company's last price and
    adjustment factor, and every company's price and adjustment factor at its latest fiscal year end
    (so market cap today = csho_fye * ajexdi_fye / ajexdi_today * price_today, which survives splits such as Organo's 5-for-1)."""
    core = universe_core(); keep = set(core.gvkey)
    a = pd.read_csv(DATA / "fundamentals_annual.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "fyear", "indfmt"], low_memory=False)
    a = a[(a.indfmt == "INDL") & (a.fyear >= 2024)].sort_values("fyear").groupby("gvkey").tail(1)
    fye = dict(zip(a.gvkey.str.zfill(6), pd.to_datetime(a.datadate)))
    parts, last, atfye = [], {}, {}
    for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey","datadate","price","ajexdi","trfd","cshtrd","curcdd"], chunksize=2_000_000):
        parts.append(ch[ch.gvkey.isin(keep)])
        ch = ch.dropna(subset=["price"]).sort_values("datadate"); ch["dd"] = pd.to_datetime(ch.datadate)
        for r in ch.groupby("gvkey").tail(1).itertuples(index=False):
            if r.gvkey not in last or r.datadate > last[r.gvkey][0]:
                last[r.gvkey] = (r.datadate, r.price, r.ajexdi, r.curcdd)
        ch["fye"] = ch.gvkey.map(fye)
        f = ch[(ch.dd <= ch.fye) & (ch.dd >= ch.fye - pd.Timedelta(days=10))].groupby("gvkey").tail(1)
        for r in f.itertuples(index=False):
            if r.gvkey not in atfye or r.datadate > atfye[r.gvkey][0]:
                atfye[r.gvkey] = (r.datadate, r.price, r.ajexdi)
    px = pd.concat(parts).sort_values(["gvkey","datadate"]); px.to_csv(CACHE / "prices_core.csv", index=False)
    pd.DataFrame([(k,)+v for k, v in last.items()], columns=["gvkey","datadate","price","ajexdi","curcdd"]).to_csv(CACHE / "last_price_all.csv", index=False)
    pd.DataFrame([(k,)+v for k, v in atfye.items()], columns=["gvkey","fye_price_date","price_fye","ajexdi_fye"]).to_csv(CACHE / "price_at_fye.csv", index=False)
    return px

def prices_core() -> pd.DataFrame:
    f = CACHE / "prices_core.csv"
    px = pd.read_csv(f, dtype={"gvkey": str}, parse_dates=["datadate"]) if (f.exists() and (CACHE / "price_at_fye.csv").exists()) else build_price_cache()
    px = px.dropna(subset=["price"]).copy(); px["datadate"] = pd.to_datetime(px.datadate)
    px["tri"] = px.price / px.ajexdi.fillna(1.0) * px.trfd.fillna(1.0)   # total-return index, local currency
    return px

def tri_wide() -> pd.DataFrame:
    px = prices_core()
    return px.pivot_table(index="datadate", columns="gvkey", values="tri").sort_index()

def indices() -> pd.DataFrame:
    i = pd.read_csv(DATA / "indices_daily.csv", parse_dates=["datadate"])
    w = i.pivot_table(index="datadate", columns="conm", values="prccd").sort_index()
    ren = {"Topix Index": "TOPIX", "Nikkei 225 Index": "NIKKEI", "CAC 40 Index": "CAC40", "Euro STOXX 50 Index": "STOXX50",
           "Deutscher Aktienindex (DAX) Index": "DAX", "Taiwan Weighted Index": "TAIEX", "FTSE 100 Index": "FTSE100"}
    return w.rename(columns=ren)[[c for c in ren.values() if c in w.rename(columns=ren).columns]]

def fx() -> pd.DataFrame:
    """Wide: units of currency per GBP. Derived crosses: USDJPY (JPY per USD), EURUSD (USD per EUR)."""
    f = pd.read_csv(DATA / "fx_daily.csv", parse_dates=["datadate"]).pivot_table(index="datadate", columns="tocurd", values="exratd").sort_index()
    f["GBP"] = 1.0
    f["USDJPY"] = f["JPY"] / f["USD"]; f["EURUSD"] = f["USD"] / f["EUR"]
    return f

def to_usd_rate(cur: str, fxw: pd.DataFrame, date=None) -> float:
    """USD per 1 unit of cur at the last date <= date."""
    row = fxw.loc[:date].iloc[-1] if date is not None else fxw.iloc[-1]
    if cur == "USD": return 1.0
    if cur not in row.index or pd.isna(row[cur]): return np.nan
    return float(row["USD"] / row[cur])

def copper_monthly() -> pd.Series:
    c = pd.read_csv(DATA / "external/fred_PCOPPUSDM_copper_monthly.csv", parse_dates=["observation_date"])
    return c.set_index("observation_date")["PCOPPUSDM"].astype(float)

def ecb_rate_daily() -> pd.Series:
    e = pd.read_csv(DATA / "external/fred_ECBDFR_ecb_deposit_rate_daily.csv", parse_dates=["observation_date"])
    return e.set_index("observation_date")["ECBDFR"].astype(float)

def semis_series(name: str) -> pd.Series:
    s = pd.read_csv(DATA / "external/semis_series.csv", parse_dates=["date"])
    s = s[s.series == name].sort_values("date")
    return s.groupby("date")["value"].last().astype(float)

# ---- Event dummies: public news and company-release dates collected by the macro agents (scenario write-ups not included).
# Signs are the analyst's ex-ante expectation [inference]; dates and labels are public events [source: news and company releases].
EVENTS_GRID = [  # (date, label, expected sign for Nexans)
 ("2024-12-05","DK offshore auction zero bids","-"), ("2024-12-25","Estlink 2 cut","+"), ("2025-01-20","US EO halts offshore wind leasing","-"),
 ("2025-01-31","ENTSO-E TYNDP 2024","+"), ("2025-05-07","Orsted cancels Hornsea 4","-"), ("2025-07-08","US 50% copper tariff announced","0/-"),
 ("2025-07-30","Refined copper excluded, Comex -20%","0/+"), ("2025-08-01","DE offshore round zero bids","-"), ("2025-08-11","Orsted rights issue","-"),
 ("2025-08-22","Revolution Wind stop-work","-"), ("2025-10-01","DOE terminates grid grants","-"), ("2025-10-23","Nexans 9M 2025 and CEO transition","co"),
 ("2025-12-10","EU Grids Package","+"), ("2025-12-22","Second US stop-work order","-"), ("2026-01-06","Nexans GSI rescheduling","-"),
 ("2026-01-12","Revolution Wind injunction","+"), ("2026-01-14","UK AR7 8.4 GW","+"), ("2026-01-15","LME copper record 14,527","0/-"),
 ("2026-01-28","DE suspends 2026 offshore auctions","-"), ("2026-02-19","Nexans FY2025 and 2026 guide","co"), ("2026-02-20","EC subsea cable security package","+"),
 ("2026-04-27","Republic Wire acquisition","co"), ("2026-05-28","IEA WEI 2026","+"), ("2026-06-08","Celtic Interconnector slips","0/-"),
 ("2026-06-11","ECB first hike 2.25%","-"), ("2026-07-29","Nexans H1 2026 guide raised","co"), ("2026-08-05","Meridiam takes 66% of GSI","+"),
 ("2026-09-08","LME copper record 14,533","0/-"), ("2026-09-10","ECB second hike 2.50%","-"), ("2026-10-06","Greece rejects Turkish demand, GSI survey restart","+"),
]
EVENTS_SEMIS = [  # (date, label, sign Organo, sign Japan Material, sign Shin-Etsu)
 ("2024-12-02","BIS SME/HBM/FDPR controls","0","0","-"), ("2025-01-13","US AI Diffusion rule","0","0","-"), ("2025-05-13","AI Diffusion rule rescinded","0","0","+"),
 ("2025-05-28","Japan FEFTA adds 21 items","0","0","-"), ("2025-09-29","Kioxia K2 starts; BIS Affiliates Rule","0","+","-"),
 ("2025-10-09","China rare earth/Ga/Ge controls","0","0","-"), ("2025-11-07","Takaichi Taiwan remarks","-","0","-"), ("2025-11-10","US-China one-year truce","0","0","+"),
 ("2025-12-03","Japan photoresist curb rumor","0","0","m"), ("2026-01-06","China dual-use ban on Japan","0","0","-"), ("2026-01-07","China anti-dumping probe","0","0","-"),
 ("2026-01-13","BIS China chip review rule","0","0","+"), ("2026-02-02","TrendForce 1Q26 NAND +55-60%","0","+","+"), ("2026-03-18","Micron FY26 capex USD 25bn","+","0","+"),
 ("2026-04-13","Rapidus JPY 631.5bn (11 Apr, Sat)","+","+","0"), ("2026-04-20","Tohoku earthquake 1","0","-","0"), ("2026-06-02","WSTS Spring forecast","+","+","+"),
 ("2026-06-25","Tohoku earthquake 2","0","-","0"), ("2026-07-28","Kumamoto M7.1 earthquake","-","-","0"), ("2026-07-31","Kioxia 1Q FY26 capex 470bn","0","+","0"),
 ("2026-09-30","TrendForce 4Q26 NAND +15-20%","0","+","+"), ("2026-10-01","Organo 5-for-1 split effective","co","0","0"),
]

if __name__ == "__main__":
    core = universe_core(); print(core.groupby("group").size()); print(core[core.case])
    px = prices_core(); print("prices_core rows", len(px), px.datadate.min(), px.datadate.max())
    print(px.groupby("gvkey").datadate.agg(["min","max","count"]).to_string())
    print(indices().tail(2).to_string()); print(fx().tail(2).to_string())
