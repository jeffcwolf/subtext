#!/usr/bin/env python3
"""Phase 1, Step 5 — build the full-text search index.

Creates a DuckDB FTS (BM25) index over utterances.text so the Rust app's
/search route can rank utterances by relevance.

The `fts` extension may need to be installed from the DuckDB extension
repository on first use, which requires network access. If that is blocked the
script prints how to install it offline and exits non-zero so the failure is
visible, without corrupting the rest of the database.

Usage:
    python ingest/build_indices.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "subtext.duckdb"


def main() -> int:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run build_schema.py first.")

    con = duckdb.connect(str(DB_PATH))
    n = con.execute("SELECT COUNT(*) FROM utterances").fetchone()[0]
    if n == 0:
        print("WARNING: utterances is empty; run load_transcripts.py first.")

    print("Installing/loading the DuckDB `fts` extension ...")
    try:
        con.execute("INSTALL fts")
        con.execute("LOAD fts")
    except duckdb.Error as exc:
        con.close()
        sys.exit(
            "ERROR: could not install the `fts` extension "
            f"(likely no network access):\n  {exc}\n"
            "Install it once in an environment with access "
            "(`INSTALL fts;`) — DuckDB caches extensions under "
            "~/.duckdb/extensions — or copy that cache into place."
        )

    print(f"Building BM25 FTS index over {n:,} utterances ...")
    # Porter stemmer + english stopwords is a sensible default for prose.
    con.execute(
        "PRAGMA create_fts_index("
        "'utterances', 'utterance_id', 'text', "
        "stemmer='porter', stopwords='english', overwrite=1)"
    )

    # Smoke-test the index with a BM25 query.
    try:
        probe = con.execute(
            "SELECT utterance_id, "
            "fts_main_utterances.match_bm25(utterance_id, 'revenue growth') AS score "
            "FROM utterances "
            "WHERE score IS NOT NULL "
            "ORDER BY score DESC LIMIT 3"
        ).fetchall()
        print(f"Index ready. Sample BM25 hits for 'revenue growth': {len(probe)}")
        for uid, score in probe:
            print(f"  {uid}  score={score:.4f}")
    except duckdb.Error as exc:
        print(f"  (index built; probe query skipped: {exc})")

    con.close()
    print("FTS index complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
