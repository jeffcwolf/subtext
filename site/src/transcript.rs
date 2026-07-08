//! `/transcript/{id}` — the full call as a sequence of utterances, with
//! per-utterance sentiment and speaker-role badges.

use std::collections::BTreeMap;

use axum::{
    extract::{Path, State},
    response::{Html, IntoResponse, Response},
};
use duckdb::params;
use leptos::prelude::*;

use crate::app;
use crate::db::Db;
use crate::types::{TranscriptMeta, Utterance};

pub async fn handler(State(db): State<Db>, Path(id): Path<String>) -> Response {
    match load(&db, id.clone()).await {
        Ok(Some((meta, utterances))) => {
            let title = format!("{} {}", meta.ticker, meta.label);
            Html(app::shell(&title, &render(meta, utterances))).into_response()
        }
        Ok(None) => app::not_found(&format!("No transcript with id “{id}”.")),
        Err(e) => app::error_response(e),
    }
}

async fn load(
    db: &Db,
    id: String,
) -> anyhow::Result<Option<(TranscriptMeta, Vec<Utterance>)>> {
    db.call(move |conn| {
        let mut ms = conn.prepare(
            "SELECT t.transcript_id, t.ticker, c.name, c.sector,
                    CAST(t.call_date AS VARCHAR), t.fiscal_year, t.fiscal_quarter,
                    (SUM(s.positive_count) - SUM(s.negative_count))::DOUBLE
                        / NULLIF(SUM(s.total_words), 0),
                    COALESCE(SUM(s.total_words), 0),
                    MAX(f.eps_ttm), MAX(f.eps_fwd), MAX(f.pe_fwd)
             FROM transcripts t
             JOIN companies c USING (ticker)
             LEFT JOIN utterances u USING (transcript_id)
             LEFT JOIN sentiment_facts s USING (utterance_id)
             LEFT JOIN financials f USING (transcript_id)
             WHERE t.transcript_id = ?
             GROUP BY t.transcript_id, t.ticker, c.name, c.sector, t.call_date,
                      t.fiscal_year, t.fiscal_quarter",
        )?;
        let mut mrows = ms.query_map(params![id], |r| {
            let year: Option<i32> = r.get(5)?;
            let quarter: Option<String> = r.get(6)?;
            let label = match (year, quarter.as_deref()) {
                (Some(y), Some(q)) => format!("{y} {q}"),
                (Some(y), None) => y.to_string(),
                _ => "—".to_string(),
            };
            Ok(TranscriptMeta {
                transcript_id: r.get(0)?,
                ticker: r.get(1)?,
                company_name: r.get::<_, Option<String>>(2)?.unwrap_or_default(),
                sector: r.get(3)?,
                call_date: r.get(4)?,
                label,
                overall: r.get(7)?,
                total_words: r.get(8)?,
                eps_ttm: r.get(9)?,
                eps_fwd: r.get(10)?,
                pe_fwd: r.get(11)?,
            })
        })?;
        let meta = match mrows.next() {
            Some(m) => m?,
            None => return Ok(None),
        };
        drop(mrows);
        drop(ms);

        let mut us = conn.prepare(
            "SELECT u.section, u.speaker_name, u.speaker_role, u.text,
                    COALESCE(s.positive_count, 0), COALESCE(s.negative_count, 0),
                    s.net_sentiment, u.word_count
             FROM utterances u
             LEFT JOIN sentiment_facts s USING (utterance_id)
             WHERE u.transcript_id = ?
             ORDER BY u.sequence_order",
        )?;
        let rows = us.query_map(params![id], |r| {
            Ok(Utterance {
                section: r.get(0)?,
                speaker_name: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                speaker_role: r.get::<_, Option<String>>(2)?.unwrap_or_else(|| "Other".into()),
                text: r.get::<_, Option<String>>(3)?.unwrap_or_default(),
                positive: r.get(4)?,
                negative: r.get(5)?,
                net_sentiment: r.get::<_, Option<f64>>(6)?,
                word_count: r.get(7)?,
            })
        })?;
        let utterances = rows.collect::<Result<Vec<_>, _>>()?;
        Ok(Some((meta, utterances)))
    })
    .await
}

