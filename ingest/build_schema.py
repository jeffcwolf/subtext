#!/usr/bin/env python3
"""Phase 1, Step 2 — build the DuckDB schema.

Creates ``./data/subtext.duckdb`` with the four MVP tables defined in
CLAUDE.md: companies, transcripts, utterances, sentiment_facts. Uses
``CREATE OR REPLACE`` so the step is idempotent — re-running it resets the
schema without touching any other file.

Usage:
    python ingest/build_schema.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "subtext.duckdb"

# Schema is copied verbatim from CLAUDE.md (the MVP contract), with
# CREATE OR REPLACE for idempotent re-runs.
SCHEMA = """
CREATE OR REPLACE TABLE companies (
    ticker VARCHAR PRIMARY KEY,
    name VARCHAR,
    sector VARCHAR,       -- from glopardo (nullable; coverage doesn't fully overlap)
    industry VARCHAR,     -- from glopardo
    cik VARCHAR           -- SEC CIK from glopardo (hook for Edgar cross-reference)
);

CREATE OR REPLACE TABLE transcripts (
    transcript_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    call_date DATE,
    fiscal_quarter VARCHAR,
    fiscal_year INTEGER
);

CREATE OR REPLACE TABLE utterances (
    utterance_id VARCHAR PRIMARY KEY,
    transcript_id VARCHAR,
    section VARCHAR,          -- 'prepared_remarks', 'qa_question', 'qa_response', 'operator', 'other'
    speaker_name VARCHAR,
    speaker_role VARCHAR,     -- 'CEO', 'CFO', 'COO', 'IR', 'Analyst', 'Operator', 'Other'
    sequence_order INTEGER,
    text TEXT,
    word_count INTEGER
);

CREATE OR REPLACE TABLE sentiment_facts (
    utterance_id VARCHAR,
    positive_count INTEGER,
    negative_count INTEGER,
    uncertainty_count INTEGER,
    litigious_count INTEGER,
    constraining_count INTEGER,
    total_lm_words INTEGER,
    total_words INTEGER,
    net_sentiment FLOAT
);

-- glopardo financial metrics, matched per transcript by ticker + nearest
-- earnings date (see load_glopardo.py). Valuation/estimate figures, not
-- beat/miss: trailing-12m EPS, forward-12m EPS estimate, forward P/E.
CREATE OR REPLACE TABLE financials (
    transcript_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    earnings_date DATE,
    eps_ttm DOUBLE,
    eps_fwd DOUBLE,
    pe_fwd DOUBLE
);
"""


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creating schema in {DB_PATH} ...")
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute(SCHEMA)
        tables = [r[0] for r in con.execute("SHOW TABLES").fetchall()]
        print(f"Tables now present: {tables}")
        for table in ("companies", "transcripts", "utterances", "sentiment_facts", "financials"):
            cols = con.execute(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = ? ORDER BY ordinal_position",
                [table],
            ).fetchall()
            print(f"\n  {table}:")
            for name, dtype in cols:
                print(f"    {name:<18} {dtype}")
    finally:
        con.close()
    print("\nSchema built.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
