"""
Check which WRDS datasets this account can query.

Run from the project folder:
    ~/.venvs/equity-screening-toolkit/bin/python check_access.py

First run: the wrds package asks for your WRDS username and password in the terminal
and offers to create ~/.pgpass. Answer yes so later runs don't prompt. Approve the Duo
push if one arrives.

Writes a summary to output/access_report.md.
"""

import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import wrds
except ImportError:
    sys.exit("The 'wrds' package isn't installed. Run ./setup.sh first.")

# Libraries worth knowing about for company screening, with the tables to probe.
TARGETS = {
    "comp": {
        "label": "Compustat North America",
        "tables": ["company", "funda", "fundq", "secm"],
        "freshness": ("funda", "datadate"),
    },
    "comp_global_daily": {
        "label": "Compustat Global",
        "tables": ["g_company", "g_funda"],
        "freshness": ("g_funda", "datadate"),
    },
    "crsp": {
        "label": "CRSP (US stock prices & returns)",
        "tables": ["msf", "dsf", "stocknames"],
        "freshness": ("msf", "date"),
    },
    "pitchbk": {
        "label": "PitchBook (private companies & deals)",
        "tables": [],  # table names vary by subscription; listed dynamically
        "freshness": None,
    },
    "ibes": {
        "label": "I/B/E/S (analyst estimates)",
        "tables": ["statsum_epsus"],
        "freshness": ("statsum_epsus", "statpers"),
    },
}


def probe_table(db, lib, table):
    """Return (ok, message) for a one-row read of lib.table."""
    try:
        df = db.raw_sql(f"select * from {lib}.{table} limit 1")
        return True, f"readable ({len(df.columns)} columns)"
    except Exception as e:  # permission errors, missing tables, etc.
        msg = str(e).splitlines()[0][:120]
        return False, f"not readable: {msg}"


def latest_date(db, lib, table, col):
    try:
        df = db.raw_sql(f"select max({col}) as latest from {lib}.{table}")
        return str(df["latest"].iloc[0])
    except Exception:
        return "unknown"


def main():
    username = os.environ.get("WRDS_USERNAME")
    print("Connecting to WRDS (approve the Duo push if one arrives)...")
    db = wrds.Connection(wrds_username=username) if username else wrds.Connection()

    libraries = sorted(db.list_libraries())
    print(f"Connected. {len(libraries)} libraries visible.\n")

    lines = [
        "# WRDS access report",
        f"Generated {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Libraries visible: {len(libraries)}",
        "",
        "## Key datasets for screening",
        "",
    ]

    for lib, info in TARGETS.items():
        header = f"### {info['label']} (`{lib}`)"
        print(header.replace("### ", "").replace("`", ""))
        lines.append(header)

        if lib not in libraries:
            print("  not in your subscription\n")
            lines += ["- Not visible to this account", ""]
            continue

        tables = info["tables"]
        if not tables:
            try:
                tables = sorted(db.list_tables(library=lib))[:10]
                lines.append(f"- Tables found (first 10): {', '.join(tables)}")
            except Exception as e:
                lines.append(f"- Could not list tables: {str(e).splitlines()[0][:120]}")
                tables = []

        any_ok = False
        for t in tables:
            ok, msg = probe_table(db, lib, t)
            any_ok = any_ok or ok
            print(f"  {t}: {msg}")
            lines.append(f"- `{t}`: {msg}")

        if any_ok and info["freshness"]:
            t, col = info["freshness"]
            latest = latest_date(db, lib, t, col)
            print(f"  latest {t}.{col}: {latest}")
            lines.append(f"- Most recent `{t}.{col}`: {latest}")

        print()
        lines.append("")

    lines += ["## All visible libraries", "", ", ".join(libraries), ""]

    db.close()

    out = Path("output")
    out.mkdir(exist_ok=True)
    report = out / "access_report.md"
    report.write_text("\n".join(lines))
    print(f"Report saved to {report}")


if __name__ == "__main__":
    main()
