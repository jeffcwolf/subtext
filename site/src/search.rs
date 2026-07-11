//! `/search` — BM25 full-text search over utterances, with filters.

use axum::{
    extract::{Query, State},
    response::{Html, IntoResponse, Response},
};
use duckdb::{params_from_iter, types::Value};
use serde::Deserialize;

use crate::app;
use crate::db::Db;
use crate::types::SearchHit;

#[derive(Debug, Deserialize)]
pub struct SearchParams {
    #[serde(default)]
    pub q: String,
    #[serde(default)]
    pub ticker: String,
    #[serde(default)]
    pub role: String,
    #[serde(default)]
    pub section: String,
}

pub async fn handler(State(db): State<Db>, Query(p): Query<SearchParams>) -> Response {
    let query = p.q.trim().to_string();
    if query.is_empty() {
        return Html(app::shell("Search", &render(&p, Ok(Vec::new()), true))).into_response();
    }
    let result = search(&db, &p).await;
    Html(app::shell("Search", &render(&p, result, false))).into_response()
}

async fn search(db: &Db, p: &SearchParams) -> anyhow::Result<Vec<SearchHit>> {
    let query = p.q.trim().to_string();
    let ticker = p.ticker.trim().to_uppercase();
    let role = p.role.trim().to_string();
    let section = p.section.trim().to_string();

    db.call_fts(move |conn| {
        let mut sql = String::from(
            "SELECT u.transcript_id, t.ticker, c.name, CAST(t.call_date AS VARCHAR),
                    u.speaker_name, u.speaker_role, u.section, u.text
             FROM (
                 SELECT utterance_id,
                        fts_main_utterances.match_bm25(utterance_id, ?) AS score
                 FROM utterances
             ) sub
             JOIN utterances u USING (utterance_id)
             JOIN transcripts t USING (transcript_id)
             JOIN companies c USING (ticker)
             WHERE sub.score IS NOT NULL",
        );
        let mut binds: Vec<Value> = vec![Value::Text(query)];
        if !ticker.is_empty() {
            sql.push_str(" AND t.ticker = ?");
            binds.push(Value::Text(ticker));
        }
        if !role.is_empty() {
            sql.push_str(" AND u.speaker_role = ?");
            binds.push(Value::Text(role));
        }
        if !section.is_empty() {
            sql.push_str(" AND u.section = ?");
            binds.push(Value::Text(section));
        }
        sql.push_str(" ORDER BY sub.score DESC LIMIT 40");

        let mut stmt = conn.prepare(&sql)?;
        let rows = stmt.query_map(params_from_iter(binds.iter()), |r| {
            Ok(SearchHit {
                transcript_id: r.get(0)?,
                ticker: r.get(1)?,
                company_name: r.get::<_, Option<String>>(2)?.unwrap_or_default(),
                call_date: r.get(3)?,
                speaker_name: r.get::<_, Option<String>>(4)?.unwrap_or_default(),
                speaker_role: r
                    .get::<_, Option<String>>(5)?
                    .unwrap_or_else(|| "Other".into()),
                section: r.get(6)?,
                snippet: r.get::<_, Option<String>>(7)?.unwrap_or_default(),
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    })
    .await
}

fn option_tag(value: &str, label: &str, selected: &str) -> String {
    let sel = if value == selected { " selected" } else { "" };
    format!(
        r#"<option value="{v}"{sel}>{l}</option>"#,
        v = app::escape(value),
        l = app::escape(label),
        sel = sel
    )
}

fn render(p: &SearchParams, result: anyhow::Result<Vec<SearchHit>>, empty_query: bool) -> String {
    // Filter controls (raw HTML so we can pre-select from the query string).
    let roles = [
        "", "CEO", "CFO", "COO", "IR", "Analyst", "Operator", "Other",
    ];
    let role_opts: String = roles
        .iter()
        .map(|r| option_tag(r, if r.is_empty() { "Any role" } else { r }, &p.role))
        .collect();
    let sections = [
        ("", "Any section"),
        ("prepared_remarks", "Prepared remarks"),
        ("qa_question", "Q&A question"),
        ("qa_response", "Q&A response"),
        ("operator", "Operator"),
    ];
    let section_opts: String = sections
        .iter()
        .map(|(v, l)| option_tag(v, l, &p.section))
        .collect();

    let form = format!(
        r#"<form action="/search" method="get">
  <div class="searchbar">
    <input type="search" name="q" value="{q}" placeholder="Search across all transcripts…" aria-label="Search"/>
    <button type="submit">Search</button>
  </div>
  <div class="filters">
    <label>Ticker<input type="text" name="ticker" value="{ticker}" placeholder="e.g. AAPL"/></label>
    <label>Role<select name="role">{roles}</select></label>
    <label>Section<select name="section">{sections}</select></label>
  </div>
</form>"#,
        q = app::escape(&p.q),
        ticker = app::escape(&p.ticker),
        roles = role_opts,
        sections = section_opts,
    );

    let tokens: Vec<String> =
        p.q.split_whitespace()
            .map(|t| t.to_lowercase())
            .filter(|t| t.len() >= 2)
            .collect();

    let results_html = if empty_query {
        r#"<p class="muted">Enter a query above to search every utterance by BM25 relevance.</p>"#
            .to_string()
    } else {
        match result {
            Err(e) => {
                eprintln!("search error: {e:#}");
                r#"<p class="muted">Search is unavailable — the DuckDB full-text index isn't loaded.</p>"#
                    .to_string()
            }
            Ok(hits) if hits.is_empty() => r#"<p class="muted">No matches.</p>"#.to_string(),
            Ok(hits) => {
                let mut out = format!(r#"<p class="muted">{} results.</p>"#, hits.len());
                for h in &hits {
                    let href = format!("/transcript/{}", h.transcript_id);
                    let badge = app::role_class(&h.speaker_role);
                    let date = h.call_date.clone().unwrap_or_default();
                    out.push_str(&format!(
                        r#"<div class="hit">
  <div class="head">
    <a href="/company/{tk}"><strong class="mono">{tk}</strong></a>
    <span class="muted">{name}</span>
    <span class="mono muted">{date}</span>
    <span class="badge {badge}">{role}</span>
    <span class="who">{speaker}</span>
    <span class="section-tag">{section}</span>
    <a href="{href}">open →</a>
  </div>
  <div class="snippet">{snippet}</div>
</div>"#,
                        tk = app::escape(&h.ticker),
                        name = app::escape(&h.company_name),
                        date = app::escape(&date),
                        badge = badge,
                        role = app::escape(&h.speaker_role),
                        speaker = app::escape(&h.speaker_name),
                        section = app::escape(app::section_label(&h.section)),
                        href = app::escape(&href),
                        snippet = snippet_html(&h.snippet, &tokens),
                    ));
                }
                out
            }
        }
    };

    format!(
        r#"<section class="card">
<h1>Search</h1>
{form}
</section>
<section class="card">
{results_html}
</section>"#
    )
}

/// Build a highlighted, windowed snippet around the first matching token.
fn snippet_html(text: &str, tokens: &[String]) -> String {
    let chars: Vec<char> = text.chars().collect();
    let lower: Vec<char> = text.to_lowercase().chars().collect();
    // Guard: to_lowercase can change length; fall back to plain if mismatched.
    if lower.len() != chars.len() || tokens.is_empty() {
        let plain: String = chars.iter().take(240).collect();
        return app::escape(&plain);
    }
    let tok_chars: Vec<Vec<char>> = tokens.iter().map(|t| t.chars().collect()).collect();

    let matches_at = |i: usize| -> Option<usize> {
        for tc in &tok_chars {
            if i + tc.len() <= lower.len() && lower[i..i + tc.len()] == tc[..] {
                return Some(tc.len());
            }
        }
        None
    };

    // Find the first match to centre the window on.
    let first = (0..chars.len())
        .find(|&i| matches_at(i).is_some())
        .unwrap_or(0);
    let start = first.saturating_sub(55);
    let end = (first + 200).min(chars.len());

    let mut out = String::new();
    if start > 0 {
        out.push('…');
    }
    let mut i = start;
    while i < end {
        if let Some(len) = matches_at(i) {
            let word: String = chars[i..i + len].iter().collect();
            out.push_str("<mark>");
            out.push_str(&app::escape(&word));
            out.push_str("</mark>");
            i += len;
        } else {
            out.push_str(&app::escape(&chars[i].to_string()));
            i += 1;
        }
    }
    if end < chars.len() {
        out.push('…');
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn snippet_highlights_matching_tokens() {
        let out = snippet_html("Revenue grew strongly", &["revenue".to_string()]);
        assert!(out.contains("<mark>Revenue</mark>"), "got: {out}");
        assert!(out.contains("grew strongly"));
    }

    #[test]
    fn snippet_escapes_html_in_both_matches_and_surrounding_text() {
        let out = snippet_html("a <b> tag & more", &["tag".to_string()]);
        assert!(out.contains("&lt;b&gt;"), "angle brackets escaped: {out}");
        assert!(out.contains("&amp;"), "ampersand escaped: {out}");
        assert!(out.contains("<mark>tag</mark>"));
        // No raw markup leaks through.
        assert!(!out.contains("<b>"));
    }

    #[test]
    fn snippet_with_no_tokens_returns_escaped_plain_text() {
        let out = snippet_html("plain <text> here", &[]);
        assert_eq!(out, "plain &lt;text&gt; here");
        assert!(!out.contains("<mark>"));
    }
}
