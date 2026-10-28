"""User-entered industry figures (optional, off by default), for example from an IBISWorld report the user licenses.

The user types one row per figure into a CSV with the header in
connectors/templates/industry_figures_template.csv. Nothing is scraped or downloaded. Each row is matched to
companies whose NAICS, GICS sub-industry or SIC code starts with `industry_code` (per `code_type`). When several
rows match a company, the longest (most specific) code wins. Every row should carry `source` and `page` so the
figure can be cited as [report: source, p.N].
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TEMPLATE = Path(__file__).resolve().parent / "templates" / "industry_figures_template.csv"
CODE_COL = {"naics": "naics", "gics": "gsubind", "sic": "sic"}


def read_figures(cfg: dict) -> pd.DataFrame:
    path = Path(cfg["file"]) if cfg.get("file") else None
    if path is None or not path.exists():
        raise FileNotFoundError(f"industry figures file not found: {path}")
    df = pd.read_csv(path, dtype={"industry_code": str})
    need = pd.read_csv(TEMPLATE, nrows=0).columns.tolist()
    missing = [c for c in need if c not in df]
    if missing:
        raise ValueError(f"industry figures file is missing columns {missing}")
    df["code_type"] = df["code_type"].str.lower().str.strip()
    bad = sorted(set(df["code_type"]) - set(CODE_COL))
    if bad:
        raise ValueError(f"code_type must be one of {sorted(CODE_COL)}, got {bad}")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


def merge_industry(summary: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, str]:
    fig = read_figures(cfg)
    out = summary.copy()
    n_hit = 0
    for i, r in out.iterrows():
        best = {}
        for _, f in fig.iterrows():
            code = str(r.get(CODE_COL[f["code_type"]]) or "")
            if code.startswith(f["industry_code"]) and len(f["industry_code"]) >= best.get(f["metric"], ("", 0))[1]:
                best[f["metric"]] = (f, len(f["industry_code"]))
        for metric, (f, _) in best.items():
            out.loc[i, f"ind_{metric}"] = f["value"]
            out.loc[i, f"ind_{metric}_src"] = f"{f['industry_name']} ({f['year']}, {f['unit']}) [report: {f['source']}, p.{f['page']}]"
        n_hit += bool(best)
    return out, f"{n_hit} of {len(out)} companies matched to {fig['industry_code'].nunique()} industry codes"
