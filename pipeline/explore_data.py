#!/usr/bin/env python3
"""Phase 1, Step 1 — explore the kurry earnings-call dataset.

Loads the kurry transcripts from the local on-disk copy at
``./data/kurry_transcripts/`` and prints everything we need to understand the
data before building the DuckDB schema and the classification heuristics:

  * schema / feature types and the exact column names
  * record counts, date range, unique companies, unique transcripts
  * per-year and per-quarter distributions
  * the most-covered companies (drives the home-page "most covered" list)
  * the shape of ``structured_content`` (segments per transcript, empties)
  * one full sample record, printed field by field
  * a survey of speaker labels — the raw material for role classification
    (CEO / CFO / COO / IR / Analyst / Operator / Other) in Step 3
  * a survey of operator "question-and-answer" transition phrases — the raw
    material for prepared_remarks vs Q&A section tagging in Step 3

Nothing is written to disk; this step is read-only exploration. Its purpose is
to make the format concrete and to justify the heuristics used downstream.

Usage:
    python pipeline/explore_data.py
    SUBTEXT_SAMPLE=5000 python pipeline/explore_data.py   # widen the sample
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter
from pathlib import Path

# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
KURRY_DIR = DATA_DIR / "kurry_transcripts"
DATASET_ID = "kurry/sp500_earnings_transcripts"

# How many transcripts to scan for the (more expensive) structured_content,
# speaker, and section-transition surveys. Cheap scalar stats always use every
# row. Override with SUBTEXT_SAMPLE=<n>, or 0 to scan everything.
SAMPLE_SIZE = int(os.environ.get("SUBTEXT_SAMPLE", "3000"))

RULE = "=" * 78


def header(title: str) -> None:
    print(f"\n{RULE}\n{title}\n{RULE}")


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_transcripts():
    """Return a single Dataset of transcripts, loaded from the local copy.

    Prefers the on-disk copy the rest of the pipeline reads. Falls back to a
    direct Hub download only if that copy is missing, so this script is still
    useful in an environment that has network access but no saved dataset yet.
    """
    import datasets
    from datasets import load_dataset, load_from_disk
    from datasets import Dataset, DatasetDict

    print(f"Python:   {sys.executable}")
    print(f"datasets: {datasets.__version__}")

    if KURRY_DIR.exists():
        print(f"Loading local dataset from {KURRY_DIR} ...")
        try:
            ds = load_from_disk(str(KURRY_DIR))
        except ValueError as exc:
            if "Feature type" in str(exc) and "not found" in str(exc):
                sys.exit(
                    f"\nERROR: this `datasets` ({datasets.__version__}) is too old "
                    "to read the saved dataset.\n"
                    "The on-disk copy uses a newer feature type (e.g. 'List'). "
                    "Use the project virtualenv (which pins datasets>=5.0.0):\n"
                    "    source .venv/bin/activate\n"
                    "or upgrade: pip install -U 'datasets>=5.0.0'\n"
                    f"(original error: {exc})"
                )
            raise
    else:
        print(
            f"No local copy at {KURRY_DIR}.\n"
            f"Falling back to downloading '{DATASET_ID}' from the Hub.\n"
            f"(Run `python pipeline/download_data.py` to save a local copy.)"
        )
        ds = load_dataset(DATASET_ID)

    # Collapse a DatasetDict (splits) into one Dataset for exploration.
    if isinstance(ds, DatasetDict):
        print(f"Splits found: {list(ds.keys())}")
        if len(ds) == 1:
            ds = next(iter(ds.values()))
        else:
            from datasets import concatenate_datasets

            ds = concatenate_datasets(list(ds.values()))
    assert isinstance(ds, Dataset)
    return ds


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def seg_field(segment, name: str) -> str:
    """Read ``speaker``/``text`` from a segment that may be a dict or object."""
    if isinstance(segment, dict):
        value = segment.get(name)
    else:
        value = getattr(segment, name, None)
    return value if isinstance(value, str) else ("" if value is None else str(value))


def year_of(row) -> int | None:
    """Best-effort fiscal/calendar year for a row."""
    if row.get("year") not in (None, ""):
        try:
            return int(row["year"])
        except (TypeError, ValueError):
            pass
    date = row.get("date")
    if isinstance(date, str) and len(date) >= 4 and date[:4].isdigit():
        return int(date[:4])
    if date is not None and hasattr(date, "year"):
        return date.year
    return None


def print_distribution(counter: Counter, top=None, label_width=18) -> None:
    items = counter.most_common(top) if top else sorted(counter.items())
    if not items:
        print("  (none)")
        return
    peak = max(counter.values())
    for label, count in items:
        bar = "#" * int(round(40 * count / peak)) if peak else ""
        print(f"  {str(label):<{label_width}} {count:>7,}  {bar}")


# ---------------------------------------------------------------------------
# Keyword sets used to survey speaker roles (Step 3 will formalise these)
# ---------------------------------------------------------------------------
ROLE_PATTERNS = {
    "CEO": r"\bchief executive\b|\bceo\b|\bpresident\s*(?:&|and)\s*ceo\b",
    "CFO": r"\bchief financial\b|\bcfo\b",
    "COO": r"\bchief operating\b|\bcoo\b",
    "Chair": r"\bchairman\b|\bchairwoman\b|\bchair\b",
    "President": r"\bpresident\b",
    "IR": r"\binvestor relations\b|\bir\b|\bhead of ir\b",
    "Operator": r"\boperator\b",
    "Other C-suite": r"\bchief\b|\bcto\b|\bcmo\b|\bcao\b",
    "VP/Exec": r"\bvice president\b|\bvp\b|\bexecutive\b|\bsvp\b|\bevp\b",
    "Analyst (firm)": (
        r"\b(?:goldman|morgan stanley|jpmorgan|j\.p\. morgan|bofa|"
        r"bank of america|barclays|citi|credit suisse|ubs|wells fargo|"
        r"deutsche|jefferies|evercore|cowen|raymond james|piper|"
        r"wolfe|bernstein|rbc|mizuho|baird|stifel|guggenheim|truist|"
        r"oppenheimer|needham|canaccord|keybanc|research|capital|"
        r"securities|analyst)\b"
    ),
}


def classify_speaker_survey(speaker: str) -> str:
    """Rough bucketing used only for the exploration survey."""
    s = speaker.lower()
    for role, pattern in ROLE_PATTERNS.items():
        if re.search(pattern, s):
            return role
    return "Unmatched"


# Phrases operators use to open the Q&A — candidates for the section split.
QA_TRANSITION_RE = re.compile(
    r"question[- ]and[- ]answer|question[- ]&[- ]answer|"
    r"we('| wi)ll now (begin|take|open|move to).{0,40}question|"
    r"first question|floor is open|open (the )?(call|line|floor) (for|to) question",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    ds = load_transcripts()
    n = ds.num_rows
    columns = ds.column_names

    header("SCHEMA / FEATURES")
    print(f"Total records: {n:,}")
    print(f"Columns ({len(columns)}): {columns}\n")
    for name, feature in ds.features.items():
        print(f"  {name:<20} {feature}")

    # ---- scalar-field stats over every row -------------------------------
    header("RECORD-LEVEL STATS (full scan)")
    symbols: Counter = Counter()
    transcript_ids: set[str] = set()
    years: Counter = Counter()
    quarters: Counter = Counter()
    dates: list[str] = []
    dup_transcript_ids = 0
    has_full_text = "full_text" in columns
    has_transcript_id = "transcript_id" in columns

    # Iterate columnar for speed on the cheap fields.
    sym_col = ds["symbol"] if "symbol" in columns else [None] * n
    name_col = ds["company_name"] if "company_name" in columns else [None] * n
    tid_col = ds["transcript_id"] if has_transcript_id else [None] * n
    date_col = ds["date"] if "date" in columns else [None] * n
    year_col = ds["year"] if "year" in columns else [None] * n
    quarter_col = ds["quarter"] if "quarter" in columns else [None] * n

    company_names: dict[str, str] = {}
    for i in range(n):
        sym = sym_col[i]
        if sym is not None:
            symbols[sym] += 1
            if name_col[i]:
                company_names.setdefault(str(sym), str(name_col[i]))
        tid = tid_col[i]
        if tid is not None:
            if tid in transcript_ids:
                dup_transcript_ids += 1
            transcript_ids.add(tid)
        y = year_of({"year": year_col[i], "date": date_col[i]})
        if y is not None:
            years[y] += 1
        q = quarter_col[i]
        if q is not None and q != "":
            quarters[str(q)] += 1
        d = date_col[i]
        if isinstance(d, str) and d:
            dates.append(d)
        elif d is not None and hasattr(d, "isoformat"):
            dates.append(d.isoformat())

    print(f"Unique companies (symbol): {len(symbols):,}")
    if has_transcript_id:
        print(f"Unique transcript_id:      {len(transcript_ids):,}")
        print(f"Duplicate transcript_id:   {dup_transcript_ids:,}")
    else:
        print("No `transcript_id` column present.")
    print(f"Has `full_text` column:    {has_full_text}")
    if dates:
        print(f"Date range:                {min(dates)}  ->  {max(dates)}")

    header("TRANSCRIPTS PER YEAR")
    print_distribution(years)

    header("TRANSCRIPTS PER QUARTER")
    print_distribution(quarters)

    header("MOST-COVERED COMPANIES (top 25)")
    for sym, count in symbols.most_common(25):
        print(f"  {sym:<8} {count:>4}  {company_names.get(str(sym), '')}")

    # ---- one full sample record ------------------------------------------
    header("SAMPLE RECORD (row 0)")
    row0 = ds[0]
    for key in columns:
        value = row0[key]
        if key == "structured_content":
            segs = value or []
            print(f"  {key}: list of {len(segs)} segments")
        elif isinstance(value, str) and len(value) > 300:
            print(f"  {key}: ({len(value)} chars) {value[:300]!r} ...")
        else:
            print(f"  {key}: {value!r}")

    sc0 = row0.get("structured_content") or []
    print("\nFirst 8 segments of structured_content:")
    for idx, seg in enumerate(sc0[:8]):
        speaker = seg_field(seg, "speaker")
        text = seg_field(seg, "text")
        snippet = text[:180].replace("\n", " ")
        print(f"  [{idx}] speaker={speaker!r}")
        print(f"       text=({len(text)} chars) {snippet!r}")
    if sc0:
        sub_keys = list(sc0[0].keys()) if isinstance(sc0[0], dict) else "n/a"
        print(f"\nSegment sub-fields: {sub_keys}")

    # ---- structured_content / speaker / section survey (sampled) ---------
    sample_n = n if SAMPLE_SIZE in (0, None) else min(SAMPLE_SIZE, n)
    header(f"STRUCTURED_CONTENT SURVEY (sample of {sample_n:,} transcripts)")

    seg_counts: list[int] = []
    empty_structured = 0
    speaker_examples: Counter = Counter()
    role_survey: Counter = Counter()
    unmatched_speakers: Counter = Counter()
    qa_transition_hits = 0
    qa_transition_examples: list[str] = []
    operator_labels: Counter = Counter()

    sc_col = ds.select(range(sample_n))["structured_content"]
    for segs in sc_col:
        segs = segs or []
        seg_counts.append(len(segs))
        if not segs:
            empty_structured += 1
            continue
        found_transition = False
        for seg in segs:
            speaker = seg_field(seg, "speaker").strip()
            text = seg_field(seg, "text")
            if speaker:
                speaker_examples[speaker] += 1
                role = classify_speaker_survey(speaker)
                role_survey[role] += 1
                if role == "Unmatched":
                    unmatched_speakers[speaker] += 1
                if re.search(r"\boperator\b", speaker.lower()):
                    operator_labels[speaker] += 1
            if not found_transition and QA_TRANSITION_RE.search(text):
                found_transition = True
                if len(qa_transition_examples) < 8:
                    m = QA_TRANSITION_RE.search(text)
                    lo, hi = max(0, m.start() - 30), m.end() + 40
                    qa_transition_examples.append(
                        text[lo:hi].replace("\n", " ").strip()
                    )
        if found_transition:
            qa_transition_hits += 1

    if seg_counts:
        seg_counts_sorted = sorted(seg_counts)
        total_segs = sum(seg_counts)
        mid = seg_counts_sorted[len(seg_counts_sorted) // 2]
        print(
            f"Segments per transcript: min={min(seg_counts)}, "
            f"median={mid}, max={max(seg_counts)}, "
            f"mean={total_segs / len(seg_counts):.1f}"
        )
        print(f"Total segments in sample:  {total_segs:,}")
        print(f"Transcripts with empty structured_content: {empty_structured:,}")
        print(f"Distinct speaker labels in sample:         {len(speaker_examples):,}")

    header("SPEAKER-ROLE SURVEY (heuristic buckets over sampled segments)")
    print("How well simple title/firm patterns would bucket speakers:")
    print_distribution(role_survey, label_width=16)

    header("MOST COMMON SPEAKER LABELS (top 30)")
    for label, count in speaker_examples.most_common(30):
        print(f"  {count:>6,}  {label!r}")

    header("MOST COMMON *UNMATCHED* SPEAKER LABELS (top 30)")
    print("These show where the Step-3 role heuristics still need work:")
    for label, count in unmatched_speakers.most_common(30):
        print(f"  {count:>6,}  {label!r}")

    header("OPERATOR LABEL VARIANTS (top 15)")
    for label, count in operator_labels.most_common(15):
        print(f"  {count:>6,}  {label!r}")

    header("Q&A SECTION-TRANSITION SURVEY")
    pct = 100.0 * qa_transition_hits / sample_n if sample_n else 0.0
    print(
        f"Transcripts with a detectable Q&A transition phrase: "
        f"{qa_transition_hits:,} / {sample_n:,} ({pct:.1f}%)"
    )
    print("Example transition snippets:")
    for ex in qa_transition_examples:
        print(f"  ...{ex}...")

    header("NOTES FOR NEXT STEPS")
    print(
        "Step 2 (schema): columns above map cleanly to companies/transcripts/\n"
        "  utterances tables. transcript_id present = "
        f"{has_transcript_id}; full_text present = {has_full_text}.\n"
        "Step 3 (classify): use the speaker-label survey to finalise role\n"
        "  regexes; use the Q&A-transition survey to split prepared_remarks\n"
        "  from qa_question/qa_response.\n"
        "Step 4 (sentiment): utterance `text` is the unit; word_count and\n"
        "  Loughran-McDonald counts will be computed per utterance."
    )
    print("\nExploration complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
