"""Capital IQ screen-export adapter (optional, off by default).

The user runs a screen in Capital IQ under their own licence, exports it to Excel or CSV and points the config
at that file. This module only reads the local file; it never calls Capital IQ. Column names in exports vary
with the user's template, so the config maps them to the toolkit names listed in
connectors/templates/capiq_export_template.csv (at least one of `isin` or `ticker` is required for the join).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

TEMPLATE = Path(__file__).resolve().parent / "templates" / "capiq_export_template.csv"
KEYS = ("isin", "ticker")
NA_TOKENS = ["NA", "NM", "-", "--", "n/a", "N/A", ""]


def toolkit_fields() -> list:
    return pd.read_csv(TEMPLATE, nrows=0).columns.tolist()


def read_export(cfg: dict) -> pd.DataFrame:
    path = Path(cfg["file"]) if cfg.get("file") else None
    if path is None or not path.exists():
        raise FileNotFoundError(f"Capital IQ export not found: {path}")
    if path.suffix.lower() in (".xlsx", ".xls"):
        df = pd.read_excel(path, sheet_name=cfg.get("sheet", 0), header=cfg.get("header_row", 0), na_values=NA_TOKENS)
    else:
        df = pd.read_csv(path, header=cfg.get("header_row", 0), na_values=NA_TOKENS)
    cmap = cfg.get("column_map") or {}
    unknown = sorted(set(cmap.values()) - set(toolkit_fields()))
    if unknown:
        raise ValueError(f"column_map targets not in the template: {unknown}")
    df = df.rename(columns=cmap)[[c for c in cmap.values() if c in df.rename(columns=cmap).columns]]
    if not any(k in df for k in KEYS):
        raise ValueError("map at least one of 'isin' or 'ticker' in column_map")
    for k in KEYS:
        if k in df:
            v = df[k].astype(str).str.strip().str.upper()
            df[k] = v.where(~v.isin(["NAN", "NONE", ""]), None)
    for c in df.columns:
        if c not in KEYS and c != "company_name":
            num = pd.to_numeric(df[c], errors="coerce")
            if num.notna().sum() >= df[c].notna().sum() * 0.8:   # keep text columns as text
                df[c] = num
    return df


def merge_capiq(summary: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, str]:
    ext = read_export(cfg)
    out = summary.copy()
    isin = out["px_isin"].astype(object) if "px_isin" in out else pd.Series(None, index=out.index, dtype=object)
    if "isin" in out:
        isin = isin.fillna(out["isin"])
    keys = {"isin": isin.astype(object).where(isin.notna(), "").astype(str).str.upper(),
            "ticker": out["tic"].astype(object).where(out["tic"].notna(), "").astype(str).str.upper()}
    val_cols = [c for c in ext.columns if c not in KEYS]
    matched = pd.Series(False, index=out.index)
    for k in KEYS:
        if k not in ext:
            continue
        lut = ext.dropna(subset=[k]).drop_duplicates(k).set_index(k)[val_cols]
        hit = keys[k].isin(lut.index) & ~matched
        for c in val_cols:
            col = f"capiq_{c}"
            vals = keys[k].map(lut[c]).astype(object)
            out[col] = vals.where(hit, out[col].astype(object) if col in out else None)
        matched |= hit
    for c in val_cols:
        num = pd.to_numeric(out[f"capiq_{c}"], errors="coerce")
        if num.notna().sum() >= out[f"capiq_{c}"].notna().sum() * 0.8:
            out[f"capiq_{c}"] = num
    return out, f"{int(matched.sum())} of {len(out)} companies matched from {Path(cfg['file']).name}"
