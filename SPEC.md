# Subtext

**Reading between the lines of earnings calls.**

A research tool for fundamental investors that applies NLP to earnings call transcripts — surfacing tone shifts, hedging language, broken promises, and the gap between what management says and what they mean.

---

## The Problem

Earnings calls are the single most time-intensive information source in fundamental research. A value investor covering 30 companies listens to 120+ calls per year, each 45–90 minutes. They take notes. They remember what the CEO said last quarter. They form impressions of management candour over time. But this process is entirely manual, entirely dependent on memory, and entirely unscalable.

No free tool lets an investor answer questions like:
- "Is this CEO getting more cautious in their language?"
- "They promised 15% margins two years ago — how has the language around margins shifted since?"
- "What are analysts pressing on that management is deflecting?"
- "Which companies in my coverage universe just had an unusual tone shift?"

Subtext makes these questions answerable.

---

## Data

### Sources

**Primary: Earnings call transcripts**

| Source | Coverage | Access | Notes |
|---|---|---|---|
| Company IR pages | Varies | Free, scraping required | Many S&P 500 companies publish full transcripts. Gold standard for accuracy. |
| Financial Modeling Prep API | Broad, multi-year | Free tier + paid | Structured JSON, speaker-separated. Good starting point. |
| Motley Fool transcript archive | S&P 500, multi-year | Free, scraping required | Historically comprehensive. Verify current availability. |
| SEC EDGAR 8-K filings | Earnings releases only | Free | Not full transcripts, but contains prepared remarks and financial highlights. Useful supplement. |

**Secondary: Earnings call audio (future phase)**

| Source | Coverage | Access | Notes |
|---|---|---|---|
| Company IR pages (audio/webcast) | Varies | Free | Speech-to-text via Whisper. Captures vocal tone, pauses, crosstalk — things transcripts miss. |

### Scope

**Phase 1 (initial build):** S&P 500 companies, last 5 years of quarterly earnings calls. This gives ~10,000 transcripts and overlaps with Edgar Explorer's filing coverage, enabling cross-referencing.

**Phase 2 (expansion):** Extend to 10 years. Add annual shareholder meeting transcripts where available. Add select mid-cap companies of interest to value investors.

### Data Model

Each transcript is structured as:

```
Transcript
├── metadata
│   ├── company (ticker, CIK, name, sector)
│   ├── date
│   ├── quarter (Q1/Q2/Q3/Q4)
│   ├── fiscal_year
│   └── type (quarterly_earnings | annual_meeting | investor_day)
├── prepared_remarks[]
│   ├── speaker (name, role: CEO | CFO | COO | IR | Other)
│   ├── text
│   └── topics[] (extracted)
├── qa_section[]
│   ├── analyst_question
│   │   ├── speaker (name, firm)
│   │   └── text
│   └── management_response
│       ├── speaker (name, role)
│       └── text
└── computed_features
    ├── sentiment (overall, by speaker, by section)
    ├── hedging_score
    ├── forward_looking_ratio
    ├── topics[]
    └── flags[] (anomalies, tone shifts)
```

---

## Features

### 1. Management Tone Tracking

The core feature. For any company, show how management's tone evolves across quarters.

**Sentiment by speaker:** Separate the CEO's tone from the CFO's. CEOs are trained to be optimistic; CFOs are trained to be precise. A divergence between the two is a signal. If the CEO is getting more enthusiastic while the CFO is getting more cautious, that's worth noticing.

**Sentiment by section:** Prepared remarks vs. Q&A. The prepared remarks are scripted and rehearsed. The Q&A is closer to unfiltered. A company that sounds confident in prepared remarks but defensive in Q&A is telling you something.

**Sentiment over time:** Line chart per company showing tone trajectory across quarters. Flag quarters where tone shifted significantly relative to the company's own baseline (not relative to the market — each company has its own rhetorical baseline).

**Dictionary:** Loughran-McDonald (same as Edgar Explorer, enabling cross-referencing). Supplement with a custom hedging/deflection dictionary (see feature 3).

### 2. Promise Tracking

Extract forward-looking statements — guidance language, commitments, targets — and track them over time.

**How it works:** NLP extraction of sentences containing forward-looking markers ("we expect," "our target is," "we plan to," "by year-end," "within the next 12 months"). Tag each with: the claim, the timeframe (if stated), the topic (margins, revenue, capex, headcount, etc.), and the date.

**Promise timeline:** For a given company, show a timeline of commitments made and whether subsequent calls reference the same topic with the same, stronger, or weaker language. Did "we expect 15% margins" become "we're targeting mid-teens margins" become "margins will be pressured in the near term"? That trajectory is the story.

