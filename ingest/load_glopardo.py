#!/usr/bin/env python3
"""Load glopardo financial metrics and enrich companies.

The glopardo dataset (glopardo/sp500-earnings-transcripts) carries quarterly
valuation/estimate figures — trailing-12m EPS, forward-12m EPS estimate, and
forward P/E — plus sector / industry / CIK, which the kurry transcripts lack.

This step:
  * enriches `companies` with sector, industry, and cik (matched by ticker);
  * matches each kurry transcript to the nearest glopardo row for the same
    ticker (by earnings date vs call date, within a tolerance) and writes the
    three financial figures into the `financials` table keyed by transcript_id.

We deliberately ignore glopardo's own transcript text — it is a single
unsegmented blob; kurry's speaker-segmented content is what the app analyses.

Usage:
    python ingest/load_glopardo.py        # or: uv run python ...
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GLOPARDO_DIR = DATA_DIR / "glopardo_transcripts"
DB_PATH = DATA_DIR / "subtext.duckdb"

# A transcript is matched to the glopardo row whose earnings_date is closest to
# the call date, but only within this window (quarters are ~90 days apart, so
# this is safely unambiguous while tolerating reporting-date discrepancies).
MATCH_TOLERANCE_DAYS = 30


def load_glopardo():
    import datasets
    from datasets import Dataset, DatasetDict, load_from_disk

    print(f"Python: {sys.executable} | datasets: {datasets.__version__}")
    if not GLOPARDO_DIR.exists():
        print(
            f"WARNING: no glopardo dataset at {GLOPARDO_DIR}; skipping financials.\n"
            "Download glopardo/sp500-earnings-transcripts and save it there to "
            "enable EPS/P/E and sector data.",
            file=sys.stderr,
        )
        return None
    try:
        ds = load_from_disk(str(GLOPARDO_DIR))
    except ValueError as exc:
        if "Feature type" in str(exc) and "not found" in str(exc):
            sys.exit(
                f"\nERROR: this `datasets` ({datasets.__version__}) is too old to "
                "read the saved dataset. Use the project venv (datasets>=5.0.0):\n"
                "    source .venv/bin/activate\n"
                f"(original error: {exc})"
            )
        raise
    if isinstance(ds, DatasetDict):
        from datasets import concatenate_datasets

        ds = ds[next(iter(ds))] if len(ds) == 1 else concatenate_datasets(
            list(ds.values())
        )
    assert isinstance(ds, Dataset)
    # Drop the large transcript blob; we only need the metadata + financials.
    drop = [c for c in ("transcript",) if c in ds.column_names]
    return ds.remove_columns(drop) if drop else ds


def parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def main() -> int:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run build_schema.py first.")

    ds = load_glopardo()
    if ds is None:
        return 0

    cols = ds.column_names
    n = ds.num_rows
    print(f"glopardo rows: {n:,}")

    def col(name):
        return ds[name] if name in cols else [None] * n

    tickers = col("ticker")
    sectors, industries, ciks = col("sector"), col("industry"), col("cik")
    edates = col("earnings_date")
    eps_ttm = col("eps12mtrailing_eoq")
    eps_fwd = col("eps12mfwd_eoq")
    pe_fwd = col("peforw_eoq")

    # ticker -> (sector, industry, cik) and ticker -> sorted [(date, e_ttm, e_fwd, pe)]
    meta: dict[str, tuple] = {}
    by_ticker: dict[str, list] = {}
    for i in range(n):
        t = tickers[i]
        if not t:
            continue
        if t not in meta:
            cik = ciks[i]
            meta[t] = (sectors[i], industries[i],
                       str(int(cik)) if cik is not None else None)
        d = parse_date(edates[i])
        if d is not None:
            by_ticker.setdefault(t, []).append((d, eps_ttm[i], eps_fwd[i], pe_fwd[i]))
    for rows in by_ticker.values():
        rows.sort(key=lambda r: r[0])

    con = duckdb.connect(str(DB_PATH))
    con.execute("DELETE FROM financials")

    # --- enrich companies ---
    con.execute(
        "CREATE OR REPLACE TEMP TABLE _meta "
        "(ticker VARCHAR, sector VARCHAR, industry VARCHAR, cik VARCHAR)"
    )
    con.executemany(
        "INSERT INTO _meta VALUES (?,?,?,?)",
        [(t, s, ind, c) for t, (s, ind, c) in meta.items()],
    )
    con.execute(
        "UPDATE companies SET sector = _meta.sector, industry = _meta.industry, "
        "cik = _meta.cik FROM _meta WHERE companies.ticker = _meta.ticker"
    )
    total_co = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    enriched = con.execute(
        "SELECT COUNT(*) FROM companies WHERE sector IS NOT NULL"
    ).fetchone()[0]

    # --- match transcripts to nearest earnings date ---
    transcripts = con.execute(
        "SELECT transcript_id, ticker, call_date FROM transcripts"
    ).fetchall()
    fin_rows = []
    no_ticker = 0
    for tid, tk, call_date in transcripts:
        rows = by_ticker.get(tk)
        if not rows or call_date is None:
            if rows is None:
                no_ticker += 1
            continue
        best = None
        best_diff = None
        for r in rows:
            diff = abs((call_date - r[0]).days)
            if best_diff is None or diff < best_diff:
                best_diff, best = diff, r
        if best is not None and best_diff <= MATCH_TOLERANCE_DAYS:
            fin_rows.append((tid, tk, best[0].isoformat(), best[1], best[2], best[3]))

    con.execute(
        "CREATE OR REPLACE TEMP TABLE _fin (transcript_id VARCHAR, ticker VARCHAR, "
        "earnings_date VARCHAR, eps_ttm DOUBLE, eps_fwd DOUBLE, pe_fwd DOUBLE)"
    )
    con.executemany("INSERT INTO _fin VALUES (?,?,?,?,?,?)", fin_rows)
    con.execute(
        "INSERT INTO financials SELECT transcript_id, ticker, "
        "TRY_CAST(earnings_date AS DATE), eps_ttm, eps_fwd, pe_fwd FROM _fin"
    )
    total_tr = len(transcripts)
    con.close()

    pct = 100.0 * len(fin_rows) / total_tr if total_tr else 0.0
    print(f"\nCompanies enriched with sector/industry/CIK: {enriched:,}/{total_co:,}")
    print(f"Glopardo tickers: {len(by_ticker):,}")
    print(f"Transcripts matched to financials: {len(fin_rows):,}/{total_tr:,} "
          f"({pct:.1f}%)")
    print(f"  (transcripts whose ticker isn't in glopardo: {no_ticker:,})")
    print("Glopardo load complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
