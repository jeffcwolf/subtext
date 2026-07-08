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

# In this dataset the speaker labels are bare names ("Mike McMullen") with no
# titles, so roles are inferred from how people are introduced in the prepared
# remarks ("... Mike McMullen, Agilent's President and CEO; and Bob McMahon,
# Senior Vice President and CFO").

OPERATOR_LABEL_RE = re.compile(r"^\s*operator\b", re.IGNORECASE)
ANALYST_LABEL_RE = re.compile(r"analyst", re.IGNORECASE)

# Chief titles, captured so the *leftmost* one in a person's title clause wins
# (so "President and CEO" resolves to CEO, not President).
CHIEF_TITLE_RE = re.compile(
    r"(?P<CEO>chief executive officer|chief executive|\bceo\b)|"
    r"(?P<CFO>chief financial officer|chief financial|\bcfo\b)|"
    r"(?P<COO>chief operating officer|chief operating|\bcoo\b)|"
    r"(?P<IR>investor relations|head of investor)",
    re.IGNORECASE,
)
# Generic management titles, used only when no chief title is present.
OTHER_MGMT_RE = re.compile(
    r"chief [a-z]+ officer|\bpresident\b|chair(?:man|woman|person)?|"
    r"vice president|\bevp\b|\bsvp\b|\bvp\b|treasurer|general counsel|"
    r"founder|managing director|head of|\bofficer\b",
    re.IGNORECASE,
)
# Boundary between one introduced person's title clause and the next.
PERSON_BREAK_RE = re.compile(r";|\n|\band our\b|\band joining\b", re.IGNORECASE)

# The operator turn that actually opens the Q&A. Deliberately does NOT match the
# opening disclaimer ("... there will be a question-and-answer session"), which
# is future-tense and appears in the very first operator segment.
QA_START_RE = re.compile(
    r"\bfirst question\b|\bnext question\b|"
    r"questions?\s*(?:comes?|come)\s*from|from the line of|"
    r"we(?:'?ll| will| are going to)?\s*(?:now\s*)?"
    r"(?:begin|start|open|take|conduct)\b[^.]{0,50}\bquestion|"
    r"(?:begin|conduct|start)\s+the\s+question[-\s]and[-\s]answer\s+session",
    re.IGNORECASE,
)

# Operators announce each analyst: "... question ... from [the line of] <Name>
# - Firm" / "... from <Name> with/of/representing <Firm>". Capture the name (up
# to 4 capitalised tokens); it stops naturally at the firm connector (dash,
# "with"/"of"/"from"/"representing", comma) since those are lowercase/punctuation.
_NAME_TOKEN = r"[A-Z][A-Za-z.'’-]+"
ANALYST_ROUTE_RE = re.compile(
    r"(?:question|caller)\b[^.]{0,40}?\bfrom(?:\s+the\s+line\s+of)?\s+"
    r"(?P<name>" + _NAME_TOKEN + r"(?:\s+" + _NAME_TOKEN + r"){0,3})"
)
HONORIFIC_RE = re.compile(r"^(?:mr|ms|mrs|dr|sir)\.?\s+", re.IGNORECASE)


def _surname(label: str) -> str:
    """Last name token of a label (punctuation stripped)."""
    toks = re.sub(r"[.,]", " ", label).split()
    return toks[-1].strip("'’-") if toks else ""


def _title_clause_role(window: str) -> str | None:
    """Classify the title clause that immediately follows (or precedes) a name.

    Only the current person's clause is considered — split off anything after a
    person break (";", newline, "and our ...") so a neighbour's title can't leak
    in. The leftmost chief title wins so "President and CEO" -> CEO.
    """
    clause = PERSON_BREAK_RE.split(window, maxsplit=1)[0]
    m = CHIEF_TITLE_RE.search(clause)
    if m:
        return m.lastgroup
    return "Other" if OTHER_MGMT_RE.search(clause) else None