**Promise scorecard (future phase):** Cross-reference forward-looking statements with actual reported results (from Provenance's verified financial data). Quantify the gap between what management said and what happened.

### 3. Hedging & Deflection Detection

A custom dictionary and pattern set for the language of evasion.

**Hedging markers:** "approximately," "roughly," "in that range," "more or less," "subject to," "depending on," "as I mentioned," "as we've discussed," "going forward" (used to avoid specifics), "it's important to note that" (preface to deflection).

**Deflection patterns in Q&A:** Analyst asks about X, management responds about Y. Detecting topic-shift between question and answer. Also: response length — a one-sentence answer to a detailed question is a signal.

**Hedging score:** Per-call, per-speaker. Track over time. A rising hedging score quarter-over-quarter, especially from the CFO, is an early warning.

### 4. Topic Analysis

What is management talking about, and how is the emphasis shifting?

**Topic extraction:** Identify the dominant topics per call (supply chain, pricing, competition, regulation, capital allocation, M&A, workforce, etc.). Track how the topic mix shifts across quarters.

**Emerging topics:** Flag topics that appear for the first time or increase significantly in prominence. If "tariffs" suddenly occupies 15% of the call when it was 2% last quarter, surface that.

**Topic sentiment:** Not just what they're talking about, but how they're talking about it. Positive about pricing, negative about supply chain, neutral about competition. This is the same keyword-contextual sentiment approach used in Edgar Explorer's topic tool.

### 5. Q&A Intelligence

The Q&A section is where the real information lives.

**Analyst focus:** What are analysts asking about? Aggregate across all analysts covering a company to see what the market is worried about. If five analysts ask about inventory and management gives five different non-answers, that's a red flag.

**Response quality:** Quantitative proxy for how directly management addresses questions. Metrics: response length relative to question length, topic overlap between question and answer (are they answering what was asked?), hedging density in responses.

**Analyst sentiment vs. management sentiment:** When analysts are pressing harder (more negative/probing questions) while management is getting more defensive, the gap between the two is information.

### 6. Cross-Company Comparison

**Sector tone:** Compare management tone across companies in the same sector. If every semiconductor CEO is cautious but one is aggressively optimistic, either they know something or they're not being straight.

**Tone leaders:** Historically, some companies' management tone shifts predict sector-wide shifts. (This is an empirical question the tool can help answer.)

### 7. Full-Text Search

Search across all transcripts. Same BM25 approach as Edgar Explorer.

**Filters:** By company, sector, date range, speaker role (CEO only, CFO only), section (prepared remarks only, Q&A only).

**Contextual results:** Show the search term in context with surrounding sentiment highlighted.

### 8. Cross-Reference with Edgar Explorer

Subtext and Edgar Explorer are separate applications, but they cover the same companies over the same time periods. The cross-reference is the compound insight.

**Implementation (Phase 1 — linking):** Subtext results pages include a link to the corresponding company's filings in Edgar Explorer. "See what AAPL said in the 10-K filed the same quarter." Simple URL-based linking using ticker and date.

**Implementation (Phase 2 — integrated view):** A side-by-side comparison view. Left panel: what management said in the earnings call. Right panel: what the 10-K filing says about the same topic. The gap between the two — where the call is more optimistic than the filing, or where the filing discloses risks the call didn't mention — is where the real reading-between-the-lines happens.

**Implementation (Phase 3 — unified query):** A query that spans both datasets: "Show me companies where earnings call sentiment is declining but 10-K risk factors haven't changed." This is the narrative-aware screening capability that doesn't exist anywhere.

---

## Technical Architecture

### Stack

| Component | Technology | Notes |
|---|---|---|
| Data ingestion | Python | Transcript scraping/API ingestion, cleaning, speaker separation |
| NLP pipeline | Python (spaCy, scikit-learn, sentence-transformers) | Sentiment, topic modelling, hedging detection, promise extraction |
| Analytical store | DuckDB | Same approach as Edgar Explorer. Enables fast analytical queries. |
| Web application | Rust (Leptos/Axum) | Same stack as Edgar Explorer. Consistent architecture across portfolio. |
| Search | DuckDB FTS or Tantivy | BM25 full-text search |
| Charts | Pure SVG | Same approach as Edgar Explorer |

### Pipeline

```
Raw transcripts (JSON/HTML)
    → Clean & structure (speaker separation, section tagging)
    → NLP enrichment (sentiment, topics, hedging, promises)
    → Load into DuckDB (facts table, search index)
    → Serve via Leptos/Axum web app
```

### Schema (core tables)

```sql
-- Companies (shared with Edgar Explorer via ticker/CIK)
CREATE TABLE companies (
    ticker VARCHAR PRIMARY KEY,
    cik VARCHAR,
    name VARCHAR,
    sector VARCHAR,
    industry VARCHAR
);

-- Transcripts
CREATE TABLE transcripts (
    transcript_id VARCHAR PRIMARY KEY,
    ticker VARCHAR REFERENCES companies,
    call_date DATE,
    fiscal_quarter VARCHAR,  -- 'Q1', 'Q2', etc.
    fiscal_year INTEGER,
    call_type VARCHAR,       -- 'quarterly_earnings', 'annual_meeting'
    source VARCHAR,
    source_url VARCHAR
);

-- Utterances (individual speaker segments)
CREATE TABLE utterances (
    utterance_id VARCHAR PRIMARY KEY,
    transcript_id VARCHAR REFERENCES transcripts,
    section VARCHAR,          -- 'prepared_remarks' | 'qa_question' | 'qa_response'
    speaker_name VARCHAR,
    speaker_role VARCHAR,     -- 'CEO', 'CFO', 'Analyst', etc.
    speaker_firm VARCHAR,     -- For analysts: their firm
    sequence_order INTEGER,
    text TEXT,
    word_count INTEGER,
    qa_pair_id VARCHAR        -- Links question to its response
);

-- Sentiment facts (per utterance)
CREATE TABLE sentiment_facts (
    utterance_id VARCHAR REFERENCES utterances,
    positive_count INTEGER,
    negative_count INTEGER,
    uncertainty_count INTEGER,
    litigious_count INTEGER,
    constraining_count INTEGER,
    hedging_count INTEGER,    -- Custom dictionary
    forward_looking_count INTEGER,
    total_words INTEGER,
    net_sentiment FLOAT,
    hedging_score FLOAT
);

-- Topics (per transcript)
CREATE TABLE transcript_topics (
    transcript_id VARCHAR REFERENCES transcripts,
    topic VARCHAR,
    weight FLOAT,
    sentiment FLOAT
);

-- Promises (extracted forward-looking statements)
CREATE TABLE promises (
    promise_id VARCHAR PRIMARY KEY,
    transcript_id VARCHAR REFERENCES transcripts,
    utterance_id VARCHAR REFERENCES utterances,
    speaker_role VARCHAR,
    claim_text TEXT,
    topic VARCHAR,
    timeframe VARCHAR,       -- 'next quarter', 'by year-end', 'within 12 months'
    target_date DATE,        -- Parsed if possible
    claim_type VARCHAR       -- 'guidance', 'target', 'commitment', 'expectation'
);
```

---

## Build Phases

### Phase 1: Core (September build)
- Ingest S&P 500 transcripts, last 5 years
- Speaker separation and section tagging
- Loughran-McDonald sentiment per utterance
- Custom hedging dictionary and scoring
- Topic extraction per transcript
- Full-text search
- Company tone timeline (sentiment over quarters)
- CEO vs CFO sentiment divergence
- Prepared remarks vs Q&A sentiment split
- Cross-reference links to Edgar Explorer

### Phase 2: Intelligence Layer
- Promise extraction and tracking
- Q&A response quality scoring
- Analyst-vs-management sentiment divergence
- Cross-company sector comparison
- Emerging topic detection

### Phase 3: Integration
- Side-by-side view with Edgar Explorer
- Promise scorecard (cross-reference with Provenance financial data)
- Unified cross-dataset queries
- Audio ingestion via Whisper (vocal tone analysis)

---

## What This Demonstrates to Employers

**To ACATIS / value investing boutiques:**
"I built the tool your analysts wish they had. Every quarter, they listen to 30 earnings calls and take notes by hand. Subtext makes that process systematic — it tracks management tone, catches hedging language, and remembers what the CEO promised two years ago. Combined with Edgar Explorer, it covers the full landscape of corporate communication. This is what research infrastructure for a value investing firm looks like."

**To ECB / institutional employers:**
"Subtext demonstrates production NLP on financial text at scale — 10,000+ documents, speaker-separated, with multiple analytical layers (sentiment, topic modelling, anomaly detection). The pipeline design, data modelling, and cross-source linking capabilities are directly transferable to any institutional text analytics application."

**To financial research technology (AlphaSense, Quartr):**
"I built a focused version of what you sell. I understand your product because I am your user. Here's what I'd build if I joined your team."