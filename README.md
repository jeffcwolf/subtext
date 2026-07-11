# Subtext

**Reading between the lines of earnings calls.** Subtext applies NLP to
earnings-call transcripts — tone shifts, hedging, CEO-vs-CFO divergence, and the
gap between prepared remarks and Q&A. See [`SPEC.md`](SPEC.md) for the full
product vision and [`CLAUDE.md`](CLAUDE.md) for the MVP build plan.

Architecture (two phases):

1. **Python ingestion pipeline** (`ingest/`) — processes the HuggingFace
   transcript dataset, runs Loughran-McDonald sentiment, and loads everything
   into a DuckDB database.
2. **Rust web application** (`site/`) — Leptos 0.8 + Axum 0.8 serving the
   analytical interface, reading from DuckDB. *(Phase 2, not built yet.)*

## Phase 1 — Ingestion pipeline

The pipeline builds `./data/subtext.duckdb` from the
[`kurry/sp500_earnings_transcripts`](https://huggingface.co/datasets/kurry/sp500_earnings_transcripts)
dataset (33,000+ S&P 500 earnings-call transcripts, 2005–2025, speaker-by-speaker).

### Steps

| Script | Step | What it does |
|---|---|---|
| `ingest/explore_data.py` | 1 | Explore the dataset: schema, counts, date range, `structured_content` shape, speaker-label and Q&A-transition surveys |
| `ingest/build_schema.py` | 2 | Create the DuckDB tables (companies, transcripts, utterances, sentiment_facts) |
| `ingest/load_transcripts.py` | 3 | Parse `structured_content`, classify speaker roles and section types, load the tables |
| `ingest/compute_sentiment.py` | 4 | Loughran-McDonald sentiment per utterance |
| `ingest/build_indices.py` | 5 | DuckDB FTS (BM25) index over `utterances.text` |
| `ingest/run_ingest.sh` | 6 | Run steps 2–5 in order (`RUN_EXPLORE=1` also runs step 1) |

### Setup

```bash
# From the repo root
uv venv --python 3.11
source .venv/bin/activate
uv pip install -r ingest/requirements.txt
```

### Data prerequisites

Both live under `./data/` (gitignored):

1. **Transcripts** — save the dataset to `./data/kurry_transcripts/`:
   ```bash
   python ingest/download_data.py     # needs access to huggingface.co
   ```
   If your environment blocks HuggingFace, run this where it's reachable and
   copy the resulting `data/kurry_transcripts/` directory into place.

2. **Loughran-McDonald Master Dictionary** — download the CSV from
   <https://sraf.nd.edu/loughran-mcdonald-master-dictionary/> and place it under
   `./data/` (any filename containing "Master" and "Dictionary"), or point
   `LM_DICT=/path/to/dictionary.csv` at it.

### Run

```bash
./ingest/run_ingest.sh          # build the DuckDB database
RUN_EXPLORE=1 ./ingest/run_ingest.sh   # also print the Step 1 exploration
```

### Speaker & section classification

In this dataset the speaker labels are **bare names** with no titles
(`'Mike McMullen'`), so:

- **Speaker role** (`CEO`/`CFO`/`COO`/`IR`/`Analyst`/`Operator`/`Other`): roles
  are inferred from how people are introduced in the prepared remarks
  ("... Mike McMullen, Agilent's President and CEO; and Bob McMahon, ... CFO").
  `load_transcripts.py` parses those intros into a name→role map (the leftmost
  chief title wins, so "President and CEO" → CEO), then applies it; unmapped
  voices in the Q&A default to analysts.
- **Section** (`prepared_remarks`/`qa_question`/`qa_response`/`operator`/`other`):
  the Q&A boundary is the operator turn that actually opens questions
  ("your first question comes from the line of …") — not the opening disclaimer,
  which mentions the "question-and-answer session" up front. Management before
  the boundary is prepared remarks, after it is Q&A responses; analysts are
  questions.

These heuristics were tuned against the real dataset. The load prints a
**classification-health** summary (share of transcripts with a detected Q&A
boundary and an identified CEO/CFO); `ingest/explore_data.py`'s speaker-label
and Q&A-transition surveys show where any remaining tuning is needed.

The dataset has no `transcript_id`, so one is synthesized from
ticker/year/quarter (collision-suffixed) for the `transcripts` primary key.

### Network notes

Two one-time steps reach external hosts that a restricted egress policy may
block: the HuggingFace download (`download_data.py`) and the DuckDB `fts`
extension install (`build_indices.py`, from `extensions.duckdb.org`). Run those
where the hosts are reachable, or allowlist them; the extension is then cached
under `~/.duckdb/extensions` and DuckDB reuses it offline.

## Phase 2 — Web app

`site/` is a Leptos 0.8 + Axum 0.8 web app. Leptos renders each page to HTML
server-side (no WASM/hydration); Axum serves them; charts are pure inline SVG;
styling is a single hand-written stylesheet (no framework). It reads
`./data/subtext.duckdb` read-only via `spawn_blocking`.

The `duckdb` crate is pinned to `1.10504.x`, which bundles libduckdb **1.5.4** —
matching the version the Python pipeline writes, so the storage format and the
`fts` extension line up.

### Run

```bash
cd site
cargo run --release          # then open http://127.0.0.1:3000
```

The app finds `data/subtext.duckdb` automatically by searching up from the
working directory, so `cargo run` works from `site/` or the repo root with no
configuration. It prints the resolved path and row counts at startup, and fails
fast with a clear message if the database isn't found.

Overrides: `SUBTEXT_DB` (explicit path to the DuckDB file) and `SUBTEXT_ADDR`
(bind address, default `127.0.0.1:3000`). The first build compiles the bundled
libduckdb and is slow (several minutes); later builds are fast. For auto-rebuild
on save during development, `cargo watch -x run` (from the `cargo-watch` crate).

### Routes

| Route | What it shows |
|---|---|
| `/` | Description, search box, most-covered companies |
| `/company/{ticker}` | Sentiment timeline, CEO-vs-CFO panel, prepared-vs-Q&A panel, **tone-vs-forward-expectations** (glopardo forward EPS / P/E + divergence flags), recent transcripts |
| `/transcript/{id}` | The full call as utterances with role badges, section tags, per-turn sentiment, **inline green/red sentiment-word highlighting**, and that quarter's EPS / P/E |
| `/sectors`, `/sector/{name}` | Cross-company **tone comparison within a sector** — companies ranked by average tone with deviation from the sector mean (SPEC #6) |
| `/search` | BM25 full-text search with ticker / role / section filters |
| `/about` | Data sources and methodology |

`/search` needs the `fts` extension loadable at runtime (installed during
`build_indices.py`); if it isn't, search degrades to an "unavailable" message
while the rest of the app works.