def find_qa_start(segments) -> int:
    """Index of the operator turn that opens the Q&A, else len(segments)."""
    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        label = (seg.get("speaker") or "").strip()
        if OPERATOR_LABEL_RE.match(label) and QA_START_RE.search(seg.get("text") or ""):
            return i
    return len(segments)


def build_role_map(segments, qa_start) -> dict[str, str]:
    """Learn speaker-name -> management role from the introduction text."""
    intro_parts: list[str] = []
    size = 0
    for seg in segments[:qa_start]:
        if isinstance(seg, dict):
            t = seg.get("text") or ""
            intro_parts.append(t)
            size += len(t)
            if size > 8000:  # the "with me are ..." intro is always near the top
                break
    intro_text = " ".join(intro_parts)[:8000]

    names = set()
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        label = (seg.get("speaker") or "").strip()
        if label and len(label) <= 60 and not OPERATOR_LABEL_RE.match(label):
            names.add(label)

    role_map: dict[str, str] = {}
    for name in names:
        role = _role_for_name(name, intro_text)
        if role:
            role_map[name] = role
    return role_map


def _role_for_name(name: str, intro_text: str) -> str | None:
    """Find a name's role in the intro, matching the full label then its surname.

    The speaker label and the introduction often use different name forms (label
    "William Parker" vs intro "Doug Parker, our CEO"), so an exact-name miss
    falls back to matching the surname near a title.
    """
    idx = intro_text.find(name)
    if idx >= 0:
        role = _title_clause_role(intro_text[idx + len(name):idx + len(name) + 120])
        if role is None:
            m = CHIEF_TITLE_RE.search(intro_text[max(0, idx - 25):idx])
            role = m.lastgroup if m else None
        if role:
            return role

    surname = _surname(name)
    if len(surname) >= 3:
        for sm in re.finditer(r"\b" + re.escape(surname) + r"\b", intro_text):
            role = _title_clause_role(intro_text[sm.end():sm.end() + 120])
            if role is None:
                m = CHIEF_TITLE_RE.search(intro_text[max(0, sm.start() - 25):sm.start()])
                role = m.lastgroup if m else None
            if role:
                return role
    return None


def extract_announced_analysts(segments) -> tuple[set[str], set[str]]:
    """Names the operator hands questions to — the reliable analyst signal.

    Returns (full names, surnames). Only operator turns are scanned, and the
    opening disclaimer has no "question ... from <Name>" routing, so it is safe.
    """
    full: set[str] = set()
    surnames: set[str] = set()
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        if not OPERATOR_LABEL_RE.match((seg.get("speaker") or "").strip()):
            continue
        for m in ANALYST_ROUTE_RE.finditer(seg.get("text") or ""):
            name = HONORIFIC_RE.sub("", m.group("name")).strip(" .,-'")
            if len(name) < 3:
                continue
            full.add(name)
            sn = _surname(name)
            if len(sn) >= 3:
                surnames.add(sn)
    return full, surnames


