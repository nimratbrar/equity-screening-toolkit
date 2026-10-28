"""WRDS data access for screening pipelines.

One `WRDS` session = at most one database connection = one Duo push. The connection is
opened lazily on the first query that isn't cached, so fully cached runs need no Duo push.

Usage:
    from wrds_client import WRDS
    with WRDS() as w:
        f = w.fundamentals_annual(start_year=2020)
        m = w.latest_market_data()

Credentials, in order:
  1. ~/.pgpass (the user's local machine; created once in their own terminal).
  2. WRDS_USERNAME + WRDS_PASSWORD environment variables (a Claude Code cloud environment,
     set in the environment's settings by the user). PGPASSFILE is also honored.
The password is never printed, logged, cached or written to disk by this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import socket
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

WRDS_HOST = "wrds-pgdata.wharton.upenn.edu"
WRDS_PORT = 9737
PGPASS = Path(os.environ.get("PGPASSFILE", Path.home() / ".pgpass"))

# Standard Compustat filters. North America: industrial, standardized, domestic, consolidated.
# Global: popsrc 'I' (international); datafmt is HIST_STD there, and banks/insurers may only have the
# FS (financial services) format, so both formats are pulled and INDL is preferred when a firm has both.
COMPUSTAT_STD = "f.indfmt = 'INDL' and f.datafmt = 'STD' and f.popsrc = 'D' and f.consol = 'C'"
COMPUSTAT_GLOBAL_STD = ("f.indfmt in ('INDL', 'FS') and f.datafmt in ('HIST_STD', 'STD') "
                        "and f.popsrc = 'I' and f.consol = 'C'")

# region -> (library, annual table, quarterly table, company table, daily security table, filter,
#            primary-issue expression on the company table)
REGIONS = {
    "na": ("comp", "funda", "fundq", "company", "secd", COMPUSTAT_STD, "coalesce(c.priusa, c.prican)"),
    "intl": ("comp_global_daily", "g_funda", "g_fundq", "g_company", "g_secd", COMPUSTAT_GLOBAL_STD,
             "coalesce(c.prirow, c.priusa, c.prican)"),
}

FUNDA_COLS = [
    "gvkey", "datadate", "fyear", "fyr", "conm", "tic", "cusip", "cik", "isin", "curcd", "indfmt",
    "sale", "revt", "cogs", "xsga", "xrd", "oibdp", "oiadp", "ib", "ni", "dp", "xint", "txt", "pi",
    "capx", "oancf", "at", "lt", "act", "lct", "che", "invt", "rect", "ceq", "seq", "pstk", "mib",
    "dltt", "dlc", "csho", "prcc_f", "dvc", "dvt", "emp",
    "nicon", "cshoi",   # Compustat Global names for net income and shares outstanding
]

COMPANY_COLS = [
    "gvkey", "conm", "fic", "loc", "state", "city", "costat", "gsector", "ggroup", "gind", "gsubind",
    "sic", "naics", "busdesc", "weburl", "ipodate", "priusa", "prican", "prirow", "cik",
]

# Compustat money items (millions of curcd). Converted to USD by the screen; `emp`/`csho` are not money.
MONEY_COLS = ["sale", "revt", "cogs", "xsga", "xrd", "oibdp", "oiadp", "ib", "ni", "nicon", "dp", "xint", "txt", "pi",
              "capx", "oancf", "at", "lt", "act", "lct", "che", "invt", "rect", "ceq", "seq", "pstk", "mib",
              "dltt", "dlc", "dvc", "dvt"]

GICS_SECTORS = {
    "10": "Energy", "15": "Materials", "20": "Industrials", "25": "Consumer Discretionary",
    "30": "Consumer Staples", "35": "Health Care", "40": "Financials", "45": "Information Technology",
    "50": "Communication Services", "55": "Utilities", "60": "Real Estate",
}

# CRSP CIZ (v2) common-stock filter: US-incorporated operating companies' common shares on NYSE/AMEX/NASDAQ.
CRSP_COMMON_STOCK = (
    "sharetype = 'NS' and securitytype = 'EQTY' and securitysubtype = 'COM' and usincflg = 'Y' "
    "and issuertype in ('ACOR', 'CORP') and primaryexch in ('N', 'A', 'Q') "
    "and conditionaltype in ('RW', 'NW') and tradingstatusflg = 'A'"
)


# Date column for each dataset, used to find the latest available date at run time.
# Never hard-code dataset end dates: WRDS updates on its own schedules, and some tables
# carry placeholder future dates, so "latest" always means max(date) <= today.
DATASET_DATES = {
    "comp.funda": "datadate",
    "comp.fundq": "datadate",
    "comp.secd": "datadate",
    "comp_global_daily.g_funda": "datadate",
    "comp_global_daily.g_secd": "datadate",
    "comp_global_daily.g_exrt_dly": "datadate",
    "crsp.msf_v2": "mthcaldt",
    "crsp.dsf_v2": "dlycaldt",
    "wrdsapps_finratio.firm_ratio": "public_date",
    "ibes.statsum_epsus": "statpers",
    "pitchbk.deal": "dealdate",
    "comp_segments_hist_daily.wrds_segmerged": "datadate",
    "comp_segments_hist_daily.seg_customer": "datadate",
    "ibes.statsum_epsint": "statpers",
}


class WRDSSetupError(RuntimeError):
    pass


def pgpass_username() -> Optional[str]:
    """Username from the WRDS line in ~/.pgpass (the password is never read into a variable)."""
    if not PGPASS.exists():
        return None
    for line in PGPASS.read_text().splitlines():
        parts = line.split(":")
        if len(parts) >= 5 and parts[0] == WRDS_HOST:
            return parts[3]
    return None


def _to_numpy_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """wrds returns pandas nullable dtypes (Float64, string); convert to plain numpy so NaN handling,
    ranking and arithmetic behave normally downstream."""
    for c in df.columns:
        if pd.api.types.is_extension_array_dtype(df[c].dtype):
            if pd.api.types.is_numeric_dtype(df[c].dtype) or pd.api.types.is_bool_dtype(df[c].dtype):
                df[c] = df[c].astype("float64")
            else:
                df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def _log(msg: str) -> None:
    print(f"[wrds] {msg}", file=sys.stderr, flush=True)


class WRDS:
    """Cached, lazily connected WRDS session."""

    def __init__(
        self,
        username: Optional[str] = None,
        cache_dir: Optional[str] = None,
        use_cache: bool = True,
        cache_ttl_hours: Optional[float] = None,
    ):
        self.username = username or os.environ.get("WRDS_USERNAME")
        # Default cache lives outside any synced folder (cloud-sync clients evict files and stall reads).
        self.cache_dir = Path(cache_dir or os.environ.get("WRDS_CACHE_DIR", Path.home() / ".cache" / "wrds"))
        self.use_cache = use_cache
        self.cache_ttl_hours = float(
            cache_ttl_hours if cache_ttl_hours is not None else os.environ.get("WRDS_CACHE_TTL_HOURS", 24)
        )
        self._db = None

    # ---------- connection ----------
    def _credentials(self):
        """(username, password or None, source). password None means libpq reads the pgpass file."""
        if pgpass_username():
            return self.username or pgpass_username(), None, str(PGPASS)
        env_pw = os.environ.get("WRDS_PASSWORD") or os.environ.get("PGPASSWORD")
        env_user = self.username or os.environ.get("PGUSER")
        if env_user and env_pw:
            return env_user, env_pw, "environment variables"
        raise WRDSSetupError(
            "No WRDS credentials. Locally: the user creates ~/.pgpass by running "
            "`python -c 'import wrds; wrds.Connection().create_pgpass_file()'` in their own Terminal. "
            "In a Claude Code cloud environment: the user sets WRDS_USERNAME and WRDS_PASSWORD in the "
            "environment's Environment variables. Never ask for the password in chat."
        )

    @staticmethod
    def check_network(timeout: float = 10.0) -> None:
        """Fail fast (instead of hanging) when WRDS's PostgreSQL port isn't reachable."""
        try:
            with socket.create_connection((WRDS_HOST, WRDS_PORT), timeout=timeout):
                return
        except OSError as e:
            raise WRDSSetupError(
                f"Can't reach {WRDS_HOST}:{WRDS_PORT} ({e}). On a Claude Code cloud environment this "
                "usually means the network access level or the HTTP-only egress proxy blocks PostgreSQL; "
                "run pulls on a local machine instead."
            ) from e

    def connect(self):
        if self._db is not None:
            return self._db
        user, password, source = self._credentials()
        self.check_network()
        import wrds  # imported here so cached runs work without a network

        # Standard wrds package connection only. Any multi-factor prompt (for example Duo) is approved by the user.
        kwargs = {"wrds_username": user}
        if password:
            kwargs["wrds_password"] = password
        _log(f"Connecting as {user} using {source} (approve any multi-factor prompt on your phone)...")
        try:
            db = wrds.Connection(**kwargs)
        except Exception as e:
            msg = str(e).splitlines()[0][:300] if str(e) else type(e).__name__
            if password and password in msg:
                msg = msg.replace(password, "***")
            raise WRDSSetupError(f"WRDS login failed ({msg}). Check the credential source ({source}).") from None
        self._db = db
        return self._db

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # ---------- core query ----------
    def _cache_path(self, sql: str, params) -> Path:
        key = hashlib.sha1((sql + json.dumps(params, sort_keys=True, default=str)).encode()).hexdigest()[:20]
        return self.cache_dir / f"{key}.pkl"

    def sql(self, sql: str, params: Optional[dict] = None, cache: bool = True, date_cols=None) -> pd.DataFrame:
        """Run parameterized SQL (psycopg2 style: %(name)s; use %% for a literal %)."""
        path = self._cache_path(sql, params)
        if cache and self.use_cache and path.exists():
            age_h = (time.time() - path.stat().st_mtime) / 3600
            if age_h <= self.cache_ttl_hours:
                try:
                    return pickle.loads(path.read_bytes())
                except Exception:   # written by a different Python/pandas version: re-query
                    pass
        db = self.connect()
        t0 = time.time()
        df = _to_numpy_dtypes(db.raw_sql(sql, params=params, date_cols=date_cols))
        _log(f"query returned {len(df):,} rows in {time.time() - t0:.1f}s")
        if cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(pickle.dumps(df))
        return df

    # ---------- data vintage ----------
    def latest_date(self, table: str, date_col: Optional[str] = None, as_of: Optional[str] = None) -> pd.Timestamp:
        """Latest date actually present in `table` on or before as_of (default today). Cached for the cache TTL."""
        col = date_col or DATASET_DATES[table]
        df = self.sql(f"select max({col}) as d from {table} where {col} <= %(d1)s",
                      {"d1": str(as_of or date.today())})
        return pd.Timestamp(df["d"].iloc[0])

    def table_columns(self, table: str) -> list:
        """Column names of lib.table (cached), used to request only the columns a table really has."""
        lib, tab = table.split(".")
        df = self.sql("select column_name from information_schema.columns "
                      "where table_schema = %(s)s and table_name = %(t)s", {"s": lib, "t": tab})
        return df["column_name"].tolist()

    def _select(self, table: str, wanted: list, alias: str = "f") -> tuple:
        have = set(self.table_columns(table))
        cols = [c for c in wanted if c in have]
        return ", ".join(f"{alias}.{c}" for c in cols), [c for c in wanted if c not in have]

    @staticmethod
    def _add_missing(df: pd.DataFrame, missing: list) -> pd.DataFrame:
        for c in missing:
            df[c] = np.nan
        return df

    def freshness(self, tables: Optional[Iterable[str]] = None) -> dict:
        """{table: latest date} for the key datasets, discovered live."""
        return {t: str(self.latest_date(t).date()) for t in (tables or DATASET_DATES)}

    # ---------- exploration ----------
    def libraries(self) -> list:
        return sorted(self.connect().list_libraries())

    def tables(self, library: str) -> list:
        return sorted(self.connect().list_tables(library=library))

    def describe(self, library: str, table: str) -> pd.DataFrame:
        return self.connect().describe_table(library=library, table=table)

    def columns(self, library: str, table: str, contains: Optional[str] = None) -> list:
        cols = [c["name"] for c in self.connect().insp.get_columns(table, schema=library)]
        return [c for c in cols if contains is None or contains.lower() in c.lower()]

    def sample(self, library: str, table: str, n: int = 5, columns: Optional[list] = None) -> pd.DataFrame:
        cols = ", ".join(columns) if columns else "*"
        return self.sql(f"select {cols} from {library}.{table} limit %(n)s", {"n": int(n)}, cache=False)

    # ---------- Compustat ----------
    def company_info(self, gvkeys: Optional[Iterable[str]] = None, region: str = "na") -> pd.DataFrame:
        """comp.company (region 'na') or comp_global_daily.g_company ('intl')."""
        lib, _, _, ctab, _, _, _ = REGIONS[region]
        sel, missing = self._select(f"{lib}.{ctab}", COMPANY_COLS)
        where, params = "", {}
        if gvkeys is not None:
            where, params = "where f.gvkey in %(g)s", {"g": tuple(gvkeys) or ("",)}
        df = self._add_missing(self.sql(f"select {sel} from {lib}.{ctab} f {where}", params), missing)
        df["sector"] = df["gsector"].map(GICS_SECTORS)
        return df

    def fundamentals_annual(
        self,
        start_year: int,
        end_year: Optional[int] = None,
        gvkeys: Optional[Iterable[str]] = None,
        columns: Optional[list] = None,
        max_datadate: Optional[str] = None,
        region: str = "na",
    ) -> pd.DataFrame:
        """Annual fundamentals with the standard filter. region 'na' = comp.funda, 'intl' = g_funda.

        Values are millions of the reporting currency `curcd` (convert with fx_to_usd). Columns a
        table lacks come back as NaN, so both regions share one schema.
        """
        lib, atab, _, _, _, std, _ = REGIONS[region]
        sel, missing = self._select(f"{lib}.{atab}", columns or FUNDA_COLS)
        where = [std, "f.fyear >= %(y0)s", "f.datadate <= %(dmax)s"]
        params = {"y0": int(start_year), "dmax": max_datadate or str(date.today())}
        if end_year:
            where.append("f.fyear <= %(y1)s")
            params["y1"] = int(end_year)
        if gvkeys is not None:
            where.append("f.gvkey in %(g)s")
            params["g"] = tuple(gvkeys) or ("",)
        sql = f"select {sel} from {lib}.{atab} f where {' and '.join(where)}"
        df = self._add_missing(self.sql(sql, params, date_cols=["datadate"]), missing)
        # Global reports net income as nicon and shares as cshoi; expose them under the NA names.
        for na_name, global_name in (("ni", "nicon"), ("csho", "cshoi")):
            if na_name in df and global_name in df:
                df[na_name] = pd.to_numeric(df[na_name], errors="coerce").fillna(
                    pd.to_numeric(df[global_name], errors="coerce"))
        if "ni" in df and "ib" in df:
            df["ni"] = df["ni"].fillna(pd.to_numeric(df["ib"], errors="coerce"))
        df["region"] = region
        return df

    def fundamentals_quarterly(
        self, start_date: str, gvkeys: Optional[Iterable[str]] = None, columns: Optional[list] = None,
        region: str = "na",
    ) -> pd.DataFrame:
        """comp.fundq (items end in q, year-to-date items in y, e.g. saleq, niq, oancfy)."""
        cols = columns or ["gvkey", "datadate", "fyearq", "fqtr", "rdq", "conm", "tic", "curcdq",
                           "saleq", "cogsq", "oibdpq", "oiadpq", "niq", "atq", "ceqq", "cheq", "dlttq",
                           "dlcq", "cshoq", "prccq", "oancfy", "capxy"]
        lib, _, qtab, _, _, std, _ = REGIONS[region]
        sel, missing = self._select(f"{lib}.{qtab}", cols)
        where = [std, "f.datadate >= %(d0)s", "f.datadate <= %(d1)s"]
        params = {"d0": start_date, "d1": str(date.today())}
        if gvkeys is not None:
            where.append("f.gvkey in %(g)s")
            params["g"] = tuple(gvkeys) or ("",)
        sql = f"select {sel} from {lib}.{qtab} f where {' and '.join(where)}"
        df = self._add_missing(self.sql(sql, params, date_cols=["datadate"]), missing)
        if "rdq" in df:
            df["rdq"] = pd.to_datetime(df["rdq"], errors="coerce")
        return df

    def latest_market_data(self, as_of: Optional[str] = None, window_days: int = 10,
                           gvkeys: Optional[Iterable[str]] = None, region: str = "na") -> pd.DataFrame:
        """Latest daily price and market cap per company from comp.secd ('na') or g_secd ('intl').

        Considers all primary issues (US, Canada, rest of world) and prefers an exchange-listed one
        over an OTC or non-traded line: Compustat marks the US OTC line of many Canadian companies
        (for example AtkinsRéalis SNCAF, WSP WSPOF) as the primary US issue. The window ends at the latest date present in the table
        (<= as_of) and reaches back `window_days` so thinly traded names still get a price.
        market_cap is in millions of the price currency `curcdd` (convert with fx_to_usd).
        """
        lib, _, _, ctab, stab, _, primary = REGIONS[region]
        end = self.latest_date(f"{lib}.{stab}", "datadate", as_of=as_of).date()
        params = {"d0": str(end - timedelta(days=window_days)), "d1": str(end)}
        have = set(self.table_columns(f"{lib}.{stab}"))
        qunit = "coalesce(nullif(s.qunit, 0), 1)" if "qunit" in have else "1"
        tic = "s.tic" if "tic" in have else "null"
        isin = "s.isin" if "isin" in have else "null"
        sedol = "s.sedol" if "sedol" in have else "null"
        extra = ""
        if gvkeys is not None:
            extra = "and s.gvkey in %(g)s"
            params["g"] = tuple(gvkeys) or ("",)
        sql = f"""
            select distinct on (s.gvkey)
                   s.gvkey, s.iid, s.datadate as px_date, {tic} as px_tic, {isin} as px_isin, {sedol} as px_sedol,
                   s.prccd / {qunit} as price, s.cshoc, s.curcdd, s.exchg,
                   s.prccd / {qunit} * s.cshoc / 1e6 as market_cap
            from {lib}.{stab} s
            join {lib}.{ctab} c on c.gvkey = s.gvkey and s.iid in (c.priusa, c.prican, c.prirow)
            where s.datadate between %(d0)s and %(d1)s
              and s.prccd is not null and s.cshoc is not null {extra}
            order by s.gvkey, s.datadate desc,
                     (case when s.exchg in (0, 1, 2, 3, 4, 13, 19) then 1 else 0 end), s.iid
        """
        df = self.sql(sql, params, date_cols=["px_date"])
        df["region"] = region
        return df

    def daily_prices(self, gvkeys: Iterable[str], lookback_days: int = 400, as_of: Optional[str] = None,
                     region: str = "na") -> pd.DataFrame:
        """Daily prices for specific companies' primary issues, ending at the latest date in the table.

        Returns gvkey, datadate, price (per share, in curcdd), ajexdi, trfd, cshtrd, curcdd.
        Total-return series = price / ajexdi * trfd.
        """
        lib, _, _, ctab, stab, _, primary = REGIONS[region]
        end = self.latest_date(f"{lib}.{stab}", "datadate", as_of=as_of).date()
        have = set(self.table_columns(f"{lib}.{stab}"))
        qunit = "coalesce(nullif(s.qunit, 0), 1)" if "qunit" in have else "1"
        sql = f"""
            select s.gvkey, s.datadate, s.prccd / {qunit} as price, s.ajexdi, s.trfd, s.cshtrd, s.curcdd
            from {lib}.{stab} s
            join {lib}.{ctab} c on c.gvkey = s.gvkey
            join (select s2.gvkey, min(s2.iid) as iid
                  from {lib}.{stab} s2 join {lib}.{ctab} c2 on c2.gvkey = s2.gvkey
                  where s2.gvkey in %(g)s and s2.datadate between %(d0)s and %(d1)s
                    and s2.iid in (c2.priusa, c2.prican, c2.prirow)
                    and s2.exchg not in (0, 1, 2, 3, 4, 13, 19)
                  group by s2.gvkey) p on p.gvkey = s.gvkey and p.iid = s.iid
            where s.gvkey in %(g)s and s.datadate between %(d0)s and %(d1)s and s.prccd is not null
            order by s.gvkey, s.datadate
        """
        params = {"g": tuple(gvkeys) or ("",), "d0": str(end - timedelta(days=lookback_days)), "d1": str(end)}
        return self.sql(sql, params, date_cols=["datadate"])

    def fx_to_usd(self, as_of: Optional[str] = None) -> pd.Series:
        """USD per 1 unit of each currency, from comp_global_daily.g_exrt_dly on its latest date <= as_of.

        Compustat quotes every rate against GBP (exratd = units of `tocurd` per 1 GBP), so
        USD per X = exratd[USD] / exratd[X].
        """
        d = self.latest_date("comp_global_daily.g_exrt_dly", as_of=as_of)
        fx = self.sql("select tocurd, exratd from comp_global_daily.g_exrt_dly "
                      "where datadate = %(d)s and fromcurd = 'GBP'", {"d": str(d.date())})
        rate = fx.set_index("tocurd")["exratd"].astype(float)
        rate["GBP"] = 1.0
        usd = rate["USD"] / rate
        usd.attrs["date"] = str(d.date())
        return usd

    def monthly_prices_compustat(self, start_date: str, gvkeys: Iterable[str]) -> pd.DataFrame:
        """comp.secm monthly prices; total-return index = prccm / ajexm * trfm."""
        sql = """
            select m.gvkey, m.iid, m.datadate, m.tic, m.prccm, m.ajexm, m.trfm, m.trt1m, m.cshoq, m.curcdm
            from comp.secm m join comp.company c on c.gvkey = m.gvkey and m.iid = coalesce(c.priusa, c.prican)
            where m.datadate between %(d0)s and %(d1)s and m.gvkey in %(g)s
        """
        return self.sql(sql, {"d0": start_date, "d1": str(date.today()), "g": tuple(gvkeys) or ("",)},
                        date_cols=["datadate"])

    # ---------- CRSP (CIZ / v2 format) ----------
    def ccm_links(self) -> pd.DataFrame:
        """gvkey <-> permno links (LU/LC, primary). Join where linkdt <= date <= linkenddt."""
        sql = """
            select gvkey, lpermno as permno, linktype, linkprim, linkdt,
                   coalesce(linkenddt, current_date) as linkenddt
            from crsp.ccmxpf_lnkhist
            where linktype in ('LU', 'LC') and linkprim in ('P', 'C') and lpermno is not null
        """
        return self.sql(sql, date_cols=["linkdt", "linkenddt"])

    def crsp_monthly(self, start_date: str, end_date: Optional[str] = None,
                     permnos: Optional[Iterable[int]] = None, common_stock_only: bool = True) -> pd.DataFrame:
        """crsp.msf_v2: mthret includes dividends and delisting returns; mthcap in $ thousands."""
        where = ["mthcaldt between %(d0)s and %(d1)s"]
        params = {"d0": start_date, "d1": end_date or str(date.today())}
        if common_stock_only:
            where.append(CRSP_COMMON_STOCK)
        if permnos is not None:
            where.append("permno in %(p)s")
            params["p"] = tuple(int(p) for p in permnos) or (0,)
        sql = f"""select permno, permco, mthcaldt, ticker, issuernm, siccd, primaryexch,
                         mthprc, mthret, mthretx, mthcap, shrout, mthvol
                  from crsp.msf_v2 where {' and '.join(where)}"""
        return self.sql(sql, params, date_cols=["mthcaldt"])

    def crsp_daily(self, start_date: str, end_date: str, permnos: Iterable[int]) -> pd.DataFrame:
        """crsp.dsf_v2 for specific permnos only (the table is huge)."""
        sql = """select permno, dlycaldt, ticker, dlyprc, dlyret, dlyretx, dlycap, dlyvol, shrout
                 from crsp.dsf_v2 where dlycaldt between %(d0)s and %(d1)s and permno in %(p)s"""
        return self.sql(sql, {"d0": start_date, "d1": end_date, "p": tuple(int(p) for p in permnos) or (0,)},
                        date_cols=["dlycaldt"])

    # ---------- WRDS Financial Ratios Suite ----------
    def fin_ratios(self, columns: Optional[list] = None, gvkeys: Optional[Iterable[str]] = None,
                   start_date: Optional[str] = None, latest_only: bool = True) -> pd.DataFrame:
        """wrdsapps_finratio.firm_ratio: ~70 monthly ratios (US, excludes financials). Date = public_date."""
        cols = ["gvkey", "permno", "public_date", "ticker"] + [c for c in (columns or ["bm", "pe_exi", "roe", "gpm", "npm", "de_ratio", "divyield", "mktcap"])
                                                              if c not in ("gvkey", "permno", "public_date", "ticker")]
        where = ["public_date <= %(d1)s"]
        params = {"d1": str(date.today())}
        if start_date:
            where.append("public_date >= %(d0)s")
            params["d0"] = start_date
        if gvkeys is not None:
            where.append("gvkey in %(g)s")
            params["g"] = tuple(gvkeys) or ("",)
        if latest_only:
            sql = (f"select distinct on (gvkey) {', '.join(cols)} from wrdsapps_finratio.firm_ratio "
                   f"where {' and '.join(where)} and gvkey is not null order by gvkey, public_date desc")
        else:
            sql = f"select {', '.join(cols)} from wrdsapps_finratio.firm_ratio where {' and '.join(where)}"
        return self.sql(sql, params, date_cols=["public_date"])

    # ---------- I/B/E/S ----------
    def ibes_consensus(self, fpi: str = "1", measure: str = "EPS", start_date: Optional[str] = None,
                       latest_only: bool = True, international: bool = False) -> pd.DataFrame:
        """I/B/E/S consensus (fpi '1' = current FY, '2' = next FY, '6' = next quarter).

        US firms: ibes.statsum_epsus, link on cusip: ibes.cusip == comp cusip[:8].
        international=True: ibes.statsum_epsint (non-US firms, estimates in local currency `curcode`);
        its `cusip` field holds a SEDOL-based id, link to Compustat Global via g_secd.sedol (see
        link_ibes_international in theme_exposure.py, which picks the matching key form from the data).
        IBES tickers are NOT exchange tickers.
        """
        # EPS lives in statsum_eps*; every other measure (SAL = sales, EBT = EBITDA, EBI = EBIT, ...; in
        # millions of `curcode`) lives in statsum_xeps*.
        stem = "statsum_eps" if measure == "EPS" else "statsum_xeps"
        table = f"ibes.{stem}{'int' if international else 'us'}"
        usfirm = 0 if international else 1
        latest = self.latest_date(table, "statpers").date()
        d0 = start_date or str(latest - timedelta(days=62))  # ~2 monthly consensus snapshots
        params = {"fpi": fpi, "m": measure, "d0": d0, "d1": str(latest)}
        sel = ("ticker, cusip, oftic, cname, statpers, fpedats, curcode, numest, meanest, medest, stdev, "
               "highest, lowest, numup, numdown, actual")
        base = (f"from {table} where fpi = %(fpi)s and measure = %(m)s and usfirm = {usfirm} "
                "and statpers between %(d0)s and %(d1)s")
        sql = (f"select distinct on (ticker) {sel} {base} order by ticker, statpers desc" if latest_only
               else f"select {sel} {base}")
        return self.sql(sql, params, date_cols=["statpers", "fpedats"])

    # ---------- Compustat segments and customers ----------
    def segments(self, stypes: Iterable[str] = ("BUSSEG", "OPSEG"), years_back: int = 3,
                 gvkeys: Optional[Iterable[str]] = None) -> pd.DataFrame:
        """Segment rows from comp_segments_hist_daily.wrds_segmerged (latest restatement of each period).

        stypes: BUSSEG / OPSEG (business lines: name `snms`, NAICS `naicss1`, SIC `sics1`, sales, ops =
        operating profit) or GEOSEG (regions: `snms`, `geotp` 2 = domestic, 3 = foreign). Values are
        millions of `curcds`. Coverage is strong for US filers and thin for Compustat Global firms.
        """
        table = "comp_segments_hist_daily.wrds_segmerged"
        end = self.latest_date(table).date()
        params = {"st": tuple(stypes), "d0": str(end - timedelta(days=365 * years_back + 31)), "d1": str(end)}
        extra = ""
        if gvkeys is not None:
            extra = "and gvkey in %(g)s"
            params["g"] = tuple(gvkeys) or ("",)
        sql = f"""
            select gvkey, stype, sid, snms, datadate, srcdate, curcds, geotp, naicss1, sics1,
                   sales, ops, oibdps, capxs, ias as assets
            from (select *, row_number() over (partition by gvkey, stype, sid, datadate order by srcdate desc) as rn
                  from {table}
                  where stype in %(st)s and datadate between %(d0)s and %(d1)s {extra}) x
            where rn = 1
        """
        return self.sql(sql, params, date_cols=["datadate", "srcdate"])

    def customers(self, years_back: int = 2, gvkeys: Optional[Iterable[str]] = None) -> pd.DataFrame:
        """Major customers disclosed by each company (seg_customer): supplier gvkey, customer name `cnms`,
        type `ctype` (COMPANY, GOVDOM, MARKET...), sales to that customer `salecs` ($mm). Use it to find
        second-order suppliers of an anchor company by matching `cnms`."""
        table = "comp_segments_hist_daily.seg_customer"
        end = self.latest_date(table).date()
        params = {"d0": str(end - timedelta(days=365 * years_back)), "d1": str(end)}
        extra = ""
        if gvkeys is not None:
            extra = "and gvkey in %(g)s"
            params["g"] = tuple(gvkeys) or ("",)
        sql = f"""select gvkey, cid, cnms, ctype, salecs, datadate from {table}
                  where datadate between %(d0)s and %(d1)s and cnms is not null {extra}"""
        return self.sql(sql, params, date_cols=["datadate"])

    # ---------- PitchBook (private companies & deals) ----------
    def pitchbook_companies(
        self,
        keywords: Optional[list] = None,
        countries: Optional[list] = None,
        industry_sectors: Optional[list] = None,
        ownership_status: Optional[list] = None,
        min_revenue: Optional[float] = None,
        last_financing_after: Optional[str] = None,
        columns: Optional[list] = None,
        limit: Optional[int] = None,
    ) -> pd.DataFrame:
        """Search pitchbk.company. keywords match description/keywords/verticals (case-insensitive, any).

        Money fields (revenue, totalraised, lastfinancingsize, lastfinancingvaluation) are USD millions.
        """
        cols = columns or [
            "companyid", "companyname", "ticker", "exchange", "cikcode", "hqcountry", "hqcity",
            "primaryindustrysector", "primaryindustrygroup", "primaryindustrycode", "verticals",
            "businessstatus", "ownershipstatus", "companyfinancingstatus", "yearfounded", "employees",
            "totalraised", "revenue", "ebitda", "netincome", "lastfinancingdate", "lastfinancingdealtype",
            "lastfinancingsize", "lastfinancingvaluation", "lastknownvaluation", "activeinvestors",
            "descriptionshort", "website",
        ]
        where, params = ["1=1"], {}
        if keywords:
            where.append("(description ilike any(%(kw)s) or keywords ilike any(%(kw)s) or verticals ilike any(%(kw)s))")
            params["kw"] = [f"%{k}%" for k in keywords]
        if countries:
            where.append("hqcountry in %(ctry)s")
            params["ctry"] = tuple(countries)
        if industry_sectors:
            where.append("primaryindustrysector in %(sect)s")
            params["sect"] = tuple(industry_sectors)
        if ownership_status:
            where.append("ownershipstatus in %(own)s")
            params["own"] = tuple(ownership_status)
        if min_revenue is not None:
            where.append("revenue >= %(minrev)s")
            params["minrev"] = float(min_revenue)
        if last_financing_after:
            where.append("lastfinancingdate >= %(lfa)s")
            params["lfa"] = last_financing_after
        sql = f"select {', '.join(cols)} from pitchbk.company where {' and '.join(where)}"
        if limit:
            sql += f" limit {int(limit)}"
        return self.sql(sql, params)

    def pitchbook_deals(self, companyids: Optional[Iterable[str]] = None, start_date: Optional[str] = None,
                        deal_types: Optional[list] = None, columns: Optional[list] = None,
                        limit: Optional[int] = None) -> pd.DataFrame:
        cols = columns or ["dealid", "companyid", "companyname", "dealdate", "dealtype", "dealtype2",
                           "dealclass", "dealstatus", "dealsize", "premoneyvaluation", "postvaluation",
                           "vcround", "investors", "revenue", "ebitda", "valuation_revenue", "impliedev_ebitda"]
        where, params = ["dealdate <= %(d1)s"], {"d1": str(date.today())}
        if companyids is not None:
            where.append("companyid in %(c)s")
            params["c"] = tuple(companyids) or ("",)
        if start_date:
            where.append("dealdate >= %(d0)s")
            params["d0"] = start_date
        if deal_types:
            where.append("dealtype in %(dt)s")
            params["dt"] = tuple(deal_types)
        sql = f"select {', '.join(cols)} from pitchbk.deal where {' and '.join(where)}"
        if limit:
            sql += f" limit {int(limit)}"
        return self.sql(sql, params, date_cols=["dealdate"])


if __name__ == "__main__":
    # Connectivity check: python wrds_client.py [--network-only]
    if "--network-only" in sys.argv:
        WRDS.check_network()
        print(f"Network OK: {WRDS_HOST}:{WRDS_PORT} is reachable.")
    else:
        with WRDS(use_cache=False) as w:
            print(f"Connected. {len(w.libraries())} libraries visible.")
            print("Latest dates:", w.freshness(["comp.funda", "comp.secd", "comp_global_daily.g_funda"]))
