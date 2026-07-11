//! Shared SQL fragments, so the definition of a derived metric lives in one
//! place instead of being copied into every query that needs it.

/// Net Loughran-McDonald sentiment over an aggregated set of `sentiment_facts`
/// rows aliased `s`: (Σ positive − Σ negative) ÷ Σ words, as a `DOUBLE`, and
/// `NULL` when the set has no words.
pub const NET_SENTIMENT: &str =
    "(SUM(s.positive_count) - SUM(s.negative_count))::DOUBLE / NULLIF(SUM(s.total_words), 0)";

/// Like [`NET_SENTIMENT`], but only over the rows for which `filter` (a SQL
/// boolean over the joined `u`/`s` columns) holds — so a single grouped query
/// can produce sentiment sliced by role or section. `filter = "TRUE"` yields
/// the same value as [`NET_SENTIMENT`].
pub fn net_sentiment_where(filter: &str) -> String {
    format!(
        "(SUM(CASE WHEN {f} THEN s.positive_count ELSE 0 END) \
          - SUM(CASE WHEN {f} THEN s.negative_count ELSE 0 END))::DOUBLE \
         / NULLIF(SUM(CASE WHEN {f} THEN s.total_words ELSE 0 END), 0)",
        f = filter
    )
}