def classify_transcript(segments, qa_start=None):
    """Yield (section, speaker_name, speaker_role, text) for each segment."""
    if qa_start is None:
        qa_start = find_qa_start(segments)
    role_map = build_role_map(segments, qa_start)
    analyst_full, analyst_surnames = extract_announced_analysts(segments)

    for i, seg in enumerate(segments):
        if not isinstance(seg, dict):
            continue
        label = (seg.get("speaker") or "").strip()
        text = seg.get("text") or ""
        in_qa = i >= qa_start
        low = label.lower()

        if OPERATOR_LABEL_RE.match(label):
            role = "Operator"
        elif len(label) > 60:
            role = "Other"          # malformed label (text leaked into speaker)
        elif ANALYST_LABEL_RE.search(label):
            role = "Analyst"        # e.g. "Unidentified Analyst"
        elif label in role_map:
            role = role_map[label]  # management, identified from the intro titles
        elif label in analyst_full or _surname(label) in analyst_surnames:
            role = "Analyst"        # named by the operator when handing off Q&A
        else:
            # Unknown speaker. In the Q&A the analysts are the ones the operator
            # announced (handled above), so an unannounced voice is management
            # responding; before the Q&A it is an unlabelled participant.
            role = "Other"

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
    import datasets
    from datasets import load_from_disk

    print(f"Python: {sys.executable} | datasets: {datasets.__version__}")
    if not KURRY_DIR.exists():
        print(
            f"ERROR: no dataset at {KURRY_DIR}.\n"
            "Run `python ingest/download_data.py` (needs HuggingFace access) "
            "or copy the saved dataset into place first.",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        return load_from_disk(str(KURRY_DIR))
    except ValueError as exc:
        if "Feature type" in str(exc) and "not found" in str(exc):
            sys.exit(
                f"\nERROR: this `datasets` ({datasets.__version__}) is too old to "
                "read the saved dataset (it uses a newer feature type such as "
                "'List').\nUse the project virtualenv (datasets>=5.0.0):\n"
                "    source .venv/bin/activate\n"
                "or upgrade: pip install -U 'datasets>=5.0.0'\n"
                f"(original error: {exc})"
            )
        raise


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
    # large whole-transcript text columns (`content` ~56 KB/row, and `full_text`
    # if present) avoids decoding them for every row — a big speedup.
    drop = [c for c in ("full_text", "content") if c in ds.column_names]
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
    # Classification-health diagnostics (how well the heuristics fired).
    n_nonempty = n_qa_detected = n_with_ceo = n_with_cfo = 0

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
            # This dataset has no transcript_id; synthesize a readable, unique
            # one from ticker/year/quarter, suffixing on the rare collision
            # (e.g. two calls in the same fiscal quarter) so none are dropped.
            base = f"{sym}_{year}_{quarter}" if sym else f"row{i}"
            tid, k = base, 2
            while tid in seen_transcripts:
                tid, k = f"{base}_{k}", k + 1
        else:
            tid = str(tid)
            if tid in seen_transcripts:
                continue  # real duplicate transcript_id: keep the first
        seen_transcripts.add(tid)

        if sym:
            companies.setdefault(sym, name)
        transcript_rows.append(
            (tid, sym or None, to_iso_date(row.get("date")), quarter,
             str(year) if year not in (None, "") else None)
        )

        segments = row.get("structured_content") or []
        qa_start = find_qa_start(segments)
        if segments:
            n_nonempty += 1
            if qa_start < len(segments):
                n_qa_detected += 1
        roles_here: set[str] = set()
        seq = 0
        for section, spk, role, text in classify_transcript(segments, qa_start):
            text = text or ""
            wc = len(text.split())
            utterance_rows.append(
                (f"{tid}#{seq}", tid, section, spk, role, seq, text, wc)
            )
            section_counts[section] += 1
            role_counts[role] += 1
            roles_here.add(role)
            seq += 1
            total_utterances += 1
        n_with_ceo += "CEO" in roles_here
        n_with_cfo += "CFO" in roles_here

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

    # Classification health: on clean data most non-empty transcripts should
    # have a detected Q&A boundary and an identified CEO and CFO. Low numbers
    # here mean the intro-parsing / Q&A-start heuristics need tuning.
    if n_nonempty:
        pct = lambda x: f"{100.0 * x / n_nonempty:5.1f}%"
        print("\nClassification health (of "
              f"{n_nonempty:,} non-empty transcripts):")
        print(f"  Q&A boundary detected: {pct(n_qa_detected)} ({n_qa_detected:,})")
        print(f"  CEO identified:        {pct(n_with_ceo)} ({n_with_ceo:,})")
        print(f"  CFO identified:        {pct(n_with_cfo)} ({n_with_cfo:,})")
    print("\nLoad complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
