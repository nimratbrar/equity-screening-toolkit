"""Config-driven global company screen on Compustat North America + Compustat Global.

    python screen.py --config my_screen.json            # run, write ranked Excel + CSV + meta JSON
    python screen.py --config my_screen.json --dry-run  # validate config, no connection
    python screen.py --list-metrics                     # show built-in metrics

Pipeline use:
    from screen import run_screen
    result = run_screen(cfg_dict)   # returns dict(ranked=DataFrame, funnel=list, paths=dict)

All money values are converted to USD millions at the latest Compustat FX rate. Growth and margin
metrics are computed before conversion effects matter (same rate for every year), so they are local-currency.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wrds_client import WRDS, GICS_SECTORS, MONEY_COLS  # noqa: E402

warnings.simplefilter("ignore", pd.errors.PerformanceWarning)

LAG_VARS = ["sale", "cogs", "oibdp", "oiadp", "ni", "at", "ceq", "emp", "csho", "oancf", "capx"]
TAX_RATE = 0.21

# ---------------------------------------------------------------- metrics
def _div(a, b, pos_denom=True):
    a, b = pd.to_numeric(a, errors="coerce"), pd.to_numeric(b, errors="coerce")
    out = a / b.where(b > 0) if pos_denom else a / b.where(b != 0)
    return out.replace([np.inf, -np.inf], np.nan)


def _z(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)


def _avg(a, b):
    return pd.concat([a, b], axis=1).mean(axis=1)


METRICS = {
    # size
    "revenue": ("Revenue (USD mm)", lambda d: d["sale"]),
    "ebitda": ("EBITDA (USD mm)", lambda d: d["oibdp"]),
    "employees": ("Employees (thousands)", lambda d: d["emp"]),
    "market_cap": ("Market cap (USD mm, latest daily)", lambda d: d["market_cap"]),
    "enterprise_value": ("EV = mkt cap + debt + pref + minority - cash", lambda d: d["market_cap"] + d["net_debt"] + _z(d["pstk"]) + _z(d["mib"])),
    # growth
    "rev_growth_1y": ("Revenue growth, last FY", lambda d: _div(d["sale"], d["sale_l1"]) - 1),
    "rev_cagr_3y": ("Revenue CAGR, 3 FY", lambda d: _div(d["sale"], d["sale_l3"]) ** (1 / 3) - 1),
    "ebitda_growth_1y": ("EBITDA growth, last FY (positive base only)", lambda d: _div(d["oibdp"], d["oibdp_l1"]) - 1),
    "emp_growth_1y": ("Headcount growth, last FY", lambda d: _div(d["emp"], d["emp_l1"]) - 1),
    "share_change_1y": ("Change in shares outstanding (dilution > 0)", lambda d: _div(d["csho"], d["csho_l1"]) - 1),
    # profitability
    "gross_margin": ("Gross margin", lambda d: _div(d["sale"] - d["cogs"], d["sale"])),
    "ebitda_margin": ("EBITDA margin", lambda d: _div(d["oibdp"], d["sale"])),
    "ebit_margin": ("EBIT margin", lambda d: _div(d["oiadp"], d["sale"])),
    "net_margin": ("Net margin", lambda d: _div(d["ni"], d["sale"])),
    "ebitda_margin_chg_3y": ("EBITDA margin change vs 3 FY ago (pts)", lambda d: _div(d["oibdp"], d["sale"]) - _div(d["oibdp_l3"], d["sale_l3"])),
    "fcf": ("Free cash flow = CFO - capex (USD mm)", lambda d: d["oancf"] - _z(d["capx"])),
    "fcf_margin": ("FCF margin", lambda d: _div(d["oancf"] - _z(d["capx"]), d["sale"])),
    "fcf_conversion": ("FCF / net income", lambda d: _div(d["oancf"] - _z(d["capx"]), d["ni"])),
    "roa": ("Return on avg assets", lambda d: _div(d["ni"], _avg(d["at"], d["at_l1"]))),
    "roe": ("Return on avg common equity", lambda d: _div(d["ni"], _avg(d["ceq"], d["ceq_l1"]))),
    "roic": ("After-tax EBIT / invested capital", lambda d: _div(d["oiadp"] * (1 - TAX_RATE), d["invested_capital"])),
    "rule_of_40": ("Revenue growth + EBITDA margin", lambda d: (_div(d["sale"], d["sale_l1"]) - 1) + _div(d["oibdp"], d["sale"])),
    # intensity
    "rd_intensity": ("R&D / revenue", lambda d: _div(_z(d["xrd"]), d["sale"])),
    "capex_intensity": ("Capex / revenue", lambda d: _div(_z(d["capx"]), d["sale"])),
    "sga_intensity": ("SG&A / revenue", lambda d: _div(d["xsga"], d["sale"])),
    "asset_turnover": ("Revenue / avg assets", lambda d: _div(d["sale"], _avg(d["at"], d["at_l1"]))),
    "rev_per_employee": ("Revenue per employee (USD k)", lambda d: _div(d["sale"], d["emp"])),
    # balance sheet
    "net_debt": ("Debt - cash (USD mm)", lambda d: d["net_debt"]),
    "net_debt_to_ebitda": ("Net debt / EBITDA (NaN if EBITDA <= 0)", lambda d: _div(d["net_debt"], d["oibdp"])),
    "debt_to_equity": ("Total debt / common equity", lambda d: _div(d["total_debt"], d["ceq"])),
    "current_ratio": ("Current assets / current liabilities", lambda d: _div(d["act"], d["lct"])),
    "interest_coverage": ("EBIT / interest expense", lambda d: _div(d["oiadp"], d["xint"])),
    "cash_to_assets": ("Cash / assets", lambda d: _div(d["che"], d["at"])),
    # valuation (all in USD)
    "ev_to_sales": ("EV / revenue", lambda d: _div(d["enterprise_value"], d["sale"])),
    "ev_to_ebitda": ("EV / EBITDA", lambda d: _div(d["enterprise_value"], d["oibdp"])),
    "ev_to_ebit": ("EV / EBIT", lambda d: _div(d["enterprise_value"], d["oiadp"])),
    "pe": ("Market cap / net income", lambda d: _div(d["market_cap"], d["ni"])),
    "pb": ("Market cap / common equity", lambda d: _div(d["market_cap"], d["ceq"])),
    "fcf_yield": ("FCF / market cap", lambda d: _div(d["oancf"] - _z(d["capx"]), d["market_cap"])),
    "earnings_yield": ("Net income / market cap", lambda d: _div(d["ni"], d["market_cap"])),
    "dividend_yield": ("Common dividends / market cap", lambda d: _div(_z(d["dvc"]), d["market_cap"])),
}

ID_COLS = ["gvkey", "tic", "conm", "loc", "sector", "gsubind", "region", "fyear", "datadate", "px_date", "curcd"]
REGION_SETS = {"global": ["na", "intl"], "na": ["na"], "intl": ["intl"]}

DEFAULTS = {
    "name": "screen",
    "history_years": 5,
    "max_staleness_months": 18,
    "report_lag_days": 90,
    "region": "global",                  # global | na | intl
    "universe": {
        "countries": None,               # HQ country (comp loc), ISO-3 e.g. ["USA", "GBR", "DEU"]
        "incorporation_countries": None, # comp fic
        "currency": None,                # reporting currency filter, e.g. "EUR"
        "active_only": True,
        "exchanges": None,               # whitelist of comp exchg codes
        "exclude_exchanges": [0, 1, 2, 3, 4, 13, 19],   # non-traded / subsidiary / OTC
        "exclude_gsectors": [],
    },
    "filters": [],
    "custom_metrics": {},
    "extra_ratios": [],
    "scoring": {"metrics": [], "rank_within": None, "min_coverage": 0.6},
    "output": {"dir": "output", "top_n": 50, "columns": []},
}


def _merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in (over or {}).items():
        out[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return out


def validate(cfg: dict) -> list:
    """Return a list of problems (empty = OK)."""
    known = set(METRICS) | set(cfg.get("custom_metrics", {})) | {f"fr_{c}" for c in cfg.get("extra_ratios", [])}
    probs = []
    for f in cfg["filters"]:
        if f.get("metric") not in known and f.get("column") is None:
            probs.append(f"filter uses unknown metric: {f.get('metric')}")
    for m in cfg["scoring"]["metrics"]:
        if m.get("metric") not in known:
            probs.append(f"scoring uses unknown metric: {m.get('metric')}")
        if m.get("direction", "high") not in ("high", "low"):
            probs.append(f"direction must be high/low: {m}")
    return probs


# ---------------------------------------------------------------- data build
def _latest_annual(w: WRDS, region: str, start_year: int, cutoff: str) -> pd.DataFrame:
    """Latest fiscal year per gvkey for one region, with 1- and 3-year lags attached."""
    funda = w.fundamentals_annual(start_year=start_year, max_datadate=cutoff, region=region)
    funda = funda.dropna(subset=["fyear"])
    funda["_indl"] = (funda["indfmt"] == "INDL").astype(int)   # prefer INDL over FS
    funda = funda.sort_values(["gvkey", "fyear", "_indl", "datadate"])
    funda = funda.drop_duplicates(["gvkey", "fyear"], keep="last")
    funda["fyear"] = funda["fyear"].astype(int)
    df = funda.copy()
    for k in (1, 3):
        lag = funda[["gvkey", "fyear", "curcd"] + LAG_VARS].copy()
        lag["fyear"] += k
        lag = lag.rename(columns={v: f"{v}_l{k}" for v in LAG_VARS + ["curcd"]})
        df = df.merge(lag, on=["gvkey", "fyear"], how="left")
        # a change of reporting currency makes the lag incomparable
        changed = df[f"curcd_l{k}"].notna() & (df[f"curcd_l{k}"] != df["curcd"])
        df.loc[changed, [f"{v}_l{k}" for v in LAG_VARS]] = np.nan
    return df.sort_values(["gvkey", "datadate"]).groupby("gvkey", as_index=False).tail(1)


def build_dataset(w: WRDS, cfg: dict, as_of: date, funnel: list) -> pd.DataFrame:
    lag_days = cfg["report_lag_days"] if cfg.get("_as_of_given") else 0
    cutoff = str((pd.Timestamp(as_of) - pd.Timedelta(days=lag_days)).date())
    start_year = as_of.year - cfg["history_years"] - 1
    regions = REGION_SETS[cfg["region"]]

    parts = []
    for region in regions:
        f = _latest_annual(w, region, start_year, cutoff)
        f = f.merge(w.company_info(region=region).drop(columns=["conm", "cik"]), on="gvkey", how="left")
        mkt = w.latest_market_data(as_of=str(as_of), region=region).drop(columns=["region"])
        cfg["_vintage"][f"{region} price date"] = str(mkt["px_date"].max().date()) if len(mkt) else "none"
        parts.append(f.merge(mkt, on="gvkey", how="left"))
    df = pd.concat(parts, ignore_index=True)
    # Global tables carry no ticker; fall back to the price-file ticker, then the ISIN.
    df["tic"] = df["tic"].fillna(df["px_tic"]).fillna(df["px_isin"]).fillna(df.get("isin"))
    # A company present in both databases keeps its North America record.
    df = df.sort_values("region").drop_duplicates("gvkey", keep="first")
    funnel.append((f"Companies with annual data ({', '.join(regions)})", len(df)))

    # Staleness is measured from the newest fiscal year-end in the data, not a fixed date.
    latest_fund = df["datadate"].max()
    cfg["_vintage"]["latest fiscal year-end in data"] = str(latest_fund.date())
    fresh = latest_fund - pd.DateOffset(months=cfg["max_staleness_months"])
    df = df[df["datadate"] >= fresh]
    funnel.append((f"Latest FY ends within {cfg['max_staleness_months']} months", len(df)))

    # Convert money to USD at the latest FX rate (one rate for all years, so growth stays local-currency).
    fx = w.fx_to_usd(as_of=str(as_of))
    cfg["_vintage"]["FX rate date (g_exrt_dly)"] = fx.attrs.get("date", "")
    f_rate = df["curcd"].map(fx)
    money = [c for c in MONEY_COLS if c in df] + [f"{v}_l{k}" for k in (1, 3) for v in LAG_VARS
                                                  if v in MONEY_COLS and f"{v}_l{k}" in df]
    for c in money:
        df[c] = pd.to_numeric(df[c], errors="coerce") * f_rate
    df["market_cap"] = pd.to_numeric(df["market_cap"], errors="coerce") * df["curcdd"].map(fx)
    df["price_usd"] = pd.to_numeric(df["price"], errors="coerce") * df["curcdd"].map(fx)
    no_fx = f_rate.isna()
    if no_fx.any():
        df = df[~no_fx]
        funnel.append(("Reporting currency has an FX rate", len(df)))

    df["total_debt"] = _z(df["dltt"]) + _z(df["dlc"])
    df["net_debt"] = df["total_debt"] - _z(df["che"])
    df["invested_capital"] = df["total_debt"] + df["ceq"] + _z(df["pstk"]) + _z(df["mib"]) - _z(df["che"])
    for name, (_, fn) in METRICS.items():
        if name != "net_debt":
            df[name] = fn(df)

    for name, expr in cfg["custom_metrics"].items():
        df[name] = pd.to_numeric(df.eval(expr), errors="coerce").replace([np.inf, -np.inf], np.nan)

    if cfg["extra_ratios"]:   # WRDS Financial Ratios Suite covers US firms only; others get NaN
        fr = w.fin_ratios(columns=cfg["extra_ratios"])
        fr = fr[["gvkey", "public_date"] + cfg["extra_ratios"]]
        cfg["_vintage"]["wrdsapps_finratio (latest public_date)"] = str(fr["public_date"].max().date()) if len(fr) else "none"
        df = df.merge(fr.rename(columns={c: f"fr_{c}" for c in cfg["extra_ratios"]}), on="gvkey", how="left")
    return df.reset_index(drop=True)


def _text_match(series: pd.Series, words: list) -> pd.Series:
    pat = "|".join(re.escape(x) for x in words)
    return series.fillna("").str.contains(pat, case=False, regex=True)


def apply_universe(df: pd.DataFrame, u: dict, funnel: list) -> pd.DataFrame:
    def step(mask, label):
        nonlocal df
        df = df[mask.fillna(False)]
        funnel.append((label, len(df)))

    if u.get("active_only"):
        step(df["costat"] == "A", "Active (costat = A)")
    if u.get("countries"):
        step(df["loc"].isin(u["countries"]), f"HQ in {', '.join(u['countries'])}")
    if u.get("incorporation_countries"):
        step(df["fic"].isin(u["incorporation_countries"]), f"Incorporated in {', '.join(u['incorporation_countries'])}")
    if u.get("currency"):
        step(df["curcd"] == u["currency"], f"Reports in {u['currency']}")
    def exchg():
        return pd.to_numeric(df["exchg"], errors="coerce")
    step(exchg().notna(), "Has a current price (primary issue traded)")
    if u.get("exchanges"):
        step(exchg().isin(u["exchanges"]), "On listed exchanges")
    if u.get("exclude_exchanges"):
        step(~exchg().isin(u["exclude_exchanges"]), "Non-traded / OTC excluded")
    if u.get("include_gsectors"):
        step(df["gsector"].isin([str(s) for s in u["include_gsectors"]]), "GICS sector included")
    if u.get("exclude_gsectors"):
        step(~df["gsector"].isin([str(s) for s in u["exclude_gsectors"]]), "GICS sectors excluded")
    if u.get("gics_prefixes"):
        pre = tuple(str(p) for p in u["gics_prefixes"])
        step(df["gsubind"].fillna("").str.startswith(pre), "GICS code prefix match")
    if u.get("sic_ranges"):
        sic = pd.to_numeric(df["sic"], errors="coerce")
        m = pd.Series(False, index=df.index)
        for lo, hi in u["sic_ranges"]:
            m |= sic.between(lo, hi)
        step(m, "SIC range match")
    if u.get("naics_prefixes"):
        step(df["naics"].fillna("").str.startswith(tuple(str(p) for p in u["naics_prefixes"])), "NAICS prefix match")
    if u.get("keywords_any"):
        step(_text_match(df["busdesc"] + " " + df["conm"], u["keywords_any"]), "Business description keyword match")
    if u.get("keywords_none"):
        step(~_text_match(df["busdesc"] + " " + df["conm"], u["keywords_none"]), "Excluded keywords removed")
    if u.get("min_market_cap") is not None:
        step(df["market_cap"] >= u["min_market_cap"], f"Market cap >= USD {u['min_market_cap']:,}mm")
    if u.get("max_market_cap") is not None:
        step(df["market_cap"] <= u["max_market_cap"], f"Market cap <= USD {u['max_market_cap']:,}mm")
    if u.get("min_revenue") is not None:
        step(df["sale"] >= u["min_revenue"], f"Revenue >= USD {u['min_revenue']:,}mm")
    return df


def apply_filters(df: pd.DataFrame, filters: list, funnel: list) -> pd.DataFrame:
    for f in filters:
        col = f.get("metric") or f.get("column")
        s = df[col]
        m = pd.Series(True, index=df.index)
        parts = []
        if "min" in f:
            m &= s >= f["min"]; parts.append(f">= {f['min']}")
        if "max" in f:
            m &= s <= f["max"]; parts.append(f"<= {f['max']}")
        if "in" in f:
            m &= s.isin(f["in"]); parts.append(f"in {f['in']}")
        if "not_in" in f:
            m &= ~s.isin(f["not_in"]); parts.append(f"not in {f['not_in']}")
        if f.get("allow_missing"):
            m |= s.isna()
        df = df[m.fillna(False)]
        funnel.append((f"{col} {' and '.join(parts)}", len(df)))
    return df


def score(df: pd.DataFrame, sc: dict) -> pd.DataFrame:
    df = df.copy()
    metrics = sc.get("metrics", [])
    if not metrics:
        df["score"] = np.nan
        df["rank"] = range(1, len(df) + 1)
        return df
    group = sc.get("rank_within")
    wsum = pd.Series(0.0, index=df.index)
    acc = pd.Series(0.0, index=df.index)
    total_w = sum(float(m.get("weight", 1)) for m in metrics)
    for m in metrics:
        col, wt = m["metric"], float(m.get("weight", 1))
        asc = m.get("direction", "high") == "high"
        vals = df[col]
        if m.get("winsorize"):
            lo, hi = vals.quantile([m["winsorize"], 1 - m["winsorize"]])
            vals = vals.clip(lo, hi)
        pct = (vals.groupby(df[group]).rank(pct=True, ascending=asc) if group else vals.rank(pct=True, ascending=asc))
        df[f"pct_{col}"] = pct
        has = pct.notna()
        acc += pct.fillna(0) * wt
        wsum += has * wt
    df["score_coverage"] = wsum / total_w
    raw = (acc / wsum.replace(0, np.nan) * 100).astype("float64")
    df["score"] = raw.where(df["score_coverage"] >= sc.get("min_coverage", 0.6))
    df = df.sort_values("score", ascending=False, na_position="last")
    df["rank"] = df["score"].rank(ascending=False, method="min", na_option="keep")
    return df


# ---------------------------------------------------------------- output
def write_outputs(ranked: pd.DataFrame, cfg: dict, funnel: list, as_of: date) -> dict:
    out_dir = Path(cfg["output"]["dir"])
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    base = out_dir / f"{cfg['name']}_{stamp}"

    score_cols = [m["metric"] for m in cfg["scoring"]["metrics"]]
    filt_cols = [f.get("metric") or f.get("column") for f in cfg["filters"]]
    extra = cfg["output"].get("columns", [])
    cols = ["rank", "score"] + ID_COLS + ["px_isin", "market_cap", "revenue", "price_usd"]
    for c in score_cols + filt_cols + extra + list(cfg["custom_metrics"]) + [f"fr_{c}" for c in cfg["extra_ratios"]]:
        if c not in cols and c in ranked.columns:
            cols.append(c)
    cols += ["busdesc", "weburl"]
    view = ranked[[c for c in cols if c in ranked.columns]]
    top = view[view["score"].notna()].head(cfg["output"]["top_n"]) if score_cols else view.head(cfg["output"]["top_n"])

    xlsx = base.with_suffix(".xlsx")
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        top.to_excel(xw, sheet_name="Ranked", index=False)
        view.to_excel(xw, sheet_name="All passing", index=False)
        pd.DataFrame(funnel, columns=["Step", "Companies remaining"]).to_excel(xw, sheet_name="Funnel", index=False)
        defs = [(k, METRICS[k][0]) for k in METRICS] + [(k, f"custom: {v}") for k, v in cfg["custom_metrics"].items()]
        pd.DataFrame(defs, columns=["Metric", "Definition"]).to_excel(xw, sheet_name="Metric definitions", index=False)
        notes = pd.DataFrame([
            ("Screen", cfg["name"]), ("As of", str(as_of)), ("Generated", datetime.now().strftime("%Y-%m-%d %H:%M")),
            ("Region", cfg["region"]),
            ("Sources", "Compustat NA (funda, company, secd) and Compustat Global (g_funda, g_company, g_secd); "
                        "FX from g_exrt_dly" + ("; WRDS Financial Ratios Suite (US only)" if cfg["extra_ratios"] else "")),
            ("Units", "Money in USD millions at the latest FX rate; growth/margins in local currency; "
                      "ratios as decimals; score 0-100 (weighted percentile)"),
            *[(f"Data vintage: {k}", v) for k, v in cfg.get("_vintage", {}).items()],
            ("Config", json.dumps({k: v for k, v in cfg.items() if not k.startswith("_")})),
            ("License", "WRDS data: use only as your institution's licence allows (usually academic use). Do not redistribute."),
        ], columns=["Item", "Value"])
        notes.to_excel(xw, sheet_name="Notes", index=False)
        _format_workbook(xw.book)

    csv = base.with_suffix(".csv")
    ranked.drop(columns=[c for c in ranked.columns if c.startswith("_")], errors="ignore").to_csv(csv, index=False)
    meta = base.with_suffix(".meta.json")
    meta.write_text(json.dumps({
        "name": cfg["name"], "as_of": str(as_of), "generated": datetime.now().isoformat(timespec="seconds"),
        "data_vintage": cfg.get("_vintage", {}), "funnel": funnel, "n_passing": int(len(view)), "n_scored": int(view["score"].notna().sum()),
        "xlsx": str(xlsx), "csv": str(csv), "config": {k: v for k, v in cfg.items() if not k.startswith("_")},
    }, indent=1, default=str))
    return {"xlsx": str(xlsx), "csv": str(csv), "meta": str(meta)}


def _format_workbook(wb):
    from openpyxl.styles import Font, PatternFill
    pct_like = re.compile(r"(margin|growth|cagr|roa|roe|roic|yield|intensity|coverage$|change|rule_of_40|chg|pct_)")
    for ws in wb.worksheets:
        ws.freeze_panes = "A2"
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F3864")
        for col in ws.columns:
            header = str(col[0].value or "")
            width = min(max(len(header), *(len(str(c.value)) if c.value is not None else 0 for c in col[1:200])) + 2, 60)
            ws.column_dimensions[col[0].column_letter].width = max(width, 8)
            if ws.title in ("Ranked", "All passing"):
                fmt = None
                if pct_like.search(header) and header != "score_coverage":
                    fmt = "0.0%"
                elif header in ("score",):
                    fmt = "0.0"
                elif header in ("market_cap", "revenue", "ebitda", "fcf", "net_debt", "enterprise_value"):
                    fmt = "#,##0"
                elif header.startswith(("ev_", "pe", "pb", "net_debt_to", "debt_to", "current_ratio", "interest")):
                    fmt = "0.0x"
                if fmt:
                    for c in col[1:]:
                        c.number_format = fmt if fmt != "0.0x" else '0.0"x"'
        if ws.max_row > 1:
            ws.auto_filter.ref = ws.dimensions


# ---------------------------------------------------------------- entry points
def run_screen(config: dict, session: WRDS = None, as_of: str = None, refresh: bool = False,
               write: bool = True) -> dict:
    cfg = _merge(DEFAULTS, config)
    cfg["_as_of_given"] = as_of is not None
    cfg["_vintage"] = {}
    probs = validate(cfg)
    if probs:
        raise ValueError("Config problems:\n  " + "\n  ".join(probs))
    as_of_d = pd.Timestamp(as_of).date() if as_of else date.today()
    own = session is None
    w = session or WRDS(use_cache=not refresh)
    funnel = []
    try:
        df = build_dataset(w, cfg, as_of_d, funnel)
    finally:
        if own:
            w.close()
    dataset = df   # every company with metrics, before any filter (used for peer comparisons)
    df = apply_universe(df, cfg["universe"], funnel)
    df = apply_filters(df, cfg["filters"], funnel)
    ranked = score(df, cfg["scoring"])
    funnel.append(("Scored (enough metric coverage)", int(ranked["score"].notna().sum())))
    paths = write_outputs(ranked, cfg, funnel, as_of_d) if write else {}
    return {"ranked": ranked, "funnel": funnel, "paths": paths, "config": cfg, "dataset": dataset,
            "as_of": as_of_d}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", help="JSON screen config")
    ap.add_argument("--as-of", help="YYYY-MM-DD for a historical screen (fundamentals lagged by report_lag_days)")
    ap.add_argument("--refresh", action="store_true", help="ignore cache, re-query WRDS")
    ap.add_argument("--dry-run", action="store_true", help="validate config only; no connection")
    ap.add_argument("--list-metrics", action="store_true")
    ap.add_argument("--print-top", type=int, default=10, help="print the top N names (ticker, name, score)")
    a = ap.parse_args()

    if a.list_metrics:
        for k, (desc, _) in METRICS.items():
            print(f"{k:24s} {desc}")
        return
    if not a.config:
        ap.error("--config is required")
    config = json.loads(Path(a.config).read_text())
    if a.dry_run:
        cfg = _merge(DEFAULTS, config)
        probs = validate(cfg)
        print("Config OK" if not probs else "Problems:\n  " + "\n  ".join(probs))
        sys.exit(1 if probs else 0)

    res = run_screen(config, as_of=a.as_of, refresh=a.refresh)
    print("\nFunnel:")
    for label, n in res["funnel"]:
        print(f"  {n:>6,}  {label}")
    top = res["ranked"][res["ranked"]["score"].notna()].head(a.print_top)
    if len(top):
        print(f"\nTop {len(top)}:")
        for _, r in top.iterrows():
            print(f"  {int(r['rank']):>3}. {str(r['tic']):12s} {str(r['conm'])[:36]:36s} {str(r.get('loc', '')):3s} score {r['score']:.1f}")
    print("\nWrote:")
    for k, v in res["paths"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
