//! `/about` — what Subtext is, data sources, and methodology.

use axum::response::{Html, IntoResponse, Response};
use leptos::prelude::*;

use crate::app;

pub async fn handler() -> Response {
    Html(app::shell("About", &render())).into_response()
}

fn render() -> String {
    view! {
        <section class="card prose">
            <h1>"About Subtext"</h1>
            <p>
                "Subtext is a research tool for fundamental investors. It applies natural-language \
                 processing to earnings-call transcripts, surfacing what management's language \
                 reveals beyond the numbers: tone shifts over time, divergence between how the CEO \
                 and CFO talk, and the gap between scripted prepared remarks and the unscripted Q&A."
            </p>

            <h2>"Data"</h2>
            <p>
                "The transcripts come from the "
                <a href="https://huggingface.co/datasets/kurry/sp500_earnings_transcripts">
                    "kurry/sp500_earnings_transcripts"</a>
                " dataset — 33,000+ earnings calls for S&P 500 companies, 2005–2025, segmented \
                 speaker by speaker. Each call is split into utterances, and each utterance is \
                 tagged with a section (prepared remarks, Q&A question, Q&A response, operator) \
                 and a speaker role (CEO, CFO, COO, IR, analyst, operator)."
            </p>

            <h2>"Methodology"</h2>
            <p>
                "Sentiment is measured with the "
                <a href="https://sraf.nd.edu/loughran-mcdonald-master-dictionary/">
                    "Loughran-McDonald Master Dictionary"</a>
                ", a finance-specific word list. For every utterance we count positive, negative, \
                 uncertainty, litigious, and constraining words, and compute a net sentiment score \
                 of (positive − negative) ÷ total words. Aggregating these by call, by speaker \
                 role, and by section produces the charts on each company page."
            </p>
            <p>
                "Speaker roles and section boundaries are inferred with heuristics: roles from how \
                 people are introduced in the prepared remarks, and the Q&A boundary from the \
                 operator's hand-off to the first analyst. Classification is good but not perfect \
                 — treat role-level figures as strong signals rather than exact truth."
            </p>

            <h2>"Related work"</h2>
            <p>
                "The same class of speaker-segmented S&P 500 transcript data underpins ECB Working \
                 Paper No. 3093 on central-bank and corporate communication. Subtext focuses on the \
                 investor's question: is this management team getting more cautious, and where?"
            </p>
        </section>
    }
    .to_html()
}
