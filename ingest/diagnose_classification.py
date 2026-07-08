#!/usr/bin/env python3
"""Diagnostic aid for tuning speaker/section classification.

Reads the already-built ./data/subtext.duckdb (fast; no re-ingest) and surfaces
WHY the heuristics miss, so the intro-parsing and Q&A rules can be tuned against
real data instead of guesswork:

  1. operator Q&A-routing lines  -> to tune analyst-name extraction
  2. transcripts with NO CEO      -> shows the intro so we see why it missed
  3. top "Analyst" speakers       -> management leaking into Analyst shows up as
                                     a name concentrated in a single ticker

Usage:
    python ingest/diagnose_classification.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "subtext.duckdb"
RULE = "=" * 78


def main() -> int:
    if not DB_PATH.exists():
        sys.exit(f"ERROR: {DB_PATH} not found. Run the ingest first.")
    con = duckdb.connect(str(DB_PATH), read_only=True)

    print(RULE)
    print("1. OPERATOR Q&A-ROUTING LINES (how analysts are announced)")
    print(RULE)
    rows = con.execute(
        """
        SELECT DISTINCT text FROM utterances
        WHERE speaker_role = 'Operator'
          AND (text ILIKE '%from the line of%'
               OR text ILIKE '%next question%'
               OR text ILIKE '%question comes from%'
               OR text ILIKE '%your line is open%'
               OR text ILIKE '%question is from%')
        LIMIT 15
        """
    ).fetchall()
    for (t,) in rows:
        print(f"  - {t[:200].strip()}")

    print("\n" + RULE)
    print("2. TRANSCRIPTS WITH NO CEO IDENTIFIED — intro (first 6 utterances)")
    print(RULE)
    tids = con.execute(
        """
        SELECT t.transcript_id, t.ticker
        FROM transcripts t
        WHERE t.transcript_id NOT IN (
            SELECT transcript_id FROM utterances WHERE speaker_role = 'CEO'
        )
        ORDER BY t.transcript_id
        LIMIT 4
        """
    ).fetchall()
    for tid, ticker in tids:
        print(f"\n  --- {ticker}  {tid} ---")
        intro = con.execute(
            """
            SELECT sequence_order, section, speaker_role, speaker_name,
                   LEFT(text, 240)
            FROM utterances WHERE transcript_id = ? AND sequence_order < 6
            ORDER BY sequence_order
            """,
            [tid],
        ).fetchall()
        for seq, section, role, spk, text in intro:
            print(f"   [{seq}] {section}/{role} | {spk!r}")
            print(f"        {text.strip()!r}")

    print("\n" + RULE)
    print("3. TOP 'Analyst' SPEAKERS — a name concentrated in ONE ticker is")
    print("   almost certainly management mislabeled as an analyst")
    print(RULE)
    rows = con.execute(
        """
        SELECT u.speaker_name,
               COUNT(*)                         AS utterances,
               COUNT(DISTINCT u.transcript_id)  AS calls,
               COUNT(DISTINCT t.ticker)         AS tickers
        FROM utterances u
        JOIN transcripts t USING (transcript_id)
        WHERE u.speaker_role = 'Analyst'
          AND u.speaker_name NOT ILIKE '%analyst%'
          AND u.speaker_name NOT ILIKE '%unidentified%'
        GROUP BY 1
        ORDER BY utterances DESC
        LIMIT 30
        """
    ).fetchall()
    print(f"  {'speaker':<28} {'utts':>7} {'calls':>6} {'tickers':>8}")
    for spk, utt, calls, tickers in rows:
        flag = "  <- likely mgmt" if tickers == 1 else ""
        print(f"  {spk[:27]:<28} {utt:>7,} {calls:>6,} {tickers:>8,}{flag}")

    # A quick quantification: how much 'Analyst' volume sits in single-ticker names.
    split = con.execute(
        """
        WITH a AS (
            SELECT u.speaker_name, COUNT(*) utt, COUNT(DISTINCT t.ticker) tickers
            FROM utterances u JOIN transcripts t USING (transcript_id)
            WHERE u.speaker_role = 'Analyst'
              AND u.speaker_name NOT ILIKE '%analyst%'
              AND u.speaker_name NOT ILIKE '%unidentified%'
            GROUP BY 1
        )
        SELECT
          SUM(CASE WHEN tickers = 1 THEN utt ELSE 0 END) AS single_ticker,
          SUM(utt)                                       AS total
        FROM a
        """
    ).fetchone()
    if split and split[1]:
        pct = 100.0 * (split[0] or 0) / split[1]
        print(f"\n  Named-analyst utterances tied to a single ticker: "
              f"{split[0]:,}/{split[1]:,} ({pct:.1f}%) "
              f"— an estimate of management mislabeled as analysts.")

    con.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
