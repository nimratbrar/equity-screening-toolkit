"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

red-stats audit, data prep (one chunked pass over daily_prices.csv) [WRDS data].
Writes data/scenario/cache/audit_country_ew.csv (equal-weight daily log-return index for USA and KOR names, used as the
market factor for US and Korean peers, which have no index in indices_daily.csv) and
data/scenario/cache/audit_price_20251016.csv (every gvkey's last price on or before 2025-10-16, for the multiple-reversion test).
Run: ~/.venvs/equity-screening-toolkit/bin/python methodology/scenario/audit_prep.py
"""
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]; DATA = ROOT / "data/scenario"; CACHE = DATA / "cache"
u = pd.read_csv(DATA / "universe.csv", dtype={"gvkey": str}); u["gvkey"] = u.gvkey.str.zfill(6)
loc = dict(zip(u.gvkey, u["loc"]))
keep = {g for g, l in loc.items() if l in ("USA", "KOR")}
parts, p25 = [], {}
for ch in pd.read_csv(DATA / "daily_prices.csv", dtype={"gvkey": str}, usecols=["gvkey", "datadate", "price", "ajexdi", "trfd", "curcdd"], chunksize=2_000_000):
    ch = ch.dropna(subset=["price"])
    parts.append(ch[ch.gvkey.isin(keep)])
    c = ch[ch.datadate <= "2025-10-16"].sort_values("datadate").groupby("gvkey").tail(1)
    for r in c.itertuples(index=False):
        if r.gvkey not in p25 or r.datadate > p25[r.gvkey][0]:
            p25[r.gvkey] = (r.datadate, r.price, r.ajexdi, r.curcdd)
px = pd.concat(parts).sort_values(["gvkey", "datadate"])
px["tri"] = px.price / px.ajexdi.fillna(1) * px.trfd.fillna(1)
px["r"] = np.log(px.tri).groupby(px.gvkey).diff().clip(-0.25, 0.25)
px["loc"] = px.gvkey.map(loc)
ew = px.dropna(subset=["r"]).groupby(["datadate", "loc"]).r.mean().unstack()
ew.to_csv(CACHE / "audit_country_ew.csv")
pd.DataFrame([(k,) + v for k, v in p25.items()], columns=["gvkey", "datadate", "price", "ajexdi", "curcdd"]).to_csv(CACHE / "audit_price_20251016.csv", index=False)
print(ew.describe().round(4).to_string(), len(p25))
