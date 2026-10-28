"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Build data/scenario/external/hde_series.csv (long format: date, series, value, unit, source).

FRED series are read from CSVs you download yourself into data/scenario/external/ (public, free).
Hand-entered points (public sources only) carry their URL and access date in methodology/hdhyundai/hde_points.csv,
which you create yourself with columns date, series, value, unit, source, url (not shipped with this repository).
Run: python3 methodology/hdhyundai/build_hde_series.py
"""
import csv
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXT = os.path.join(ROOT, "data", "scenario", "external")
ACC = "accessed 2026-10-20"

FRED = [
    # file, series name, unit, sampling: 'M' monthly as is, 'ME' month-end of daily
    ("fred_PCU335311335311.csv", "us_ppi_power_distribution_transformers", "index (BLS base)", "M", "2007-01"),
    ("fred_PCU3353133531.csv", "us_ppi_switchgear_apparatus", "index", "M", "2007-01"),
    ("fred_DEXKOUS.csv", "usdkrw_month_end", "KRW per USD", "ME", "2019-01"),
    ("fred_DCOILBRENTEU.csv", "brent_month_end", "USD/bbl", "ME", "2019-01"),
]


def fred_rows():
    out = []
    for f, name, unit, mode, start in FRED:
        sid = f[5:-4]
        url = f"https://fred.stlouisfed.org/series/{sid}"
        rows = [(d, x) for d, x in list(csv.reader(open(os.path.join(EXT, f))))[1:] if x not in ("", ".")]
        rows = [(d, float(x)) for d, x in rows if d[:7] >= start]
        if mode == "ME":
            last = {}
            for d, x in rows:
                last[d[:7]] = (d, x)
            rows = sorted(last.values())
        for d, x in rows:
            out.append((d, name, round(x, 3), unit, f"FRED {sid}, {url}, {ACC}"))
    return out


def main():
    rows = fred_rows()
    pts = os.path.join(ROOT, "methodology", "hdhyundai", "hde_points.csv")
    for r in csv.DictReader(open(pts)):
        rows.append((r["date"], r["series"], r["value"], r["unit"], f'{r["source"]}, {r["url"]}, {ACC}'))
    rows.sort(key=lambda r: (r[1], r[0]))
    with open(os.path.join(EXT, "hde_series.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["date", "series", "value", "unit", "source"])
        w.writerows(rows)
    print(len(rows), "rows written")


if __name__ == "__main__":
    main()
