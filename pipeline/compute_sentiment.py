#!/usr/bin/env python3
"""Phase 1, Step 4 — Loughran-McDonald sentiment per utterance.

Counts positive / negative / uncertainty / litigious / constraining words in
each utterance using the Loughran-McDonald Master Dictionary, then writes the
sentiment_facts table.

The dictionary is a CSV with one row per word and a column per category; a
non-zero value in a category column means the word belongs to that category.
Download it from https://sraf.nd.edu/loughran-mcdonald-master-dictionary/ and
place the CSV under ./data/ (any name containing "Master" and "Dictionary"),
or point LM_DICT at it explicitly. ./data/ is gitignored, so the file stays
out of version control.

Usage:
    python pipeline/compute_sentiment.py
    LM_DICT=/path/to/LM_MasterDictionary.csv python pipeline/compute_sentiment.py
"""

from __future__ import annotations

import csv
import os
import re
import sys
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "subtext.duckdb"

CATEGORIES = ("positive", "negative", "uncertainty", "litigious", "constraining")
TOKEN_RE = re.compile(r"[A-Za-z']+")
BATCH = 20000  # utterances per read/write batch


def find_dictionary() -> Path:
    env = os.environ.get("LM_DICT")
    if env:
        p = Path(env)
        if not p.exists():
            sys.exit(f"ERROR: LM_DICT={env} does not exist.")
        return p
    # Look for a Master Dictionary CSV under ./data/.
    candidates = sorted(DATA_DIR.glob("*.csv"))
    for p in candidates:
        name = p.name.lower()
        if "master" in name and "dictionar" in name:
            return p
    for p in candidates:
        if "loughran" in p.name.lower() or p.name.lower().startswith("lm"):
            return p
    sys.exit(
        "ERROR: Loughran-McDonald Master Dictionary CSV not found.\n"
        "Download it from "
        "https://sraf.nd.edu/loughran-mcdonald-master-dictionary/\n"
        "and place it under ./data/ (or set LM_DICT=/path/to/dictionary.csv)."
    )


def load_category_sets(path: Path) -> dict[str, set[str]]:
    """Read the LM CSV into a set of words per sentiment category."""
    sets: dict[str, set[str]] = {c: set() for c in CATEGORIES}
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        # Map our category -> the actual column name (case-insensitive).
        colmap = {}
        lower = {h.lower(): h for h in (reader.fieldnames or [])}
        word_col = lower.get("word")
        if not word_col:
            sys.exit(f"ERROR: no 'Word' column in {path.name}: {reader.fieldnames}")
        for cat in CATEGORIES:
            if cat in lower:
                colmap[cat] = lower[cat]
        missing = [c for c in CATEGORIES if c not in colmap]
        if missing:
            print(f"  WARNING: dictionary lacks columns for {missing}")
        for r in reader:
            word = (r.get(word_col) or "").strip().upper()
            if not word:
                continue
            for cat, col in colmap.items():
                val = (r.get(col) or "0").strip()
                if val and val not in ("0", "0.0", ""):
                    sets[cat].add(word)
    for cat in CATEGORIES:
        print(f"  {cat:<13} {len(sets[cat]):>6,} words")
    return sets


def score_text(text: str, sets: dict[str, set[str]]) -> tuple:
    tokens = TOKEN_RE.findall(text.upper()) if text else []
    total_words = len(tokens)
    counts = {c: 0 for c in CATEGORIES}
    lm_hits = 0
    for tok in tokens:
        hit = False
        for cat in CATEGORIES:
            if tok in sets[cat]:
                counts[cat] += 1
                hit = True
        if hit:
            lm_hits += 1
    net = (
        (counts["positive"] - counts["negative"]) / total_words if total_words else 0.0
    )
    return (
        counts["positive"],
        counts["negative"],
        counts["uncertainty"],
        counts["litigious"],
        counts["constraining"],
        lm_hits,
        total_words,
        net,
    )


def main() -> int:
    dict_path = find_dictionary()
    print(f"Loading Loughran-McDonald dictionary: {dict_path}")
    sets = load_category_sets(dict_path)

    con = duckdb.connect(str(DB_PATH))
    con.execute("DELETE FROM sentiment_facts")

    # Export the word lists so the web app can highlight sentiment words inline
    # without needing the dictionary CSV at runtime.
    con.execute("CREATE OR REPLACE TABLE lm_words (word VARCHAR, category VARCHAR)")
    word_rows = [(w, cat) for cat in CATEGORIES for w in sets[cat]]
    if word_rows:
        con.executemany("INSERT INTO lm_words VALUES (?,?)", word_rows)
    print(f"Exported {len(word_rows):,} lm_words rows.")

    total = con.execute("SELECT COUNT(*) FROM utterances").fetchone()[0]
    print(f"\nScoring {total:,} utterances ...")

    done = 0
    offset = 0
    while True:
        rows = con.execute(
            "SELECT utterance_id, text FROM utterances "
            "ORDER BY utterance_id LIMIT ? OFFSET ?",
            [BATCH, offset],
        ).fetchall()
        if not rows:
            break
        facts = []
        for uid, text in rows:
            s = score_text(text or "", sets)
            facts.append((uid, *s))
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _s "
            "(utterance_id VARCHAR, positive_count INTEGER, "
            " negative_count INTEGER, uncertainty_count INTEGER, "
            " litigious_count INTEGER, constraining_count INTEGER, "
            " total_lm_words INTEGER, total_words INTEGER, net_sentiment FLOAT)"
        )
        con.executemany("INSERT INTO _s VALUES (?,?,?,?,?,?,?,?,?)", facts)
        con.execute("INSERT INTO sentiment_facts SELECT * FROM _s")
        done += len(rows)
        offset += BATCH
        print(f"  ...{done:,}/{total:,}")

    summary = con.execute(
        "SELECT COUNT(*), AVG(net_sentiment), "
        "SUM(positive_count), SUM(negative_count) FROM sentiment_facts"
    ).fetchone()
    con.close()
    print(
        f"\nWrote {summary[0]:,} sentiment rows. "
        f"Mean net_sentiment={summary[1]:.5f}, "
        f"total positive={summary[2]:,}, total negative={summary[3]:,}"
    )
    print("Sentiment complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
