# Subtext — MVP Build Prompt

## What This Is

Subtext is a web application that applies NLP to earnings call transcripts, helping value investors read between the lines of what management says. It analyses tone shifts, hedging language, CEO-versus-CFO sentiment divergence, and the gap between prepared remarks and Q&A responses.

## Architecture

Two-phase build:
1. **Python ingestion pipeline** — processes the raw HuggingFace datasets, runs NLP enrichment, and loads everything into a DuckDB database
2. **Rust web application** — Leptos 0.8 + Axum 0.8 serving the analytical interface, reading from DuckDB

This is the same architecture as my Edgar Explorer project: Python for data processing, Rust for the web app, DuckDB as the analytical store.

## Data

Two HuggingFace datasets are already downloaded to `./data/`:

- `./data/kurry_transcripts/` — Primary dataset. 33,000+ earnings call transcripts for S&P 500 companies, 2005–2025, with speaker-by-speaker segmentation. Each record has: `symbol`, `company_name`, `date`, `quarter`, `year`, `transcript_id`, `full_text`, and `structured_content` (a list of segments, each with `speaker` and `text` fields). The structured_content separates operator remarks, management prepared remarks, Q&A questions, and Q&A responses.
- `./data/glopardo_transcripts/` — Supplement. S&P 500 transcripts 2014–2024 with quarterly EPS and P/E data alongside transcripts. Used for the ECB Working Paper No. 3093.

For the MVP, use **kurry only**. We'll integrate glopardo's financial metrics later.

## Phase 1: Python Ingestion Pipeline (`pipeline/`)

Write a Python pipeline that:

### Step 1: Load and explore the kurry dataset
- Load from `./data/kurry_transcripts/` using the HuggingFace `datasets` library
- Print summary stats: total records, date range, number of unique companies, sample of structured_content to understand the speaker/text format
- Determine how to classify each segment's speaker role (CEO, CFO, analyst, operator, other) and section type (prepared_remarks, qa_question, qa_response, operator)

### Step 2: Build the DuckDB schema
- Create `./data/subtext.duckdb` with these tables:

```sql
CREATE TABLE companies (
    ticker VARCHAR PRIMARY KEY,
    name VARCHAR
);

CREATE TABLE transcripts (
    transcript_id VARCHAR PRIMARY KEY,
    ticker VARCHAR,
    call_date DATE,
    fiscal_quarter VARCHAR,
    fiscal_year INTEGER
);

CREATE TABLE utterances (
    utterance_id VARCHAR PRIMARY KEY,
    transcript_id VARCHAR,
    section VARCHAR,          -- 'prepared_remarks', 'qa_question', 'qa_response', 'operator', 'other'
    speaker_name VARCHAR,
    speaker_role VARCHAR,     -- 'CEO', 'CFO', 'COO', 'IR', 'Analyst', 'Operator', 'Other'
    sequence_order INTEGER,
    text TEXT,
    word_count INTEGER
);

CREATE TABLE sentiment_facts (
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
```

### Step 3: Classify speakers and sections
- Parse structured_content for each transcript
- Use heuristics to classify:
  - Speaker role: look for titles in the speaker field (CEO, Chief Executive, CFO, Chief Financial, COO, VP Investor Relations, etc.). Analysts typically have a firm name. The operator is usually "Operator" or "Conference Call Operator".
  - Section type: segments before the Q&A transition are prepared_remarks. After the Q&A begins (usually signalled by the operator saying something like "we will now begin the question-and-answer session"), segments alternate between qa_question (analyst) and qa_response (management).

### Step 4: Sentiment analysis
- Use the Loughran-McDonald Master Dictionary for financial sentiment (same dictionary used in Edgar Explorer)
- Download from: https://sraf.nd.edu/loughran-mcdonald-master-dictionary/
- Or if already available locally, point to it
- For each utterance, count: positive, negative, uncertainty, litigious, constraining words
- Compute net_sentiment = (positive_count - negative_count) / total_words

### Step 5: Build a full-text search index
- Create a DuckDB FTS index on utterances.text for BM25 search

### Step 6: Run script
- Create `pipeline/run_ingest.sh` that runs the full pipeline
- All intermediate steps should print progress

## Phase 2: Rust Web Application (`site/`)

A Leptos 0.8 + Axum 0.8 web app. Same pattern as Edgar Explorer: server-side rendering, DuckDB via `spawn_blocking`, pure-SVG charts, custom CSS.

