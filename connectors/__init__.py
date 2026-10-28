"""Optional, file-based connectors that enrich the WRDS pipeline with data the user licenses separately.

Both connectors are OFF by default. The pipeline runs fully on WRDS alone; nothing here connects to any service.
The user exports or types the files themselves, keeps them in `inputs/` (git-ignored) and turns a connector on
in the pipeline config:

    "connectors": {
      "capiq":    {"enabled": true, "file": "inputs/capiq_export.xlsx", "sheet": 0, "header_row": 0,
                   "column_map": {"ISIN": "isin", "Ticker": "ticker", "EBITDA NTM": "ebitda_ntm"}},
      "industry": {"enabled": true, "file": "inputs/industry_figures.csv"}
    }

- capiq:    a Capital IQ screen export (Excel or CSV) the user downloads under their own licence.
            Columns are renamed with `column_map` to the toolkit names in templates/capiq_export_template.csv,
            joined on ISIN, then ticker, and added to the summary with the prefix `capiq_`.
- industry: industry-level figures the user enters by hand from a report they license (for example IBISWorld),
            in templates/industry_figures_template.csv format. Rows are matched to companies on NAICS, GICS or
            SIC prefixes and added with the prefix `ind_`. Keep the source and page on every row.

No licensed content ships with this repository: only the adapter code and header-only templates.
"""
from __future__ import annotations

import pandas as pd

from .capiq_import import merge_capiq
from .industry_figures import merge_industry

DEFAULTS = {
    "capiq": {"enabled": False, "file": None, "sheet": 0, "header_row": 0, "column_map": {}},
    "industry": {"enabled": False, "file": None},
}


def apply_connectors(summary: pd.DataFrame, cfg: dict | None, warnings: list) -> tuple[pd.DataFrame, list]:
    """Return (summary, list of connectors applied). Failures become warnings; they never stop the pipeline."""
    cfg = cfg or {}
    used = []
    for name, fn in (("capiq", merge_capiq), ("industry", merge_industry)):
        c = {**DEFAULTS[name], **(cfg.get(name) or {})}
        if not c.get("enabled"):
            continue
        try:
            summary, note = fn(summary, c)
            used.append(f"{name}: {note}")
        except Exception as e:  # a bad user file must not break a WRDS run
            warnings.append(f"Connector '{name}' skipped: {str(e).splitlines()[0][:200]}")
    return summary, used
