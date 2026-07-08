//! Row types returned by the DuckDB queries.

#[derive(Clone, Debug)]
pub struct CoveredCompany {
    pub ticker: String,
    pub name: String,
    pub transcripts: i64,
}

#[derive(Clone, Debug)]
pub struct CompanyHeader {
    pub ticker: String,
    pub name: String,
    pub sector: Option<String>,
    pub industry: Option<String>,
    pub transcripts: i64,
    pub first_date: Option<String>,
    pub last_date: Option<String>,
}

/// One call's aggregate sentiment, used for the timeline and the panels.
#[derive(Clone, Debug)]
pub struct CallPoint {
    pub transcript_id: String,
    pub fiscal_year: Option<i32>,
    pub fiscal_quarter: Option<String>,
    pub call_date: Option<String>,
    /// Label like "2021 Q3".
    pub label: String,
    pub overall: Option<f64>,
    pub ceo: Option<f64>,
    pub cfo: Option<f64>,
    pub prepared: Option<f64>,
    pub qa: Option<f64>,
    // glopardo financials matched to this call (may be absent).
    pub eps_ttm: Option<f64>,
    pub eps_fwd: Option<f64>,
    pub pe_fwd: Option<f64>,
}

#[derive(Clone, Debug)]
pub struct RecentTranscript {
    pub transcript_id: String,
    pub call_date: Option<String>,
    pub label: String,
    pub overall: Option<f64>,
}

/// A single utterance rendered on the transcript page.
#[derive(Clone, Debug)]
pub struct Utterance {
    pub section: String,
    pub speaker_name: String,
    pub speaker_role: String,
    pub text: String,
    pub positive: i64,
    pub negative: i64,
    pub net_sentiment: Option<f64>,
    pub word_count: i64,
}

#[derive(Clone, Debug)]
pub struct TranscriptMeta {
    pub transcript_id: String,
    pub ticker: String,
    pub company_name: String,
    pub call_date: Option<String>,
    pub label: String,
    pub overall: Option<f64>,
    pub total_words: i64,
    pub sector: Option<String>,
    pub eps_ttm: Option<f64>,
    pub eps_fwd: Option<f64>,
    pub pe_fwd: Option<f64>,
}

#[derive(Clone, Debug)]
pub struct SearchHit {
    pub transcript_id: String,
    pub ticker: String,
    pub company_name: String,
    pub call_date: Option<String>,
    pub speaker_name: String,
    pub speaker_role: String,
    pub section: String,
    pub snippet: String,
    pub score: f64,
}