### Project setup
- Leptos 0.8 with Axum 0.8 integration
- DuckDB via the `duckdb` Rust crate, wrapped in a `spawn_blocking` helper (same pattern as Edgar Explorer)
- The DuckDB file is at `./data/subtext.duckdb` (read-only at runtime)
- Custom CSS — do NOT use Tailwind. Write a clean, minimal stylesheet. Dark background option not required; use a clean light theme. Professional, not flashy. Serif body font (Georgia or similar), monospace for data/numbers.

### MVP Routes

**`/` — Home**
- Brief description of what Subtext does
- Search box to find a company by ticker or name
- List of "most covered" companies (those with the most transcripts)

**`/company/:ticker` — Company Dashboard**
- Company name and ticker
- Total number of transcripts available, date range
- **Sentiment Timeline**: SVG line chart showing net_sentiment per transcript over time (x-axis: quarters, y-axis: net_sentiment). This is the core visualisation.
- **CEO vs CFO panel**: Two line series on the same chart — one for CEO utterances' average sentiment per call, one for CFO. Highlight quarters where they diverge significantly.
- **Prepared Remarks vs Q&A panel**: Two line series — average sentiment of prepared_remarks section vs average sentiment of qa_response section per call. The gap between these is information.
- **Recent Transcripts**: List of the last 8 transcripts with date, overall sentiment score, and a link to `/transcript/:id`

**`/transcript/:transcript_id` — Single Transcript View**
- Full transcript text, rendered as a sequence of utterances
- Each utterance shows: speaker name, speaker role (colour-coded badge), section type, and the text
- Sentiment words highlighted inline (positive in green, negative in red)
- Aggregate stats at the top: overall sentiment, hedging score, word counts by speaker

**`/search` — Full-Text Search**
- Search box with BM25 search across all utterances
- Filter by: company (ticker), date range, speaker role, section type
- Results show: company, date, speaker, snippet with highlighted match
- Link to full transcript

**`/about` — About Page**
- What Subtext is, data sources, methodology
- Mention the Loughran-McDonald dictionary
- Link to the ECB Working Paper No. 3093 that used the same class of data

### SVG Charts
- Pure SVG, no JavaScript charting library
- Same approach as Edgar Explorer: server-rendered SVG elements
- Line charts with axes, gridlines, data points
- Tooltip-like labels on hover (CSS-only if possible, or minimal JS)
- Use CSS variables for colours so theming is easy

### CSS Approach
- Single stylesheet, not a framework
- Clean, professional, minimal
- Georgia or similar serif for body text
- Monospace (SF Mono, Fira Code, or system monospace) for numbers and data
- Muted colour palette: dark grey text, white/off-white background, blue accent for links and primary actions
- Speaker role badges: distinct colours for CEO (dark blue), CFO (teal), Analyst (orange), Operator (grey)
- Responsive but desktop-first — this is a research tool

## What NOT to Build Yet

- Hedging dictionary and hedging scores (Phase 2)
- Promise tracking / forward-looking statement extraction (Phase 2)
- Q&A response quality scoring (Phase 2)
- Cross-company sector comparison (Phase 2)
- Integration with Edgar Explorer (Phase 3)
- glopardo financial metrics integration (Phase 2)
- Audio analysis (Phase 3)
- Docker deployment (later)

## File Structure

```
subtext/
├── pipeline/
│   ├── explore_data.py          # Step 1: explore dataset structure
│   ├── build_schema.py          # Step 2: create DuckDB schema
│   ├── load_transcripts.py      # Step 3: parse, classify, load
│   ├── compute_sentiment.py     # Step 4: Loughran-McDonald sentiment
│   ├── build_indices.py         # Step 5: FTS index
│   ├── run_ingest.sh            # Step 6: run all steps
│   └── requirements.txt
├── site/
│   ├── Cargo.toml
│   ├── src/
│   │   ├── main.rs
│   │   ├── lib.rs
│   │   ├── app.rs               # Router, shell, nav
│   │   ├── db.rs                # DuckDB wrapper
│   │   ├── types.rs             # Serde types
│   │   ├── chart.rs             # SVG chart components
│   │   ├── home.rs              # /
│   │   ├── company.rs           # /company/:ticker
│   │   ├── transcript.rs        # /transcript/:id
│   │   ├── search.rs            # /search
│   │   └── about.rs             # /about
│   └── style/
│       └── main.css
├── data/                        # gitignored
│   ├── kurry_transcripts/
│   ├── glopardo_transcripts/
│   └── subtext.duckdb           # built by ingest pipeline
├── .gitignore
└── README.md
```

## Key Principle

Start with the Python ingestion pipeline. Get data into DuckDB first. Verify the data looks right. Then build the Rust web app on top of it. Don't try to do both simultaneously.