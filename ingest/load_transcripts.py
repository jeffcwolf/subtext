#!/usr/bin/env python3
"""Phase 1, Step 3 — parse, classify, and load transcripts into DuckDB.

Reads the kurry transcripts from ``./data/kurry_transcripts/`` and populates the
companies, transcripts, and utterances tables created by ``build_schema.py``.

Classification design
---------------------
Speaker role (CEO / CFO / COO / IR / Analyst / Operator / Other):
  Titles are usually stated once, when a speaker is introduced in the prepared
  remarks ("Tim Cook - Chief Executive Officer"). In the Q&A the same person
  often reappears with just a name. So we make two passes: pass 1 learns a
  name -> role map from any segment whose label carries a title/firm; pass 2
  assigns each segment a role from its own label, falling back to the learned
  map, and finally to "Analyst" if the speaker turns up unlabeled inside the
  Q&A (analysts are the unlabeled Q&A voices) or "Other" otherwise.

Section (prepared_remarks / qa_question / qa_response / operator / other):
  The operator announces the Q&A ("we will now begin the question-and-answer
  session"). Everything at/after that marker is the Q&A. Then: operator ->
  operator; analyst -> qa_question; management before the marker ->
  prepared_remarks; management at/after -> qa_response.

Usage:
    python ingest/load_transcripts.py
    SUBTEXT_LIMIT=500 python ingest/load_transcripts.py   # load a subset
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KURRY_DIR = DATA_DIR / "kurry_transcripts"
DB_PATH = DATA_DIR / "subtext.duckdb"

# Flush to DuckDB every this many transcripts to bound memory.
BATCH_TRANSCRIPTS = 3000
# Optional cap for quick runs.
LIMIT = int(os.environ.get("SUBTEXT_LIMIT", "0"))

# Separators between a speaker's name and their title/firm.
NAME_SEP_RE = re.compile(r"\s+[-–—]{1,2}\s+|\s*[,(]\s*")

# Firms/roles that mark an analyst. Deliberately broad; refine against the
# speaker survey from explore_data.py once real data is available.
FIRM_RE = re.compile(
    r"\b(goldman|morgan stanley|jpmorgan|j\.?p\.? morgan|bofa|bank of america|"
    r"barclays|citi(group)?|credit suisse|ubs|wells fargo|deutsche|jefferies|"
    r"evercore|cowen|raymond james|piper|wolfe|bernstein|rbc|mizuho|baird|"
    r"stifel|guggenheim|truist|oppenheimer|needham|canaccord|keybanc|"
    r"macquarie|nomura|hsbc|scotiabank|td securities|bmo|"
    r"securities|research|capital|partners|& co\.?|analyst)\b",
    re.IGNORECASE,
)

QA_TRANSITION_RE = re.compile(
    r"question[- ]and[- ]answer|question[- ]&[- ]answer|"
    r"we('| wi)ll now (begin|take|open|move to).{0,40}question|"
    r"(begin|open|start).{0,20}q\s*&\s*a|"
    r"floor is open|open (the )?(call|line|floor) (for|to) question",
    re.IGNORECASE,
)


def role_from_label(speaker: str) -> str | None:
    """Role inferable from the speaker label alone, or None if ambiguous."""
    s = speaker.lower()
    if re.search(r"\boperator\b", s):
        return "Operator"
    if re.search(r"chief executive|\bceo\b", s):
        return "CEO"
    if re.search(r"chief financial|\bcfo\b", s):
        return "CFO"
    if re.search(r"chief operating|\bcoo\b", s):
        return "COO"
    if re.search(r"investor relations|head of investor|\bir\b", s):
        return "IR"
    if FIRM_RE.search(s):
        return "Analyst"
    return None


def speaker_name(speaker: str) -> str:
    """The name portion of a label, lowercased for map lookups."""
    return NAME_SEP_RE.split(speaker.strip(), maxsplit=1)[0].strip().lower()


def find_qa_start(segments) -> int:
    """Index of the first Q&A segment, or len(segments) if none is detected."""
    for i, seg in enumerate(segments):
        text = seg.get("text") or "" if isinstance(seg, dict) else ""
        if QA_TRANSITION_RE.search(text):
            return i
    return len(segments)


def classify_transcript(segments):
    """Yield (section, speaker_name, speaker_role, text) for each segment."""
    # Pass 1: learn name -> role from any labelled segment.
    name_to_role: dict[str, str] = {}
    for seg in segments:
        label = (seg.get("speaker") or "") if isinstance(seg, dict) else ""
        role = role_from_label(label)
        if role and role not in ("Operator",):
            name_to_role.setdefault(speaker_name(label), role)

    qa_start = find_qa_start(segments)

    # Pass 2: assign role + section.
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        label = (seg.get("speaker") or "").strip()
        text = seg.get("text") or ""
        in_qa = i >= qa_start

        role = role_from_label(label)
        if role is None:
            role = name_to_role.get(speaker_name(label))
        if role is None:
            role = "Analyst" if in_qa else "Other"

        if role == "Operator":
            section = "operator"
        elif role == "Analyst":
            section = "qa_question"
        else:  # management: CEO/CFO/COO/IR/Other
            section = "qa_response" if in_qa else "prepared_remarks"

        yield section, label, role, text


# ---------------------------------------------------------------------------
# Field normalisation
# ---------------------------------------------------------------------------
def normalize_quarter(q) -> str | None:
    if q is None or q == "":
        return None
    s = str(q).strip()
    m = re.search(r"[1-4]", s)
    if s.upper().startswith("Q") or "quarter" in s.lower():
        return f"Q{m.group()}" if m else s
    if m and len(s) <= 2:
        return f"Q{m.group()}"
    return s


def to_iso_date(d) -> str | None:
    if d is None or d == "":
        return None
    if hasattr(d, "isoformat"):
        return d.isoformat()[:10]
    s = str(d).strip()
    m = re.search(r"\d{4}-\d{2}-\d{2}", s)
    return m.group() if m else (s[:10] if len(s) >= 10 else s)


def load_dataset_local():
    from datasets import load_from_disk

    if not KURRY_DIR.exists():
        print(
            f"ERROR: no dataset at {KURRY_DIR}.\n"
            "Run `python ingest/download_data.py` (needs HuggingFace access) "
            "or copy the saved dataset into place first.",
            file=sys.stderr,
        )
        sys.exit(2)
    return load_from_disk(str(KURRY_DIR))


def main() -> int:
    from datasets import Dataset, DatasetDict

    ds = load_dataset_local()
    if isinstance(ds, DatasetDict):
        from datasets import concatenate_datasets

        ds = ds[next(iter(ds))] if len(ds) == 1 else concatenate_datasets(
            list(ds.values())
        )
    assert isinstance(ds, Dataset)

    # We only need the metadata fields and structured_content here. Dropping the
    # large `full_text` column avoids decoding it for every row, which is a big
    # speedup over the full dataset.
    drop = [c for c in ("full_text",) if c in ds.column_names]
    if drop:
        ds = ds.remove_columns(drop)

    n = ds.num_rows if not LIMIT else min(LIMIT, ds.num_rows)
    print(f"Loading {n:,} transcripts from {KURRY_DIR} ...")

    con = duckdb.connect(str(DB_PATH))
    # Idempotent: clear the tables this step owns.
    for table in ("utterances", "transcripts", "companies"):
        con.execute(f"DELETE FROM {table}")

    companies: dict[str, str] = {}
    seen_transcripts: set[str] = set()
    transcript_rows: list[tuple] = []
    utterance_rows: list[tuple] = []
    section_counts: Counter = Counter()
    role_counts: Counter = Counter()
    total_utterances = 0

    def flush():
        nonlocal transcript_rows, utterance_rows
        if transcript_rows:
            con.execute(
                "CREATE OR REPLACE TEMP TABLE _t "
                "(transcript_id VARCHAR, ticker VARCHAR, call_date VARCHAR, "
                " fiscal_quarter VARCHAR, fiscal_year VARCHAR)"
            )
            con.executemany("INSERT INTO _t VALUES (?,?,?,?,?)", transcript_rows)
            con.execute(
                "INSERT INTO transcripts SELECT transcript_id, ticker, "
                "TRY_CAST(call_date AS DATE), fiscal_quarter, "
                "TRY_CAST(fiscal_year AS INTEGER) FROM _t"
            )
            transcript_rows = []
        if utterance_rows:
            con.execute(
                "CREATE OR REPLACE TEMP TABLE _u "
                "(utterance_id VARCHAR, transcript_id VARCHAR, section VARCHAR, "
                " speaker_name VARCHAR, speaker_role VARCHAR, "
                " sequence_order INTEGER, text VARCHAR, word_count INTEGER)"
            )
            con.executemany(
                "INSERT INTO _u VALUES (?,?,?,?,?,?,?,?)", utterance_rows
            )
            con.execute("INSERT INTO utterances SELECT * FROM _u")
            utterance_rows = []

    # Stream with the dataset iterator (far faster than per-row ds[i] indexing).
    for i, row in enumerate(ds):
        if LIMIT and i >= LIMIT:
            break
        sym = (row.get("symbol") or "").strip() if row.get("symbol") else ""
        name = (row.get("company_name") or "").strip() if row.get("company_name") else ""
        year = row.get("year")
        quarter = normalize_quarter(row.get("quarter"))
        tid = row.get("transcript_id")
        if not tid:
            tid = f"{sym}_{year}_{quarter}"
        tid = str(tid)
        if tid in seen_transcripts:
            continue  # keep the first occurrence; transcript_id is the PK
        seen_transcripts.add(tid)

        if sym:
            companies.setdefault(sym, name)
        transcript_rows.append(
            (tid, sym or None, to_iso_date(row.get("date")), quarter,
             str(year) if year not in (None, "") else None)
        )

        segments = row.get("structured_content") or []
        seq = 0
        for section, spk, role, text in classify_transcript(segments):
            text = text or ""
            wc = len(text.split())
            utterance_rows.append(
                (f"{tid}#{seq}", tid, section, spk, role, seq, text, wc)
            )
            section_counts[section] += 1
            role_counts[role] += 1
            seq += 1
            total_utterances += 1

        if (i + 1) % BATCH_TRANSCRIPTS == 0:
            flush()
            print(f"  ...{i + 1:,}/{n:,} transcripts "
                  f"({total_utterances:,} utterances)")

    flush()

    # Companies last (small; deduped by ticker).
    if companies:
        con.execute(
            "CREATE OR REPLACE TEMP TABLE _c (ticker VARCHAR, name VARCHAR)"
        )
        con.executemany(
            "INSERT INTO _c VALUES (?,?)", list(companies.items())
        )
        con.execute("INSERT INTO companies SELECT ticker, name FROM _c")

    # Report.
    n_co = con.execute("SELECT COUNT(*) FROM companies").fetchone()[0]
    n_tr = con.execute("SELECT COUNT(*) FROM transcripts").fetchone()[0]
    n_ut = con.execute("SELECT COUNT(*) FROM utterances").fetchone()[0]
    con.close()

    print(f"\nLoaded: {n_co:,} companies, {n_tr:,} transcripts, "
          f"{n_ut:,} utterances")
    print("\nUtterances by section:")
    for section, count in section_counts.most_common():
        print(f"  {section:<16} {count:>9,}")
    print("\nUtterances by speaker_role:")
    for role, count in role_counts.most_common():
        print(f"  {role:<10} {count:>9,}")
    print("\nLoad complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
