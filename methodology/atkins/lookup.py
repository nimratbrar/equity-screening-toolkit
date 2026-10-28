"""PUBLIC METHODOLOGY COPY: logic kept; inputs from licensed databases replaced by illustrative placeholders. See docs/METHODOLOGY.md.

Find AtkinsRéalis and WSP in Compustat and see why the screen drops them.
Run from the repository root (one WRDS connection): ~/.venvs/equity-screening-toolkit/bin/python methodology/atkins/lookup.py
"""
import sys
sys.path.insert(0, ".claude/skills/wrds/scripts")
from wrds_client import WRDS
with WRDS(use_cache=False) as w:
    co = w.sql("select gvkey, conm, cik, fic, loc, costat, priusa, prican, gsubind from comp.company "
               "where conm like %(a)s or conm like %(b)s or conm like %(c)s", {"a": "%ATKINS%", "b": "%LAVALIN%", "c": "WSP GLOBAL%"})
    print(co.to_string(index=False))
    for g in co.gvkey:
        f = w.sql("select gvkey, datadate, fyear, indfmt, datafmt, popsrc, consol, curcd, sale, oibdp from comp.funda where gvkey=%(g)s "
                  "and datadate >= current_date - 800 order by datadate desc limit 6", {"g": g})
        print(f.to_string(index=False))
        p = w.sql("select gvkey, iid, datadate, prccd, cshoc, curcdd, exchg, tic from comp.secd where gvkey=%(g)s "
                  "and datadate >= current_date - 20 order by datadate desc, iid limit 8", {"g": g})
        print(p.to_string(index=False))
