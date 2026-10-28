"""Deep-dive analysis on a screen shortlist: history, quarterly trend, prices, peers, estimates, flags.

Every function takes the shared WRDS session so the whole pipeline uses one connection (one Duo push).
Money is USD millions at the latest FX rate unless stated; ratios are decimals.
"""
from __future__ import annotations

import sys
from pathlib import Path

import warnings

import numpy as np
import pandas as pd

warnings.simplefilter("ignore", FutureWarning)   # pandas concat notice for all-empty columns

sys.path.insert(0, str(Path(__file__).resolve().parent / ".claude" / "skills" / "wrds" / "scripts"))
from wrds_client import WRDS, MONEY_COLS  # noqa: E402
from screen import _div, _z, TAX_RATE  # noqa: E402

DEFAULTS = {
    "top_n": 15,                  # names taken from the top of the ranked screen
    "names": None,                # optional watchlist of ISINs or tickers: analyze exactly these instead of the top N
    "history_years": 10,
    "peer_level": "gsubind",      # widened to gind, ggroup, gsector until min_peers is met
    "min_peers": 5,
    "min_peer_market_cap": 250,   # USD mm
    "price_lookback_days": 400,
    "flags": {
        "dilution_1y": 0.05,              # shares outstanding up more than this
        "net_debt_to_ebitda": 3.0,
        "margin_compression_3y": -0.03,   # EBITDA margin change over 3 FY below this
        "growth_deceleration": 0.10,      # last FY growth below 3y CAGR by more than this
        "growth_spike": 1.0,              # last FY growth above this (possible one-off or M&A)
        "fcf_conversion_min": 0.5,
        "drawdown_from_high": -0.30,
        "peer_premium": 0.5,              # EV/EBITDA above peer median by more than this
        "min_adv_usd_mm": 1.0,            # average daily traded value, USD mm
        "stale_months": 12,
        "min_analysts": 3,
    },
}

PEER_LEVELS = ["gsubind", "gind", "ggroup", "gsector"]
PEER_METRICS = ["ev_to_ebitda", "ev_to_sales", "pe", "rev_growth_1y", "rev_cagr_3y", "gross_margin",
                "ebitda_margin", "fcf_margin", "roic", "net_debt_to_ebitda"]
LOWER_IS_BETTER = {"ev_to_ebitda", "ev_to_sales", "pe", "net_debt_to_ebitda"}


def _by_region(short: pd.DataFrame):
    for region, g in short.groupby("region"):
        yield region, sorted(g["gvkey"].unique())


# ---------------------------------------------------------------- annual history
def annual_history(w: WRDS, short: pd.DataFrame, fx: pd.Series, years: int, as_of) -> pd.DataFrame:
    parts = [w.fundamentals_annual(start_year=as_of.year - years - 1, gvkeys=keys, region=region,
                                   max_datadate=str(as_of)) for region, keys in _by_region(short)]
    h = pd.concat(parts, ignore_index=True).dropna(subset=["fyear"])
    h["_indl"] = (h["indfmt"] == "INDL").astype(int)
    h = h.sort_values(["gvkey", "fyear", "_indl", "datadate"]).drop_duplicates(["gvkey", "fyear"], keep="last")
    rate = h["curcd"].map(fx)
    for c in MONEY_COLS:
        h[c] = pd.to_numeric(h[c], errors="coerce") * rate
    h["fyear"] = h["fyear"].astype(int)
    h = h.sort_values(["gvkey", "fyear"]).reset_index(drop=True)

    g = h.groupby("gvkey")
    consecutive = (h["fyear"] - g["fyear"].shift(1)) == 1
    total_debt = _z(h["dltt"]) + _z(h["dlc"])
    net_debt = total_debt - _z(h["che"])
    invested = total_debt + h["ceq"] + _z(h["pstk"]) + _z(h["mib"]) - _z(h["che"])
    fcf = h["oancf"] - _z(h["capx"])
    out = pd.DataFrame({
        "gvkey": h["gvkey"], "fyear": h["fyear"], "datadate": h["datadate"], "curcd": h["curcd"],
        "revenue": h["sale"],
        "rev_growth": (_div(h["sale"], g["sale"].shift(1)) - 1).where(consecutive),
        "gross_margin": _div(h["sale"] - h["cogs"], h["sale"]),
        "ebitda": h["oibdp"],
        "ebitda_margin": _div(h["oibdp"], h["sale"]),
        "ebit_margin": _div(h["oiadp"], h["sale"]),
        "net_income": h["ni"],
        "net_margin": _div(h["ni"], h["sale"]),
        "fcf": fcf,
        "fcf_margin": _div(fcf, h["sale"]),
        "roic": _div(h["oiadp"] * (1 - TAX_RATE), invested),
        "net_debt": net_debt,
        "net_debt_to_ebitda": _div(net_debt, h["oibdp"]),
        "rd_intensity": _div(_z(h["xrd"]), h["sale"]),
        "shares_mm": h["csho"],
    })
    return out


