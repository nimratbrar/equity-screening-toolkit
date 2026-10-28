"""Screening + analysis pipeline: one command, one WRDS connection (one Duo push).

    ./setup.sh        # once: builds ~/.venvs/equity-screening-toolkit with uv (Python 3.12, pinned by uv.lock)
    UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run pipeline.py --config pipelines/quality_growth.json

Stages:
  1. Screen   global universe -> filters -> weighted score -> ranked list     (skill: screen.py)
  2. Analyze  top N names: 10y history, quarterly trend, price performance,
              peer comparison, analyst estimates, rule-based risks/strengths   (analysis.py)
  3. Report   output/<name>_<stamp>/: report.md, analysis.xlsx, screen xlsx/csv,
              dossiers/<ticker>.json (one per company, for later steps), run.json

The config is a screen config (see .claude/skills/wrds/references/screen_config.md) plus an
optional "analysis" block (defaults in analysis.DEFAULTS) and an optional "connectors" block (Capital IQ export,
user-entered industry figures; both off by default, see connectors/__init__.py). WRDS alone is enough to run.
Outputs stay local (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import analysis as an
from analysis import WRDS  # also puts the skill's scripts on sys.path
from screen import METRICS, _format_workbook, _merge, run_screen
from connectors import apply_connectors

PCT_COLS = re.compile(r"^(ret_|pct_|rev_|ttm_rev_growth|volatility|.*margin|.*growth|.*cagr|roic|roe|roa|"
                      r"percentile|vs_median|fcf_yield|share_change|eps_growth|revision|rd_intensity)")


# ---------------------------------------------------------------- formatting helpers
def _na(x) -> bool:
    return x is None or (isinstance(x, float) and np.isnan(x)) or x is pd.NaT


def pct(x, digits=1):
    return "n/a" if _na(x) else f"{x * 100:.{digits}f}%"


def mult(x):
    return "n/a" if _na(x) else f"{x:.1f}x"


def money(x):
    if _na(x):
        return "n/a"
    return f"${x / 1000:,.1f}bn" if abs(x) >= 1000 else f"${x:,.0f}mm"


def day(x):
    return "n/a" if _na(x) else str(pd.Timestamp(x).date())


def _json_safe(v):
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if _na(v):
        return None
    if isinstance(v, (pd.Timestamp, datetime)):
        return str(pd.Timestamp(v).date())
    if isinstance(v, np.generic):
        return v.item()
    return v


def _records(df: pd.DataFrame) -> list:
    return [_json_safe(r) for r in df.to_dict("records")]


def _table(headers: list, rows: list) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------- stage 2
def analyze(w: WRDS, res: dict, acfg: dict) -> dict:
    ranked, as_of = res["ranked"], res["as_of"]
    warnings = []
    if acfg.get("names"):   # watchlist mode: exactly these companies, taken from the unfiltered dataset
        ds = res["dataset"]
        want = [str(n).strip().upper() for n in acfg["names"]]
        key = ds["px_isin"].fillna(ds["tic"]).astype(str).str.upper()
        tick = ds["tic"].astype(str).str.upper()
        ptick = ds["px_tic"].astype(str).str.upper() if "px_tic" in ds else tick
        pos = {n: i for i, n in enumerate(want)}
        short = ds[key.isin(want) | tick.isin(want) | ptick.isin(want)].copy()
        short["_order"] = [pos.get(k, pos.get(t, pos.get(pt, 999)))
                           for k, t, pt in zip(key[short.index], tick[short.index], ptick[short.index])]
        short = short.sort_values("_order").drop(columns="_order")
        short["rank"], short["score"] = range(1, len(short) + 1), np.nan
        found = set(key[short.index]) | set(tick[short.index]) | set(ptick[short.index])
        missing = [n for n in want if n not in found]
        if missing:
            warnings.append("Not found in Compustat by ISIN or ticker: " + ", ".join(missing))
    else:
        scored = ranked[ranked["score"].notna()] if ranked["score"].notna().any() else ranked
        short = scored.head(acfg["top_n"]).copy()
    if short.empty:
        raise SystemExit("No companies to analyze. Loosen the filters (see the funnel) or check the names list.")
    fx = w.fx_to_usd(as_of=str(as_of))

    history = an.annual_history(w, short, fx, acfg["history_years"], as_of)
    quarters, q_sum = an.quarterly_trend(w, short, fx, as_of)
    prices = an.price_performance(w, short, fx, acfg["price_lookback_days"], as_of)
    peers, peer_sum = an.peer_comparison(res["dataset"], short, acfg)
    try:
        est = an.analyst_estimates(w, short, fx)
    except Exception as e:  # estimates are a nice-to-have; never fail the run on them
        est = pd.DataFrame(columns=["gvkey"])
        warnings.append(f"Analyst estimates skipped: {str(e).splitlines()[0][:150]}")

    summary = short
    for extra in (q_sum, prices, peer_sum, est):
        if len(extra):
            summary = summary.merge(extra, on="gvkey", how="left")
    if len(peers):
        wide = peers.pivot(index="gvkey", columns="metric")
        for field, suffix in (("peer_median", "median"), ("vs_median", "vs_median"), ("percentile", "percentile")):
            block = wide[field].copy()
            block.columns = [f"peer_{m}_{suffix}" for m in block.columns]
            summary = summary.merge(block.reset_index(), on="gvkey", how="left")

    # Valuation inputs in the reporting currency, so a price target can be built without re-deriving them.
    rate = summary["curcd"].map(fx)          # USD per 1 unit of reporting currency
    summary["fx_usd_per_local"] = rate
    summary["shares_mm"] = pd.to_numeric(summary["cshoc"], errors="coerce") / 1e6
    summary["price_local"] = summary["price"]
    for usd_col, new in (("market_cap", "market_cap_local"), ("enterprise_value", "ev_local"), ("net_debt", "net_debt_local"),
                         ("oibdp", "ebitda_local"), ("oiadp", "ebit_local"), ("dp", "da_local"), ("sale", "revenue_local"),
                         ("ni", "net_income_local"), ("capx", "capex_local")):
        summary[new] = pd.to_numeric(summary[usd_col], errors="coerce") / rate
    if "ebitda_fy1_usd" in summary:
        summary["ebitda_fy1_local"] = summary["ebitda_fy1_usd"] / rate

    latest_fy = pd.Timestamp(res["dataset"]["datadate"].max())
    risks, strengths = {}, {}
    for _, r in summary.iterrows():
        risks[r["gvkey"]], strengths[r["gvkey"]] = an.flags_for(r.to_dict(), acfg["flags"], latest_fy)
    summary["risk_count"] = summary["gvkey"].map(lambda g: len(risks[g]))
    summary["strength_count"] = summary["gvkey"].map(lambda g: len(strengths[g]))
    return {"summary": summary, "history": history, "quarters": quarters, "prices": prices, "peers": peers,
            "estimates": est, "risks": risks, "strengths": strengths, "warnings": warnings}


# ---------------------------------------------------------------- stage 3
def write_report(run_dir: Path, res: dict, a: dict, cfg: dict) -> Path:
    s = a["summary"]
    vintage = cfg.get("_vintage", {})
    L = [f"# {cfg['name']}: screening and analysis report", "",
         f"Generated {datetime.now():%Y-%m-%d %H:%M} | as of {res['as_of']} | region: {cfg['region']} | "
         f"{len(s)} companies analyzed", "",
         "Money is USD at the latest FX rate. Source: WRDS (Compustat, I/B/E/S)"
         + (f"; optional connectors: {'; '.join(a.get('connectors_used', []))}" if a.get("connectors_used") else "")
         + ". Licensed data: keep local, use only as your data licences allow.", "",
         "## Data vintage", ""]
    L += [f"- {k}: {v}" for k, v in vintage.items()] + [""]
    L += ["## Screen funnel", "", _table(["Companies left", "Step"], [(f"{n:,}", lab) for lab, n in res["funnel"]]), ""]

    L += ["## Shortlist", "", _table(
        ["#", "Ticker", "Company", "HQ", "Sector", "Mkt cap", "Score", "Rev CAGR 3y", "EBITDA margin", "ROIC",
         "EV/EBITDA", "12m return", "Risks"],
        [(i + 1, r["tic"], str(r["conm"]).title()[:32], r["loc"], r["sector"], money(r["market_cap"]),
          "n/a" if _na(r["score"]) else f"{r['score']:.0f}", pct(r["rev_cagr_3y"]), pct(r["ebitda_margin"]),
          pct(r["roic"]), mult(r["ev_to_ebitda"]), pct(r.get("ret_12m")), r["risk_count"])
         for i, (_, r) in enumerate(s.iterrows())]), ""]
    if a["warnings"]:
        L += ["**Warnings:** " + "; ".join(a["warnings"]), ""]

    L += ["## Company notes", ""]
    for i, (_, r) in enumerate(s.iterrows()):
        g = r["gvkey"]
        L += [f"### {i + 1}. {str(r['conm']).title()} ({r['tic']}) | {r['loc']} | {r['sector']}", ""]
        desc = str(r.get("busdesc") or "").strip()
        if desc:
            L += [desc[:450] + ("..." if len(desc) > 450 else ""), ""]
        L += [
            f"- **Size:** market cap {money(r['market_cap'])}, EV {money(r['enterprise_value'])}, "
            f"revenue {money(r['revenue'])} (FY ending {day(r['datadate'])}, reported in {r['curcd']})",
            f"- **Growth:** revenue {pct(r['rev_growth_1y'])} last FY, {pct(r['rev_cagr_3y'])} 3-year CAGR; "
            f"trailing 12 months {pct(r.get('ttm_rev_growth'))}, latest quarter {pct(r.get('rev_yoy_latest_q'))} "
            f"year on year (quarter ending {day(r.get('last_quarter'))})",
            f"- **Profitability:** gross margin {pct(r['gross_margin'])}, EBITDA margin {pct(r['ebitda_margin'])}, "
            f"FCF margin {pct(r['fcf_margin'])}, ROIC {pct(r['roic'])}",
            f"- **Balance sheet:** net debt {money(r['net_debt'])} ({mult(r['net_debt_to_ebitda'])} EBITDA), "
            f"share count change {pct(r['share_change_1y'])}",
            f"- **Valuation:** EV/EBITDA {mult(r['ev_to_ebitda'])} vs peer median "
            f"{mult(r.get('peer_ev_to_ebitda_median'))}; EV/sales {mult(r['ev_to_sales'])} vs "
            f"{mult(r.get('peer_ev_to_sales_median'))}; P/E {mult(r['pe'])}; FCF yield {pct(r['fcf_yield'])}",
            f"- **Peers:** {int(r['peer_count']) if not _na(r.get('peer_count')) else 0} companies at "
            f"{r.get('peer_level')} level. Largest: {r.get('largest_peers') or 'n/a'}",
            f"- **Price:** {pct(r.get('ret_1m'))} 1m, {pct(r.get('ret_3m'))} 3m, {pct(r.get('ret_6m'))} 6m, "
            f"{pct(r.get('ret_12m'))} 12m; {pct(r.get('pct_from_52w_high'))} from 52-week high; "
            f"volatility {pct(r.get('volatility_1y'), 0)}; about {money(r.get('adv_usd_mm'))} traded per day",
        ]
        L.append(f"- **Valuation inputs ({r['curcd']} mm, FY ending {day(r['datadate'])}; price in {r.get('curcdd')}):** "
                 f"shares {r['shares_mm']:,.1f}mm, price {r['price_local']:,.2f}, market cap {r['market_cap_local']:,.0f}, "
                 f"net debt {r['net_debt_local']:,.0f}, EV {r['ev_local']:,.0f}, EBITDA {r['ebitda_local']:,.0f}, "
                 f"EBIT {r['ebit_local']:,.0f}, D&A {r['da_local']:,.0f}, capex {r['capex_local']:,.0f}"
                 + ("" if _na(r.get("ebitda_fy1_local")) else f", FY1 consensus EBITDA {r['ebitda_fy1_local']:,.0f}"))
        if not _na(r.get("eps_fy1")):
            L.append(f"- **Estimates [I/B/E/S]:** FY1 EPS {r['eps_fy1']:.2f} {r.get('est_currency') or ''} "
                     f"({int(r['analysts'])} analysts), forward P/E {mult(r.get('forward_pe'))}, FY2 EPS growth "
                     f"{pct(r.get('eps_growth_fy2'))}; forward EV/EBITDA {mult(r.get('ev_to_ebitda_fwd'))}, "
                     f"FY1 sales vs last FY {pct(r.get('est_sales_growth_fy1'))}")
        L.append("")
        if a["strengths"][g]:
            L += ["**Strengths**", ""] + [f"- {x}" for x in a["strengths"][g]] + [""]
        if a["risks"][g]:
            L += ["**Risks to check**", ""] + [f"- {x}" for x in a["risks"][g]] + [""]

        h = a["history"][a["history"]["gvkey"] == g].tail(6)
        if len(h):
            L += [_table(["FY", "Revenue", "Growth", "Gross margin", "EBITDA margin", "FCF", "ROIC", "Net debt/EBITDA"],
                         [(int(x["fyear"]), money(x["revenue"]), pct(x["rev_growth"]), pct(x["gross_margin"]),
                           pct(x["ebitda_margin"]), money(x["fcf"]), pct(x["roic"]), mult(x["net_debt_to_ebitda"]))
                          for _, x in h.iterrows()]), ""]
        q = a["quarters"][a["quarters"]["gvkey"] == g].tail(6)
        if len(q):
            L += [_table(["Quarter ending", "Revenue", "YoY growth", "EBITDA margin"],
                         [(day(x["datadate"]), money(x["saleq"]), pct(x["rev_yoy_q"]), pct(x["ebitda_margin_q"]))
                          for _, x in q.iterrows()]), ""]
    path = run_dir / "report.md"
    path.write_text("\n".join(L))
    return path


def write_workbook(run_dir: Path, a: dict, cfg: dict) -> Path:
    s = a["summary"]
    lead = ["rank", "score", "tic", "conm", "loc", "sector", "market_cap", "risk_count", "strength_count"]
    keep = lead + [c for c in list(METRICS) + list(cfg.get("custom_metrics", {})) if c in s and c not in lead]
    keep += [c for c in s.columns if c.startswith(("ret_", "pct_", "ttm_", "rev_yoy", "peer_", "eps_", "forward_pe",
                                                   "analysts", "revision", "volatility", "adv_usd", "ebitda_margin_",
                                                   "ev_to_ebitda_fwd", "est_", "ebitda_fy1", "sales_fy1", "capiq_", "ind_"))
             and c not in keep]
    names = s.set_index("gvkey")[["tic", "conm"]]

    def named(df):
        return df.merge(names, left_on="gvkey", right_index=True, how="left") if len(df) else df

    flags = pd.DataFrame(
        [(names.loc[g, "tic"], names.loc[g, "conm"], kind, text)
         for kind, src in (("Risk", a["risks"]), ("Strength", a["strengths"])) for g, items in src.items()
         for text in items], columns=["tic", "conm", "type", "note"])
    path = run_dir / "analysis.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        s[[c for c in keep if c in s]].to_excel(xw, sheet_name="Summary", index=False)
        vcols = ["tic", "conm", "loc", "curcd", "curcdd", "datadate", "px_date", "fx_usd_per_local", "shares_mm", "price_local",
                 "market_cap_local", "net_debt_local", "ev_local", "revenue_local", "ebitda_local", "ebit_local", "da_local",
                 "capex_local", "net_income_local", "ebitda_fy1_local", "ev_to_ebitda", "ev_to_ebitda_fwd", "pe", "forward_pe",
                 "eps_fy1", "eps_fy2", "est_currency", "analysts", "market_cap", "enterprise_value", "roic", "adv_usd_mm"]
        s[[c for c in vcols if c in s]].to_excel(xw, sheet_name="Valuation inputs", index=False)
        flags.to_excel(xw, sheet_name="Risks and strengths", index=False)
        named(a["history"]).to_excel(xw, sheet_name="Annual history", index=False)
        named(a["quarters"]).to_excel(xw, sheet_name="Quarterly", index=False)
        named(a["peers"]).to_excel(xw, sheet_name="Peer comparison", index=False)
        named(a["prices"]).to_excel(xw, sheet_name="Price performance", index=False)
        if len(a["estimates"]):
            named(a["estimates"]).to_excel(xw, sheet_name="Estimates", index=False)
        _format_workbook(xw.book)
        for ws in xw.book.worksheets:
            for col in ws.columns:
                if PCT_COLS.match(str(col[0].value or "")):
                    for c in col[1:]:
                        c.number_format = "0.0%"
    return path


def write_dossiers(run_dir: Path, a: dict, cfg: dict) -> Path:
    """One JSON per company holding everything the pipeline knows about it, for later analysis steps."""
    d = run_dir / "dossiers"
    d.mkdir(exist_ok=True)
    for _, r in a["summary"].iterrows():
        g = r["gvkey"]
        row = {k: v for k, v in r.to_dict().items() if not k.startswith("_")}
        name = re.sub(r"[^A-Za-z0-9]+", "_", str(r["tic"] if not _na(r["tic"]) else g)).strip("_")
        (d / f"{name}.json").write_text(json.dumps({
            "screen": cfg["name"], "gvkey": g, "company": r["conm"], "ticker": r["tic"],
            "summary": _json_safe(row),
            "strengths": a["strengths"][g], "risks": a["risks"][g],
            "annual_history": _records(a["history"][a["history"]["gvkey"] == g]),
            "quarters": _records(a["quarters"][a["quarters"]["gvkey"] == g]),
            "peer_comparison": _records(a["peers"][a["peers"]["gvkey"] == g]) if len(a["peers"]) else [],
        }, indent=1))
    return d


# ---------------------------------------------------------------- orchestration
def run_pipeline(config: dict, as_of: str = None, refresh: bool = False, top_n: int = None,
                 session: WRDS = None) -> dict:
    acfg = _merge(an.DEFAULTS, config.get("analysis", {}))
    if top_n:
        acfg["top_n"] = top_n
    name = config.get("name", "screen")
    run_dir = Path(config.get("output", {}).get("dir", "output")) / f"{name}_{datetime.now():%Y%m%d_%H%M}"
    run_dir.mkdir(parents=True, exist_ok=True)
    screen_cfg = {k: v for k, v in config.items() if k not in ("analysis", "connectors")}
    screen_cfg["output"] = dict(config.get("output", {}), dir=str(run_dir))

    w = session or WRDS(use_cache=not refresh)
    try:
        print(f"[pipeline] {name}: stage 1/3 screening", file=sys.stderr, flush=True)
        res = run_screen(screen_cfg, session=w, as_of=as_of)
        what = f"{len(acfg['names'])} named companies" if acfg.get("names") else f"top {acfg['top_n']}"
        print(f"[pipeline] {name}: stage 2/3 analyzing {what}", file=sys.stderr, flush=True)
        a = analyze(w, res, acfg)
        a["summary"], a["connectors_used"] = apply_connectors(a["summary"], config.get("connectors"), a["warnings"])
    finally:
        if session is None:
            w.close()

    print(f"[pipeline] {name}: stage 3/3 writing outputs", file=sys.stderr, flush=True)
    cfg = res["config"]
    paths = dict(res["paths"])
    paths["report"] = str(write_report(run_dir, res, a, cfg))
    paths["analysis_xlsx"] = str(write_workbook(run_dir, a, cfg))
    paths["dossiers"] = str(write_dossiers(run_dir, a, cfg))
    manifest = {
        "name": name, "as_of": str(res["as_of"]), "generated": datetime.now().isoformat(timespec="seconds"),
        "data_vintage": cfg.get("_vintage", {}), "funnel": res["funnel"], "warnings": a["warnings"],
        "shortlist": [{"rank": i + 1, "ticker": r["tic"], "company": r["conm"], "gvkey": r["gvkey"],
                       "score": _json_safe(r["score"]), "risks": a["risks"][r["gvkey"]],
                       "strengths": a["strengths"][r["gvkey"]]}
                      for i, (_, r) in enumerate(a["summary"].iterrows())],
        "paths": paths, "analysis_config": acfg, "connectors_used": a.get("connectors_used", []),
    }
    (run_dir / "run.json").write_text(json.dumps(_json_safe(manifest), indent=1, default=str))
    paths["manifest"] = str(run_dir / "run.json")
    return {"run_dir": run_dir, "paths": paths, "screen": res, "analysis": a, "manifest": manifest}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", required=True, nargs="+",
                    help="one or more pipeline config JSON files; they share one WRDS connection (one Duo push)")
    ap.add_argument("--as-of", help="YYYY-MM-DD for a historical run")
    ap.add_argument("--top-n", type=int, help="override analysis.top_n")
    ap.add_argument("--refresh", action="store_true", help="ignore the cache and re-query WRDS")
    a = ap.parse_args()

    with WRDS(use_cache=not a.refresh) as w:
        for cfg_path in a.config:
            out = run_pipeline(json.loads(Path(cfg_path).read_text()), as_of=a.as_of, refresh=a.refresh,
                               top_n=a.top_n, session=w)
            print(f"\n===== {out['manifest']['name']} =====\nFunnel:")
            for label, n in out["screen"]["funnel"]:
                print(f"  {n:>6,}  {label}")
            print("\nCompanies analyzed:")
            for x in out["manifest"]["shortlist"]:
                score = "" if x["score"] is None else f"score {x['score']:.0f}"
                print(f"  {x['rank']:>2}. {str(x['ticker']):12s} {str(x['company'])[:34]:34s} {score:9s} "
                      f"{len(x['strengths'])} strengths, {len(x['risks'])} risks")
            for wmsg in out["manifest"]["warnings"]:
                print(f"\nWarning: {wmsg}")
            print(f"\nOutputs in {out['run_dir']}/")
            for k, v in out["paths"].items():
                print(f"  {k}: {Path(v).name}")


if __name__ == "__main__":
    main()
