//! Page shell, navigation, and small shared render helpers.

use axum::{
    http::StatusCode,
    response::{Html, IntoResponse, Response},
};

/// Wrap rendered body HTML in the full document with nav + footer.
pub fn shell(title: &str, body: &str) -> String {
    format!(
        r#"<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Subtext</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<header class="topbar">
  <a class="brand" href="/">Subtext</a>
  <nav class="mainnav">
    <a href="/">Home</a>
    <a href="/sectors">Sectors</a>
    <a href="/search">Search</a>
    <a href="/about">About</a>
  </nav>
</header>
<main class="page">
{body}
</main>
<footer class="sitefooter">
  <span>Subtext — reading between the lines of earnings calls.</span>
  <span class="muted">Loughran-McDonald sentiment · kurry S&amp;P 500 transcripts</span>
</footer>
</body>
</html>"#,
        title = escape(title),
        body = body,
    )
}

/// Minimal HTML-attribute/text escaping for values interpolated into the raw
/// `format!` shell (Leptos already escapes text inside `view!`).
pub fn escape(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for c in s.chars() {
        match c {
            '&' => out.push_str("&amp;"),
            '<' => out.push_str("&lt;"),
            '>' => out.push_str("&gt;"),
            '"' => out.push_str("&quot;"),
            '\'' => out.push_str("&#39;"),
            _ => out.push(c),
        }
    }
    out
}

/// Percent-encode a string for use in a URL path segment.
pub fn urlencode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// A 500 page for an unexpected error. The detail is logged server-side rather
/// than shown to the client, so a public instance doesn't leak query internals,
/// schema, or filesystem paths in error text.
pub fn error_response(err: anyhow::Error) -> Response {
    eprintln!("request error: {err:#}");
    let body = r#"<section class="card"><h1>Something went wrong</h1>
<p class="muted">The database query failed. Please try again.</p></section>"#;
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Html(shell("Error", body)),
    )
        .into_response()
}

/// A 404 page.
pub fn not_found(message: &str) -> Response {
    let body = format!(
        r#"<section class="card"><h1>Not found</h1><p>{}</p>
<p><a href="/">← Back home</a></p></section>"#,
        escape(message)
    );
    (StatusCode::NOT_FOUND, Html(shell("Not found", &body))).into_response()
}

/// CSS class for a net-sentiment value (drives the coloured pill).
pub fn sentiment_class(v: Option<f64>) -> &'static str {
    match v {
        Some(x) if x > 0.005 => "pos",
        Some(x) if x < -0.005 => "neg",
        Some(_) => "neu",
        None => "na",
    }
}

/// Format a net-sentiment value as a signed, scaled score (× 1000 for legibility).
pub fn fmt_sentiment(v: Option<f64>) -> String {
    match v {
        Some(x) => format!("{:+.1}", x * 1000.0),
        None => "—".to_string(),
    }
}

/// Format an optional dollar figure (e.g. EPS).
pub fn fmt_money(v: Option<f64>) -> String {
    match v {
        Some(x) => format!("${x:.2}"),
        None => "—".to_string(),
    }
}

/// Format an optional ratio (e.g. P/E).
pub fn fmt_ratio(v: Option<f64>) -> String {
    match v {
        Some(x) => format!("{x:.1}"),
        None => "—".to_string(),
    }
}

/// Human-readable label for a section code.
pub fn section_label(section: &str) -> &'static str {
    match section {
        "prepared_remarks" => "Prepared remarks",
        "qa_question" => "Q&A question",
        "qa_response" => "Q&A response",
        "operator" => "Operator",
        _ => "Other",
    }
}

/// CSS modifier for a speaker-role badge.
pub fn role_class(role: &str) -> &'static str {
    match role {
        "CEO" => "role-ceo",
        "CFO" => "role-cfo",
        "COO" => "role-coo",
        "IR" => "role-ir",
        "Analyst" => "role-analyst",
        "Operator" => "role-operator",
        _ => "role-other",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn escape_covers_all_html_metacharacters() {
        assert_eq!(
            escape(r#"<a href="x">& '"#),
            "&lt;a href=&quot;x&quot;&gt;&amp; &#39;"
        );
        // Plain text is passed through untouched.
        assert_eq!(escape("Consolidated revenue"), "Consolidated revenue");
    }

    #[test]
    fn urlencode_preserves_unreserved_and_encodes_the_rest() {
        // Unreserved characters (RFC 3986) survive verbatim.
        assert_eq!(urlencode("AZaz09-_.~"), "AZaz09-_.~");
        // Spaces and other bytes are percent-encoded, uppercase hex.
        assert_eq!(urlencode("Consumer Staples"), "Consumer%20Staples");
        assert_eq!(urlencode("S&P/500"), "S%26P%2F500");
    }

    #[test]
    fn sentiment_class_uses_a_dead_band_around_zero() {
        assert_eq!(sentiment_class(Some(0.006)), "pos");
        assert_eq!(sentiment_class(Some(-0.006)), "neg");
        assert_eq!(sentiment_class(Some(0.0)), "neu");
        assert_eq!(sentiment_class(Some(0.005)), "neu"); // boundary is exclusive
        assert_eq!(sentiment_class(None), "na");
    }

    #[test]
    fn fmt_sentiment_scales_by_1000_and_signs() {
        assert_eq!(fmt_sentiment(Some(0.0123)), "+12.3");
        assert_eq!(fmt_sentiment(Some(-0.002)), "-2.0");
        assert_eq!(fmt_sentiment(None), "—");
    }

    #[test]
    fn labels_map_known_codes_and_fall_back() {
        assert_eq!(section_label("qa_response"), "Q&A response");
        assert_eq!(section_label("prepared_remarks"), "Prepared remarks");
        assert_eq!(section_label("something_else"), "Other");
        assert_eq!(role_class("CEO"), "role-ceo");
        assert_eq!(role_class("Chairman"), "role-other");
    }
}
