#!/usr/bin/env python3
"""Explore the glopardo dataset (the financial-metrics supplement).

Schema-agnostic on purpose — CLAUDE.md's description of a dataset has not matched
reality so far, so this prints whatever is actually there: columns/types, record
count, a couple of full sample records, and — importantly — the likely key
columns (ticker / date / quarter / year) and financial columns (EPS / P/E /
price) with basic stats, so we can see how to join glopardo to the kurry-derived
`transcripts` table.

Usage:
    python ingest/explore_glopardo.py          # or: uv run python ...
    SUBTEXT_SAMPLE=2000 python ingest/explore_glopardo.py
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
GLOPARDO_DIR = DATA_DIR / "glopardo_transcripts"
DATASET_ID = "glopardo/sp500-earnings-transcripts"
SAMPLE = int(os.environ.get("SUBTEXT_SAMPLE", "4000"))
RULE = "=" * 78


def header(t: str) -> None:
    print(f"\n{RULE}\n{t}\n{RULE}")


def load():
    import datasets
    from datasets import load_dataset, load_from_disk, Dataset, DatasetDict

    print(f"Python:   {sys.executable}")
    print(f"datasets: {datasets.__version__}")
    if GLOPARDO_DIR.exists():
        print(f"Loading local dataset from {GLOPARDO_DIR} ...")
        try:
            ds = load_from_disk(str(GLOPARDO_DIR))
        except ValueError as exc:
            if "Feature type" in str(exc) and "not found" in str(exc):
                sys.exit(
                    f"\nERROR: this `datasets` ({datasets.__version__}) is too old "
                    "to read the saved dataset.\nUse the project venv "
                    "(datasets>=5.0.0):  source .venv/bin/activate\n"
                    f"(original error: {exc})"
                )
            raise
    else:
        print(f"No local copy at {GLOPARDO_DIR}; downloading '{DATASET_ID}' ...")
        ds = load_dataset(DATASET_ID)

    if isinstance(ds, DatasetDict):
        print(f"Splits found: {list(ds.keys())}")
        if len(ds) == 1:
            ds = next(iter(ds.values()))
        else:
            from datasets import concatenate_datasets
            ds = concatenate_datasets(list(ds.values()))
    assert isinstance(ds, Dataset)
    return ds


def looks_like(name: str, needles) -> bool:
    n = name.lower()
    return any(k in n for k in needles)


def main() -> int:
    ds = load()
    cols = ds.column_names
    n = ds.num_rows

    header("SCHEMA / FEATURES")
    print(f"Total records: {n:,}")
    print(f"Columns ({len(cols)}): {cols}\n")
    for name, feat in ds.features.items():
        print(f"  {name:<24} {feat}")

    # Classify columns by name.
    key_cols = [c for c in cols if looks_like(c, ("ticker", "symbol", "cik"))]
    date_cols = [c for c in cols if looks_like(c, ("date", "day"))]
    period_cols = [c for c in cols if looks_like(c, ("quarter", "fiscal", "period", "year", "qtr"))]
    fin_cols = [c for c in cols if looks_like(
        c, ("eps", "p/e", "pe", "price", "earning", "ratio", "revenue",
            "estimate", "actual", "surprise", "market", "cap"))]
    text_cols = [c for c in cols if looks_like(c, ("transcript", "text", "content", "body"))]

    header("SAMPLE RECORDS (rows 0 and 1)")
    for idx in range(min(2, n)):
        print(f"\n--- row {idx} ---")
        row = ds[idx]
        for key in cols:
            v = row[key]
            if isinstance(v, str) and len(v) > 220:
                print(f"  {key}: ({len(v)} chars) {v[:220]!r} …")
            elif isinstance(v, list):
                print(f"  {key}: list of {len(v)} items"
                      + (f"; first item keys: {list(v[0].keys())}"
                         if v and isinstance(v[0], dict) else ""))
            else:
                print(f"  {key}: {v!r}")

    header("KEY / PERIOD COLUMNS (how to join to `transcripts`)")
    print(f"Ticker-ish columns:  {key_cols}")
    print(f"Date-ish columns:    {date_cols}")
    print(f"Period-ish columns:  {period_cols}")
    print(f"Text/transcript cols:{text_cols}")

    for c in key_cols:
        vals = ds[c]
        uniq = len(set(v for v in vals if v is not None))
        print(f"\n  {c}: {uniq:,} distinct; examples: "
              f"{list(dict.fromkeys(v for v in vals if v is not None))[:8]}")
    for c in date_cols:
        vals = [str(v) for v in ds[c] if v is not None]
        if vals:
            print(f"  {c}: range {min(vals)} → {max(vals)}")
    for c in period_cols:
        cnt = Counter(str(v) for v in ds[c] if v is not None)
        print(f"  {c}: {dict(sorted(cnt.items())[:12])}"
              + (" …" if len(cnt) > 12 else ""))

    header("FINANCIAL COLUMNS (the supplement value)")
    if not fin_cols:
        print("  No obviously-financial columns by name — inspect the sample "
              "records above and tell me which columns hold EPS / P/E.")
    for c in fin_cols:
        vals = [v for v in ds[c] if isinstance(v, (int, float))]
        nulls = n - len(vals)
        if vals:
            vals_sorted = sorted(vals)
            mid = vals_sorted[len(vals_sorted) // 2]
            print(f"  {c:<20} type={ds.features[c]}  n={len(vals):,} nulls={nulls:,}  "
                  f"min={min(vals):.4g} median={mid:.4g} max={max(vals):.4g}")
        else:
            ex = [v for v in ds[c][:5]]
            print(f"  {c:<20} type={ds.features[c]}  (non-numeric) examples={ex}")

    header("NOTES")
    print(
        "To integrate, I need: the EPS and P/E column names, the ticker column,\n"
        "and how the fiscal period is identified (a quarter+year, or a date).\n"
        "Then I can build a `financials` table keyed to (ticker, fiscal_year,\n"
        "fiscal_quarter) and surface EPS/P/E next to sentiment."
    )
    print("\nExploration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