# ---------------------------------------------------------------- quarterly trend
Q_COLS = ["gvkey", "datadate", "fyearq", "fqtr", "indfmt", "curcdq", "saleq", "oibdpq", "niq"]


def quarterly_trend(w: WRDS, short: pd.DataFrame, fx: pd.Series, as_of) -> tuple:
    """Returns (quarter rows, one summary row per company)."""
    start = str((pd.Timestamp(as_of) - pd.DateOffset(years=3, months=3)).date())
    parts = [w.fundamentals_quarterly(start_date=start, gvkeys=keys, columns=Q_COLS, region=region)
             for region, keys in _by_region(short)]
    q = pd.concat(parts, ignore_index=True)
    q = q[(q["datadate"] <= pd.Timestamp(as_of)) & q["fyearq"].notna() & q["fqtr"].notna()].copy()
    q["_indl"] = (q["indfmt"] == "INDL").astype(int)
    q = q.sort_values(["gvkey", "datadate", "_indl"]).drop_duplicates(["gvkey", "fyearq", "fqtr"], keep="last")
    rate = q["curcdq"].map(fx)
    for c in ("saleq", "oibdpq", "niq"):
        q[c] = pd.to_numeric(q[c], errors="coerce") * rate
    q["ebitda_margin_q"] = _div(q["oibdpq"], q["saleq"])

    prior = q[["gvkey", "fyearq", "fqtr", "saleq", "ebitda_margin_q"]].copy()
    prior["fyearq"] += 1
    q = q.merge(prior.rename(columns={"saleq": "saleq_ya", "ebitda_margin_q": "ebitda_margin_q_ya"}),
                on=["gvkey", "fyearq", "fqtr"], how="left")
    q["rev_yoy_q"] = _div(q["saleq"], q["saleq_ya"]) - 1
    q["ebitda_margin_q_chg"] = q["ebitda_margin_q"] - q["ebitda_margin_q_ya"]
    q = q.sort_values(["gvkey", "datadate"]).reset_index(drop=True)

    rows = []
    for gvkey, g in q.groupby("gvkey"):
        g = g.dropna(subset=["saleq"])
        if g.empty:
            continue
        last = g.iloc[-1]
        ttm = g["saleq"].tail(4).sum() if len(g) >= 4 else np.nan
        prior_ttm = g["saleq"].iloc[-8:-4].sum() if len(g) >= 8 else np.nan
        prev_yoy = g["rev_yoy_q"].iloc[-2] if len(g) >= 2 else np.nan
        rows.append({
            "gvkey": gvkey, "last_quarter": last["datadate"], "quarters_available": len(g),
            "rev_yoy_latest_q": last["rev_yoy_q"], "rev_yoy_prior_q": prev_yoy,
            "ebitda_margin_latest_q": last["ebitda_margin_q"],
            "ebitda_margin_q_yoy_chg": last["ebitda_margin_q_chg"],
            "ttm_revenue": ttm,
            "ttm_rev_growth": (ttm / prior_ttm - 1) if prior_ttm and prior_ttm > 0 else np.nan,
        })
    cols = ["gvkey", "datadate", "fyearq", "fqtr", "saleq", "rev_yoy_q", "oibdpq", "ebitda_margin_q", "niq"]
    return q[cols], pd.DataFrame(rows)


