"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Data layer for the scenario scripts: prices, indices, FX and fundamentals for the 4 cases and their peers.

    UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run methodology/scenario/pull_data.py

One WRDS session. Writes CSVs to data/scenario/ (git-ignored). All windows are anchored on the latest
date present in each table (no hard-coded dates).
"""
import glob, json, sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / ".claude/skills/wrds/scripts"))
from wrds_client import WRDS  # noqa: E402

OUT = ROOT / "data/scenario"; OUT.mkdir(parents=True, exist_ok=True)
YEARS_PRICES, YEARS_FUND = 6, 12

# Universe: latest run of each peer group
names = []
for g in ("cable_grid", "fab_water_facility", "chip_materials_and_chem"):
    d = sorted(glob.glob(str(ROOT / f"output/peers_{g}_2026*")))[-1]
    csv = sorted(glob.glob(f"{d}/peers_{g}_*.csv"))[-1]
    s = pd.read_csv(csv, dtype={"gvkey": str}, low_memory=False)[["gvkey", "conm", "tic", "loc", "region", "curcd", "gsubind"]]
    s["group"] = g; names.append(s)
uni = pd.concat(names).drop_duplicates("gvkey").reset_index(drop=True)
uni["gvkey"] = uni["gvkey"].str.zfill(6)
uni.to_csv(OUT / "universe.csv", index=False)
print(f"universe: {len(uni)} companies")

with WRDS() as w:
    fresh = w.freshness(["comp.secd", "comp_global_daily.g_secd", "comp.fundq", "comp_global_daily.g_funda"])
    print("freshness:", fresh)
    # daily prices by region
    px = []
    for region in ("na", "intl"):
        g = uni[uni.region == region]["gvkey"].tolist()
        if g:
            px.append(w.daily_prices(g, lookback_days=365 * YEARS_PRICES, region=region).assign(region=region))
    px = pd.concat(px); px.to_csv(OUT / "daily_prices.csv", index=False); print("daily prices rows:", len(px))

    # indices: discover what exists, then pull daily values
    idx_cols = w.table_columns("comp_global_daily.g_idx_index")
    print("g_idx_index cols:", idx_cols)
    idx = w.sql("select * from comp_global_daily.g_idx_index", cache=False)
    namecol = next(c for c in idx.columns if "name" in c.lower() or c.lower() in ("conm", "indexname"))
    want = r"topix|nikkei 225|cac 40|stoxx europe 600|euro stoxx 50|s&p 500|kospi|taiex|taiwan weighted|philadelphia semiconductor|sox|msci world|msci acwi|dax|ftse 100|nasdaq composite"
    sel = idx[idx[namecol].astype(str).str.contains(want, case=False, regex=True, na=False)]
    sel.to_csv(OUT / "indices_list.csv", index=False); print("indices matched:", len(sel))
    keycol = "gvkeyx" if "gvkeyx" in idx.columns else idx.columns[0]
    dcols = w.table_columns("comp_global_daily.g_idx_daily")
    end = w.latest_date("comp_global_daily.g_idx_daily", "datadate")
    vals = w.sql(f"select * from comp_global_daily.g_idx_daily where {keycol} in %(k)s and datadate >= %(d0)s",
                 {"k": tuple(sel[keycol].astype(str)), "d0": str((end - pd.DateOffset(years=YEARS_PRICES)).date())}, cache=False)
    vals = vals.merge(sel[[keycol, namecol]], on=keycol, how="left")
    vals.to_csv(OUT / "indices_daily.csv", index=False); print("index rows:", len(vals), "cols:", dcols[:12])

    # FX daily (vs GBP; USD per X = USD/X)
    fend = w.latest_date("comp_global_daily.g_exrt_dly")
    fx = w.sql("select datadate, tocurd, exratd from comp_global_daily.g_exrt_dly where fromcurd='GBP' and tocurd in %(c)s and datadate >= %(d0)s",
               {"c": ("USD", "JPY", "EUR", "KRW", "TWD", "DKK", "SEK", "CNY"), "d0": str((fend - pd.DateOffset(years=YEARS_PRICES)).date())}, cache=False)
    fx.to_csv(OUT / "fx_daily.csv", index=False); print("fx rows:", len(fx))

    # fundamentals: annual (long) and quarterly, both regions
    ann, qtr = [], []
    for region in ("na", "intl"):
        g = uni[uni.region == region]["gvkey"].tolist()
        if not g: continue
        ann.append(w.fundamentals_annual(start_year=end.year - YEARS_FUND, gvkeys=g, region=region))
        qtr.append(w.fundamentals_quarterly(start_date=str((end - pd.DateOffset(years=YEARS_FUND)).date()), gvkeys=g, region=region).assign(region=region))
    pd.concat(ann).to_csv(OUT / "fundamentals_annual.csv", index=False)
    q = pd.concat(qtr); q.to_csv(OUT / "fundamentals_quarterly.csv", index=False)
    print("annual rows:", sum(len(a) for a in ann), "quarterly rows:", len(q))
    json.dump({"freshness": fresh, "pulled": str(pd.Timestamp.now())[:16]}, open(OUT / "meta.json", "w"), indent=1)
print("DATA LAYER DONE ->", OUT)
