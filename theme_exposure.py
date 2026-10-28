"""Theme exposure discovery: which listed companies (market cap >= $1B by default, any country) are exposed to each
theme in a themes file, how exposed, and how crowded they are.

    UV_PROJECT_ENVIRONMENT=~/.venvs/equity-screening-toolkit uv run theme_exposure.py [--themes examples/themes_security_resilience.json] [--min-cap 1000]

Write your own themes file with the same keys (see examples/); the example set covers grid equipment, cables, water,
semiconductor materials and similar resilience themes.

Combines, in one WRDS session (one Duo push):
  - the screen's global dataset (Compustat NA + Global, USD, ~40 metrics per company)
  - Compustat business segments   -> share of sales in theme segments, segment growth and margin
  - Compustat geographic segments -> US and China share of sales
  - Compustat customer segments   -> second-order suppliers of anchor companies
  - I/B/E/S US + international    -> number of analysts (a crowding proxy)
Companies without segment data (most non-US firms) are caught by business-description keywords and
GICS codes and flagged as "no segment data".

Writes output/theme_exposure_<stamp>/<theme>.csv (+ suppliers CSVs) and a compact summary for the
research agents at research/data_notes/theme_exposure.md. Outputs stay local (git-ignored).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", message="This pattern is interpreted as a regular expression")
warnings.simplefilter("ignore", DeprecationWarning)

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / ".claude" / "skills" / "wrds" / "scripts"))
from wrds_client import WRDS  # noqa: E402
from screen import run_screen, _div  # noqa: E402

US_RX = r"united states|u\.s\.|^us$|^usa$|domestic|north america|americas"
CHINA_RX = r"china|prc|hong kong|greater china"
SHOW = ["tic", "conm", "loc", "sector", "gsubind", "market_cap", "core", "is_utility", "seg_share", "matched_segments", "seg_growth",
        "seg_margin", "match_basis", "rev_cagr_3y", "rev_growth_1y", "ebitda_margin", "roic", "net_debt_to_ebitda",
        "ev_to_ebitda", "capex_to_da", "analysts", "us_share", "china_share", "named_customers", "gvkey"]


def _latest_per_firm(seg: pd.DataFrame) -> tuple:
    """(latest-period rows, prior-year rows) using BUSSEG where a firm has it, else OPSEG."""
    seg = seg[seg["sales"].notna() & (seg["sales"] > 0)].copy()
    has_bus = seg.loc[seg["stype"] == "BUSSEG", "gvkey"].unique()
    seg = seg[(seg["stype"] == "BUSSEG") | ~seg["gvkey"].isin(has_bus)]
    last = seg.groupby("gvkey")["datadate"].transform("max")
    cur = seg[seg["datadate"] == last]
    prev = seg[(seg["datadate"] < last) & (seg["datadate"] >= last - pd.Timedelta(days=400))]
    return cur, prev


def segment_exposure(seg: pd.DataFrame, theme: dict) -> pd.DataFrame:
    """Per company: share of segment sales in theme-matching segments, plus growth and margin of those."""
    cur, prev = _latest_per_firm(seg)
    rx = re.compile(theme["segment_regex"], re.I)
    naics = tuple(theme.get("segment_naics", []))
    ex = re.compile(theme["segment_exclude"], re.I) if theme.get("segment_exclude") else None

    def hit(d):
        by_name = d["snms"].fillna("").map(lambda x: bool(rx.search(x)))
        by_code = d["naicss1"].fillna("").astype(str).str.startswith(naics) if naics else False
        keep = ~d["snms"].fillna("").map(lambda x: bool(ex.search(x))) if ex else True
        return (by_name | by_code) & keep

    cur = cur.assign(hit=hit(cur))
    total = cur.groupby("gvkey")["sales"].sum().rename("seg_total")
    m = cur[cur["hit"]]
    if m.empty:
        return pd.DataFrame(columns=["gvkey", "seg_share", "matched_segments", "seg_growth", "seg_margin", "seg_date"])
    g = m.groupby("gvkey")
    out = pd.DataFrame({
        "seg_sales": g["sales"].sum(), "seg_ops": g["ops"].sum(min_count=1),
        "matched_segments": g["snms"].agg(lambda x: "; ".join(sorted(set(map(str, x)))[:4])),
        "seg_date": g["datadate"].max(),
    }).join(total)
    out["seg_share"] = (out["seg_sales"] / out["seg_total"]).clip(upper=1.0)
    out["seg_margin"] = _div(out["seg_ops"], out["seg_sales"])
    p = prev.merge(m[["gvkey", "sid"]].drop_duplicates(), on=["gvkey", "sid"])
    p = p.sort_values("datadate").drop_duplicates(["gvkey", "sid"], keep="last").groupby("gvkey")["sales"].sum()
    out["seg_growth"] = _div(out["seg_sales"], p.reindex(out.index)) - 1
    return out.reset_index()[["gvkey", "seg_share", "matched_segments", "seg_growth", "seg_margin", "seg_date"]]


def geo_shares(geo: pd.DataFrame) -> pd.DataFrame:
    geo = geo[geo["sales"].notna() & (geo["sales"] > 0)].copy()
    last = geo.groupby("gvkey")["datadate"].transform("max")
    geo = geo[geo["datadate"] == last]
    name = geo["snms"].fillna("")
    geo["us"] = np.where(name.str.contains(US_RX, case=False, regex=True), geo["sales"], 0.0)
    geo["cn"] = np.where(name.str.contains(CHINA_RX, case=False, regex=True), geo["sales"], 0.0)
    g = geo.groupby("gvkey")[["sales", "us", "cn"]].sum()
    return pd.DataFrame({"gvkey": g.index, "us_share": (g["us"] / g["sales"]).clip(upper=1).values,
                         "china_share": (g["cn"] / g["sales"]).clip(upper=1).values})


def analyst_counts(w: WRDS, data: pd.DataFrame) -> tuple:
    """Number of FY1 EPS analysts per gvkey: US by 8-char CUSIP, international by SEDOL.

    The identifier format in ibes.statsum_epsint is checked against the data: every plausible
    key form is tried and the one that links the most companies is used.
    """
    us = w.ibes_consensus(fpi="1")[["cusip", "numest"]].dropna()
    a = data[["gvkey", "cusip"]].dropna().assign(k=lambda d: d["cusip"].astype(str).str[:8])
    us_n = a.merge(us, left_on="k", right_on="cusip")[["gvkey", "numest"]]

    intl = w.ibes_consensus(fpi="1", international=True)[["cusip", "numest"]].dropna()
    intl["cusip"] = intl["cusip"].astype(str).str.strip().str.upper()
    b = data[["gvkey", "px_sedol"]].dropna().assign(s=lambda d: d["px_sedol"].astype(str).str.strip().str.upper())
    forms = {"full": lambda x: x, "last7": lambda x: x.str[-7:], "first7": lambda x: x.str[:7],
             "last6": lambda x: x.str[-6:], "first6": lambda x: x.str[:6]}
    best, best_n, best_name = None, -1, ""
    for iname, f in forms.items():
        for sname, h in (("sedol7", lambda x: x.str[:7]), ("sedol6", lambda x: x.str[:6])):
            m = b.assign(k=h(b["s"])).merge(intl.assign(k=f(intl["cusip"])), on="k")
            n = m["gvkey"].nunique()
            if n > best_n:
                best, best_n, best_name = m, n, f"ibes {iname} = {sname}"
    intl_n = best[["gvkey", "numest"]] if best is not None else pd.DataFrame(columns=["gvkey", "numest"])
    out = pd.concat([us_n, intl_n]).groupby("gvkey")["numest"].max().rename("analysts").reset_index()
    note = (f"I/B/E/S link: {us_n['gvkey'].nunique():,} US-table matches by CUSIP; "
            f"{best_n:,} international matches by SEDOL ({best_name}) out of {len(b):,} companies with a SEDOL")
    return out, note


def build(w: WRDS, themes: dict, min_cap: float) -> dict:
    print("[theme] loading global dataset", file=sys.stderr, flush=True)
    res = run_screen({"name": "theme_base", "custom_metrics": {"capex_to_da": "capx / dp"},
                      "universe": {"min_market_cap": min_cap}}, session=w, write=False)
    data = res["ranked"].copy()
    print("[theme] segments, geography, customers, analyst coverage", file=sys.stderr, flush=True)
    seg = w.segments(stypes=("BUSSEG", "OPSEG"))
    geo = geo_shares(w.segments(stypes=("GEOSEG",)))
    cust = w.customers()
    analysts, link_note = analyst_counts(w, data)
    n_cust = cust[cust["ctype"].fillna("").str.upper().eq("COMPANY")].groupby("gvkey")["cnms"].nunique() \
        .rename("named_customers").reset_index()
    data = data.merge(geo, on="gvkey", how="left").merge(analysts, on="gvkey", how="left") \
               .merge(n_cust, on="gvkey", how="left")
    has_seg = set(seg["gvkey"].unique())
    desc = (data["busdesc"].fillna("") + " " + data["conm"].fillna(""))

    out = {"themes": {}, "suppliers": {}, "funnel": res["funnel"], "vintage": res["config"].get("_vintage", {}),
           "link_note": link_note, "n_universe": len(data), "n_with_segments": int(data["gvkey"].isin(has_seg).sum()),
           "seg_latest": str(seg["datadate"].max().date()) if len(seg) else "none"}
    for name, t in themes.items():
        if name.startswith("_"):
            continue
        ex = segment_exposure(seg, t)
        d = data.merge(ex, on="gvkey", how="left")
        d["busdesc_match"] = desc.str.contains(t["busdesc_regex"], case=False, regex=True).values
        core = tuple(t.get("gics_core", []))
        d["gics_match"] = d["gsubind"].fillna("").astype(str).str.startswith(core).values if core else False
        d["name_match"] = (d["conm"].fillna("").str.contains(t["include_names"], case=False, regex=True)
                           if t.get("include_names") else False)
        d["has_segment_data"] = d["gvkey"].isin(has_seg)
        d["is_utility"] = d["gsector"].astype(str).eq("55")
        d = d[(d["seg_share"] > 0) | d["busdesc_match"] | d["gics_match"] | d["name_match"]].copy()
        d["match_basis"] = np.select(
            [d["seg_share"] > 0, d["gics_match"] | d["name_match"], d["busdesc_match"]],
            ["segment", "GICS or name (exposure share unverified)", "description only (exposure unverified)"], "")
        # Core group: strong evidence of theme exposure, utilities kept separate from suppliers.
        d["core"] = ((d["seg_share"] >= 0.5) | d["gics_match"] | d["name_match"]) & ~d["is_utility"]
        out["themes"][name] = d.sort_values(["seg_share", "market_cap"], ascending=False, na_position="last")

        rx = t.get("anchor_customers")
        if rx:
            c = cust[cust["cnms"].str.contains(rx, case=False, regex=True, na=False)]
            c = c.sort_values("datadate").drop_duplicates(["gvkey", "cnms"], keep="last")
            c = c.merge(data[["gvkey", "tic", "conm", "loc", "sector", "market_cap", "revenue", "analysts"]], on="gvkey")
            c["share_of_supplier_sales"] = _div(c["salecs"], c["revenue"])
            out["suppliers"][name] = c.sort_values("market_cap", ascending=False)
    return out


def _fmt(v, kind):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return ""
    return {"pct": f"{v * 100:.0f}%", "x": f"{v:.1f}x", "bn": f"{v / 1000:.1f}", "n": f"{v:.0f}"}[kind]


def summarize(out: dict, themes: dict, min_cap: float) -> str:
    L = ["# Theme exposure from WRDS data", "",
         f"Generated {datetime.now():%Y-%m-%d %H:%M}. All numbers here are [WRDS data] unless marked otherwise.",
         f"Universe: {out['n_universe']:,} active, traded companies worldwide with market cap >= ${min_cap:,.0f}mm "
         f"(Compustat NA + Global, USD). {out['n_with_segments']:,} of them report business segments "
         f"(latest segment period {out['seg_latest']}); the rest are matched on business description only.",
         out["link_note"] + ".", "",
         "Columns: share = theme segments' share of segment sales; seg growth = year-on-year sales growth of those "
         "segments; analysts = number of FY1 EPS estimates (blank = no I/B/E/S link, common outside the US); "
         "US% / China% = share of sales from geographic segments. Money in USD bn.", ""]
    for name, d in out["themes"].items():
        t = themes[name]
        segd = d[d["match_basis"] == "segment"]
        core, util = d[d["core"]], d[d["is_utility"]]
        pure = segd[(segd["seg_share"] >= 0.5) & ~segd["is_utility"]]
        minor = segd[(segd["seg_share"] < 0.5) & ~segd["is_utility"]]
        nonus = d[d["loc"] != "USA"]
        n_basis = d["match_basis"].str.split(" (", regex=False).str[0].value_counts().to_dict()
        L += [f"## {name} ({t['sub_theme']})", "",
              f"- Companies matched: {len(d)} ({', '.join(f'{v} by {k}' for k, v in n_basis.items())}). "
              f"Non-US HQ: {len(nonus)}. Utilities among them: {len(util)}.",
              f"- **Core group** (segment share >= 50%, core GICS code, or named company; utilities excluded): "
              f"{len(core)} companies, {int((core['loc'] != 'USA').sum())} non-US. Use this group for comparisons; "
              "description-only matches are noisy."]

        def med(g, label):
            if len(g) < 5:
                return f"- {label}: n={len(g)} (too few for medians)"
            m = g[["rev_cagr_3y", "ebitda_margin", "roic", "ev_to_ebitda", "analysts", "capex_to_da"]].median()
            n_ev = int(g["ev_to_ebitda"].notna().sum())
            return (f"- {label} (n={len(g)}, EV/EBITDA available for {n_ev}): median rev CAGR 3y {_fmt(m['rev_cagr_3y'], 'pct')}, "
                    f"EBITDA margin {_fmt(m['ebitda_margin'], 'pct')}, ROIC {_fmt(m['roic'], 'pct')}, EV/EBITDA "
                    f"{_fmt(m['ev_to_ebitda'], 'x')}, analysts {_fmt(m['analysts'], 'n')}, capex/D&A {_fmt(m['capex_to_da'], 'x')}")

        L += [med(core, "Core group, all"), med(core[core["loc"] == "USA"], "Core group, US HQ"),
              med(core[core["loc"] != "USA"], "Core group, non-US HQ"),
              med(pure, "Segment pure plays (share >= 50%), ex utilities"),
              med(minor, "Theme is a minority segment (share < 50%), ex utilities"),
              med(util, "Utilities (shown separately)"), ""]
        by = core.groupby("loc").agg(n=("gvkey", "size"), ev=("ev_to_ebitda", "median"), an=("analysts", "median"),
                                     g=("rev_cagr_3y", "median"), roic=("roic", "median"), cx=("capex_to_da", "median"),
                                     cap=("market_cap", "sum")).sort_values("n", ascending=False).head(10)
        if len(by):
            L += ["**Core group by HQ country (medians; treat n < 5 as anecdotal)**", "",
                  "| HQ | n | EV/EBITDA | Analysts | Rev CAGR 3y | ROIC | Capex/D&A | Total cap |", "|---|---|---|---|---|---|---|---|"]
            L += [f"| {k} | {int(r['n'])} | {_fmt(r['ev'], 'x')} | {_fmt(r['an'], 'n')} | {_fmt(r['g'], 'pct')} | "
                  f"{_fmt(r['roic'], 'pct')} | {_fmt(r['cx'], 'x')} | {_fmt(r['cap'], 'bn')} |" for k, r in by.iterrows()] + [""]

        def table(g, title, n):
            if g.empty:
                return []
            rows = ["| Company | Ticker/ISIN | HQ | Cap | Share | Theme segments | Seg growth | Rev CAGR 3y | EBITDA m. | "
                    "EV/EBITDA | Analysts | US% | China% |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
            for _, r in g.head(n).iterrows():
                rows.append("| " + " | ".join([
                    str(r["conm"]).title()[:28], str(r["tic"]), str(r["loc"]), _fmt(r["market_cap"], "bn"),
                    _fmt(r["seg_share"], "pct"),
                    ("" if pd.isna(r.get("matched_segments")) else str(r["matched_segments"]))[:40].replace("|", "/"),
                    _fmt(r["seg_growth"], "pct"), _fmt(r["rev_cagr_3y"], "pct"), _fmt(r["ebitda_margin"], "pct"),
                    _fmt(r["ev_to_ebitda"], "x"), _fmt(r["analysts"], "n"), _fmt(r["us_share"], "pct"),
                    _fmt(r["china_share"], "pct")]) + " |")
            return [f"**{title}**", ""] + rows + [""]

        L += table(pure.sort_values("market_cap", ascending=False), "Segment pure plays (ex utilities), largest first", 12)
        L += table(minor[minor["seg_share"] >= 0.1].sort_values("market_cap", ascending=False),
                   "Theme segment is 10% to 50% of sales (possible hidden exposure), largest first", 12)
        cn = core[(core["loc"] != "USA") & (core["match_basis"] != "segment")]
        L += table(cn.sort_values("market_cap", ascending=False),
                   "Non-US core group by GICS or name (theme share unverified: needs Capital IQ / FactSet segments), largest first", 25)
        s = out["suppliers"].get(name)
        if s is not None and len(s):
            L += ["**Second-order suppliers: companies naming a theme anchor as a major customer**", "",
                  "| Supplier | Ticker/ISIN | HQ | Cap | Customer named | % of supplier sales | Analysts |",
                  "|---|---|---|---|---|---|---|"]
            for _, r in s.head(15).iterrows():
                L.append("| " + " | ".join([str(r["conm"]).title()[:28], str(r["tic"]), str(r["loc"]),
                                            _fmt(r["market_cap"], "bn"), str(r["cnms"]).title()[:30],
                                            _fmt(r["share_of_supplier_sales"], "pct"), _fmt(r["analysts"], "n")]) + " |")
            L.append("")
    L += ["## Caveats", "",
          "- Segment matching uses keywords on segment names and segment NAICS codes: expect false positives "
          "(for example 'test' or 'network') and misses. Check the matched segment names.",
          "- Segment data covers mostly US filers. A non-US company with no segment data is not 'unexposed'; its "
          "exposure is unverified and needs Capital IQ or FactSet segment revenue.",
          "- Customer links only exist where a company discloses a major customer (mostly US filers).",
          "- Analyst counts are missing where the I/B/E/S link failed, which is not the same as zero coverage."]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--themes", default=str(ROOT / "examples" / "themes_security_resilience.json"))
    ap.add_argument("--min-cap", type=float, default=1000, help="minimum market cap, USD mm")
    ap.add_argument("--refresh", action="store_true")
    a = ap.parse_args()
    themes = {k: v for k, v in json.loads(Path(a.themes).read_text()).items() if not k.startswith("_")}

    with WRDS(use_cache=not a.refresh) as w:
        out = build(w, themes, a.min_cap)

    run_dir = ROOT / "output" / f"theme_exposure_{datetime.now():%Y%m%d_%H%M}"
    run_dir.mkdir(parents=True, exist_ok=True)
    for name, d in out["themes"].items():
        d[[c for c in SHOW if c in d]].to_csv(run_dir / f"{name}.csv", index=False)
        if name in out["suppliers"]:
            out["suppliers"][name].to_csv(run_dir / f"{name}_suppliers.csv", index=False)
    notes = ROOT / "research" / "data_notes"
    notes.mkdir(parents=True, exist_ok=True)
    (notes / "theme_exposure.md").write_text(summarize(out, themes, a.min_cap))
    print(f"\n{out['link_note']}")
    for name, d in out["themes"].items():
        n_seg = int((d["match_basis"] == "segment").sum())
        print(f"  {name:28s} {len(d):>4} companies ({n_seg} by segment, core group {int(d['core'].sum())}, "
              f"{int((d['loc'] != 'USA').sum())} non-US)"
              f"  suppliers found: {len(out['suppliers'].get(name, []))}")
    print(f"\nSummary: {notes / 'theme_exposure.md'}\nCSVs:    {run_dir}/")


if __name__ == "__main__":
    main()