# ---------------------------------------------------------------- price performance
def price_performance(w: WRDS, short: pd.DataFrame, fx: pd.Series, lookback_days: int, as_of) -> pd.DataFrame:
    parts = [w.daily_prices(keys, lookback_days=lookback_days, as_of=str(as_of), region=region)
             for region, keys in _by_region(short)]
    p = pd.concat(parts, ignore_index=True)
    rows = []
    for gvkey, g in p.groupby("gvkey"):
        g = g.sort_values("datadate")
        adjf = pd.to_numeric(g["ajexdi"], errors="coerce").where(lambda x: x > 0)
        trf = pd.to_numeric(g["trfd"], errors="coerce").ffill().fillna(1.0)
        adj = (g["price"] / adjf * trf).dropna()
        if len(adj) < 2:
            continue
        last = adj.iloc[-1]

        def ret(n):
            return last / adj.iloc[-1 - n] - 1 if len(adj) > n else np.nan

        year = adj.tail(252)
        rate = fx.get(g["curcdd"].iloc[-1], np.nan)
        traded = (g["price"] * pd.to_numeric(g["cshtrd"], errors="coerce")).tail(63).mean()
        rows.append({
            "gvkey": gvkey, "price_date": g["datadate"].iloc[-1], "trading_days": len(adj),
            "ret_1m": ret(21), "ret_3m": ret(63), "ret_6m": ret(126), "ret_12m": ret(252),
            "pct_from_52w_high": last / year.max() - 1,
            "pct_above_52w_low": last / year.min() - 1,
            "volatility_1y": adj.pct_change().tail(252).std() * np.sqrt(252),
            "adv_usd_mm": traded * rate / 1e6,
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- peers
def peer_comparison(dataset: pd.DataFrame, short: pd.DataFrame, cfg: dict) -> tuple:
    """Compare each company with industry peers drawn from the full (unfiltered) screen dataset.

    Returns (long table: one row per company x metric, summary: one row per company).
    """
    pool = dataset[(dataset["costat"] == "A") & (dataset["market_cap"] >= cfg["min_peer_market_cap"])]
    start = PEER_LEVELS.index(cfg["peer_level"]) if cfg["peer_level"] in PEER_LEVELS else 0
    long_rows, summary = [], []
    for _, co in short.iterrows():
        peers, level = pool.iloc[0:0], None
        for level in PEER_LEVELS[start:]:
            code = co.get(level)
            if code is None or pd.isna(code):
                continue
            peers = pool[(pool[level] == code) & (pool["gvkey"] != co["gvkey"])]
            if len(peers) >= cfg["min_peers"]:
                break
        biggest = peers.sort_values("market_cap", ascending=False).head(5)
        summary.append({
            "gvkey": co["gvkey"], "peer_level": level, "peer_count": len(peers),
            "largest_peers": "; ".join(str(n).title() for n in biggest["conm"]),
        })
        for m in PEER_METRICS:
            vals = pd.to_numeric(peers[m], errors="coerce").dropna()
            v = co.get(m)
            med = vals.median() if len(vals) else np.nan
            pct = (vals < v).mean() if len(vals) and pd.notna(v) else np.nan
            long_rows.append({
                "gvkey": co["gvkey"], "metric": m, "company": v, "peer_median": med, "peers_with_data": len(vals),
                "percentile": pct,
                # a negative multiple (negative EV or earnings) isn't comparable with the peer median
                "vs_median": (v / med - 1) if pd.notna(v) and pd.notna(med) and med > 0
                and not (m in LOWER_IS_BETTER and v <= 0) else np.nan,
            })
    return pd.DataFrame(long_rows), pd.DataFrame(summary)


# ---------------------------------------------------------------- analyst estimates (US + international)
EST_COLS = ["gvkey", "ibes_ticker", "est_currency", "eps_fy1", "eps_fy2", "analysts", "fy1_period_end",
            "eps_growth_fy2", "revision_breadth", "forward_pe", "ebitda_fy1_usd", "ev_to_ebitda_fwd",
            "sales_fy1_usd", "est_sales_growth_fy1", "ebitda_analysts"]


def _link_ibes(short: pd.DataFrame, f1: pd.DataFrame, international: bool) -> pd.DataFrame:
    """US: 8-character CUSIP. International: the last 6 characters of the I/B/E/S id equal the first 6 of the SEDOL."""
    f1 = f1.copy()
    f1["cusip"] = f1["cusip"].astype(str).str.strip().str.upper()
    if international:
        k = short[short["px_sedol"].notna()].assign(k=lambda d: d["px_sedol"].astype(str).str.strip().str.upper().str[:6])
        f1["k"] = f1["cusip"].str[-6:]
    else:
        k = short[short["cusip"].notna()].assign(k=lambda d: d["cusip"].astype(str).str[:8])
        f1["k"] = f1["cusip"].str[:8]
    return k[["gvkey", "k"]].merge(f1, on="k", how="inner").drop_duplicates("gvkey")


def analyst_estimates(w: WRDS, short: pd.DataFrame, fx: pd.Series) -> pd.DataFrame:
    """I/B/E/S consensus for FY1/FY2 EPS plus FY1 EBITDA and sales, for US and non-US names.

    Estimates are in the analysts' currency (`est_currency`); forward P/E is only computed when that
    matches the price currency, and EBITDA / sales are converted to USD at the latest FX rate.
    """
    parts = []
    for international in (False, True):
        e1 = w.ibes_consensus(fpi="1", international=international)
        e = _link_ibes(short[~short["gvkey"].isin([g for p_ in parts for g in p_["gvkey"]])], e1, international)
        if e.empty:
            continue
        e = e.rename(columns={"ticker": "ibes_ticker", "meanest": "eps_fy1", "numest": "analysts",
                              "fpedats": "fy1_period_end", "curcode": "est_currency"})
        e["revision_breadth"] = _div(e["numup"] - e["numdown"], e["analysts"])
        e2 = w.ibes_consensus(fpi="2", international=international)[["ticker", "meanest"]]
        e = e.merge(e2.rename(columns={"ticker": "ibes_ticker", "meanest": "eps_fy2"}), on="ibes_ticker", how="left")
        for measure, col in (("EBT", "ebitda_fy1"), ("SAL", "sales_fy1")):
            try:
                x = w.ibes_consensus(fpi="1", measure=measure, international=international)
                x = x[["ticker", "meanest", "numest", "curcode"]].rename(
                    columns={"ticker": "ibes_ticker", "meanest": col, "numest": f"{col}_n", "curcode": f"{col}_cur"})
                e = e.merge(x.drop_duplicates("ibes_ticker"), on="ibes_ticker", how="left")
            except Exception:
                e[col], e[f"{col}_n"], e[f"{col}_cur"] = np.nan, np.nan, None
        parts.append(e)
    if not parts:
        return pd.DataFrame(columns=EST_COLS)
    e = pd.concat(parts, ignore_index=True).merge(
        short[["gvkey", "price", "curcdd", "enterprise_value", "revenue", "oibdp", "pe"]], on="gvkey", how="left")
    same_ccy = e["est_currency"] == e["curcdd"]
    e["eps_growth_fy2"] = _div(e["eps_fy2"], e["eps_fy1"]) - 1
    e["forward_pe"] = _div(e["price"], e["eps_fy1"]).where(same_ccy)
    # A forward P/E below 25% of the trailing P/E almost always means the estimate and the price are on
    # different share bases (a recent split), so it is blanked rather than reported.
    e.loc[e["forward_pe"] < 0.25 * e["pe"], "forward_pe"] = np.nan
    e["ebitda_fy1_usd"] = e["ebitda_fy1"] * e["ebitda_fy1_cur"].map(fx)
    e["sales_fy1_usd"] = e["sales_fy1"] * e["sales_fy1_cur"].map(fx)
    # I/B/E/S quotes non-per-share estimates in millions for most currencies but in billions for some
    # (JPY, KRW). Detect that from the data: an estimate under 2% of the last reported figure is in billions.
    in_bn = (e["sales_fy1_usd"] / e["revenue"] < 0.02) | (e["sales_fy1_usd"].isna() & (e["ebitda_fy1_usd"] / e["oibdp"] < 0.02))
    for c in ("ebitda_fy1_usd", "sales_fy1_usd"):
        e.loc[in_bn.fillna(False), c] *= 1000.0
    e["ev_to_ebitda_fwd"] = _div(e["enterprise_value"], e["ebitda_fy1_usd"])
    e["est_sales_growth_fy1"] = _div(e["sales_fy1_usd"], e["revenue"]) - 1
    e["ebitda_analysts"] = e["ebitda_fy1_n"]
    return e[EST_COLS]


# ---------------------------------------------------------------- flags
def flags_for(row: dict, t: dict, latest_fy_end) -> tuple:
    """Rule-based (risks, strengths) for one company from its merged summary row."""
    def val(k):
        v = row.get(k)
        return None if v is None or (isinstance(v, float) and np.isnan(v)) else v

    risks, strengths = [], []
    v = val("share_change_1y")
    if v is not None and v > t["dilution_1y"]:
        risks.append(f"Share count up {v:.0%} in the last fiscal year (dilution)")
    elif v is not None and v < -0.02:
        strengths.append(f"Share count down {abs(v):.0%} (buybacks)")
    v = val("net_debt_to_ebitda")
    if v is not None and v > t["net_debt_to_ebitda"]:
        risks.append(f"Net debt is {v:.1f}x EBITDA")
    if val("net_debt") is not None and val("net_debt") < 0:
        strengths.append("Net cash balance sheet")
    if val("fcf") is not None and val("fcf") < 0:
        risks.append("Negative free cash flow in the last fiscal year")
    v = val("ebitda_margin_chg_3y")
    if v is not None and v < t["margin_compression_3y"]:
        risks.append(f"EBITDA margin down {abs(v) * 100:.1f} pts over 3 years")
    elif v is not None and v > 0.03:
        strengths.append(f"EBITDA margin up {v * 100:.1f} pts over 3 years")
    g1, g3 = val("rev_growth_1y"), val("rev_cagr_3y")
    if g1 is not None and g1 > t["growth_spike"]:
        risks.append(f"Revenue up {g1:.0%} in one year: check for M&A or a one-off")
    elif g1 is not None and g3 is not None and g1 < g3 - t["growth_deceleration"]:
        risks.append(f"Growth decelerating: {g1:.0%} last year vs {g3:.0%} 3-year CAGR")
    v = val("fcf_conversion")
    if v is not None and val("ni") is not None and val("ni") > 0 and v < t["fcf_conversion_min"]:
        risks.append(f"Weak cash conversion: FCF is {v:.0%} of net income")
    v = val("pct_from_52w_high")
    if v is not None and v < t["drawdown_from_high"]:
        risks.append(f"Trading {abs(v):.0%} below its 52-week high")
    v = val("adv_usd_mm")
    if v is not None and v < t["min_adv_usd_mm"]:
        risks.append(f"Thin liquidity: about ${v:.2f}mm traded per day")
    v = val("peer_ev_to_ebitda_vs_median")
    if v is not None and v > t["peer_premium"]:
        risks.append(f"EV/EBITDA is {v:.0%} above the peer median")
    elif v is not None and v < -0.2:
        strengths.append(f"EV/EBITDA is {abs(v):.0%} below the peer median")
    v = val("peer_roic_percentile")
    if v is not None and v >= 0.75:
        strengths.append(f"ROIC beats {v:.0%} of peers")
    v = val("ttm_rev_growth")
    if v is not None and g1 is not None and v > g1 + 0.05:
        strengths.append(f"Recent quarters accelerating: trailing-12-month revenue growth {v:.0%}")
    elif v is not None and v < 0:
        risks.append(f"Trailing-12-month revenue is shrinking ({v:.0%})")
    d = row.get("datadate")
    if d is not None and pd.notna(d) and pd.Timestamp(d) < latest_fy_end - pd.DateOffset(months=t["stale_months"]):
        risks.append(f"Latest annual financials are dated {pd.Timestamp(d).date()}")
    v = val("analysts")
    if v is not None and v < t["min_analysts"]:
        risks.append(f"Only {int(v)} analyst(s) covering")
    v = val("revision_breadth")
    if v is not None and v >= 0.3:
        strengths.append("Analyst estimates are being revised up")
    elif v is not None and v <= -0.3:
        risks.append("Analyst estimates are being revised down")
    return risks, strengths