fn render(meta: TranscriptMeta, utterances: Vec<Utterance>) -> String {
    // Words spoken by each management/analyst role, for the header stats.
    // Owned keys so the map doesn't borrow `utterances` across the move below.
    let mut by_role: BTreeMap<String, i64> = BTreeMap::new();
    for u in &utterances {
        *by_role.entry(u.speaker_role.clone()).or_insert(0) += u.word_count;
    }
    let role_stat = |role: &str| -> String {
        by_role.get(role).copied().unwrap_or(0).to_string()
    };

    let company_href = format!("/company/{}", meta.ticker);
    let overall_pill = format!("pill {}", app::sentiment_class(meta.overall));
    let date = meta.call_date.clone().unwrap_or_else(|| "—".to_string());
    let sector = meta.sector.clone().unwrap_or_else(|| "—".to_string());
    let ceo_words = role_stat("CEO");
    let cfo_words = role_stat("CFO");
    let analyst_words = role_stat("Analyst");
    let has_fin = meta.eps_ttm.is_some() || meta.eps_fwd.is_some() || meta.pe_fwd.is_some();
    let eps_ttm = app::fmt_money(meta.eps_ttm);
    let eps_fwd = app::fmt_money(meta.eps_fwd);
    let pe_fwd = app::fmt_ratio(meta.pe_fwd);
    let fin_html = if has_fin {
        format!(
            r#"<div class="stat-row" style="margin-top:0.75rem">
  <div class="stat"><span class="k">Trailing EPS</span><span class="v mono">{ttm}</span></div>
  <div class="stat"><span class="k">Forward EPS est.</span><span class="v mono">{fwd}</span></div>
  <div class="stat"><span class="k">Forward P/E</span><span class="v mono">{pe}</span></div>
  <div class="stat"><span class="k">Source</span><span class="v muted">glopardo</span></div>
</div>"#,
            ttm = eps_ttm, fwd = eps_fwd, pe = pe_fwd
        )
    } else {
        String::new()
    };

    view! {
        <section class="card">
            <p class="muted"><a href=company_href>{"← "}{meta.ticker.clone()}</a></p>
            <h1>{meta.company_name.clone()}" — "{meta.label.clone()}</h1>
            <div class="stat-row">
                <div class="stat"><span class="k">"Sector"</span><span class="v">{sector}</span></div>
                <div class="stat"><span class="k">"Date"</span><span class="v mono">{date}</span></div>
                <div class="stat"><span class="k">"Overall sentiment"</span>
                    <span class="v"><span class=overall_pill>{app::fmt_sentiment(meta.overall)}</span></span></div>
                <div class="stat"><span class="k">"Total words"</span><span class="v">{meta.total_words}</span></div>
                <div class="stat"><span class="k">"CEO words"</span><span class="v">{ceo_words}</span></div>
                <div class="stat"><span class="k">"CFO words"</span><span class="v">{cfo_words}</span></div>
                <div class="stat"><span class="k">"Analyst words"</span><span class="v">{analyst_words}</span></div>
            </div>
            <div inner_html=fin_html></div>
        </section>

        <section class="card">
            <h2>"Transcript"</h2>
            <p class="muted">
                "Each turn shows the speaker, their inferred role, the section, and that turn's net sentiment (×1000)."
            </p>
            <div class="transcript">
                {utterances.into_iter().map(|u| {
                    let cls = format!("utterance section-{}", u.section);
                    let badge = format!("badge {}", app::role_class(&u.speaker_role));
                    let pill = format!("pill {}", app::sentiment_class(u.net_sentiment));
                    let section = app::section_label(&u.section);
                    let counts = format!("+{} / −{}", u.positive, u.negative);
                    view! {
                        <div class=cls>
                            <div class="meta">
                                <span class="who">{u.speaker_name.clone()}</span>
                                <span class=badge>{u.speaker_role.clone()}</span>
                                <span class="section-tag">{section}</span>
                                <span class=pill>{app::fmt_sentiment(u.net_sentiment)}</span>
                                <span class="section-tag mono">{counts}</span>
                            </div>
                            <p class="body">{u.text.clone()}</p>
                        </div>
                    }
                }).collect_view()}
            </div>
        </section>
    }
    .to_html()
}
