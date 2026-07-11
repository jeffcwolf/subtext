//! `/sectors` and `/sector/{name}` — cross-company tone comparison within a
//! sector (SPEC #6). Sector data comes from glopardo.

use axum::{
    extract::{Path, State},
    response::{Html, IntoResponse, Response},
};
use duckdb::params;
use leptos::prelude::*;

use crate::app;
use crate::db::Db;
use crate::sql::NET_SENTIMENT;
use crate::types::{SectorCompany, SectorSummary};

pub async fn list_handler(State(db): State<Db>) -> Response {
    match load_sectors(&db).await {
        Ok(sectors) => Html(app::shell("Sectors", &render_list(sectors))).into_response(),
        Err(e) => app::error_response(e),
    }
}

pub async fn detail_handler(State(db): State<Db>, Path(sector): Path<String>) -> Response {
    match load_sector(&db, sector.clone()).await {
        Ok(companies) if !companies.is_empty() => {
            Html(app::shell(&sector, &render_detail(&sector, companies))).into_response()
        }
        Ok(_) => app::not_found(&format!("No sector “{sector}”, or no companies with data.")),
        Err(e) => app::error_response(e),
    }
}

async fn load_sectors(db: &Db) -> anyhow::Result<Vec<SectorSummary>> {
    db.call(|conn| {
        let sql = format!(
            "SELECT c.sector, COUNT(DISTINCT c.ticker), COUNT(DISTINCT t.transcript_id), {NET_SENTIMENT}
             FROM companies c
             JOIN transcripts t USING (ticker)
             JOIN utterances u USING (transcript_id)
             JOIN sentiment_facts s USING (utterance_id)
             WHERE c.sector IS NOT NULL AND c.sector <> ''
             GROUP BY c.sector
             ORDER BY COUNT(DISTINCT c.ticker) DESC, c.sector"
        );
        let mut stmt = conn.prepare(&sql)?;
        let rows = stmt.query_map([], |r| {
            Ok(SectorSummary {
                sector: r.get(0)?,
                companies: r.get(1)?,
                transcripts: r.get(2)?,
                avg_sentiment: r.get(3)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    })
    .await
}

async fn load_sector(db: &Db, sector: String) -> anyhow::Result<Vec<SectorCompany>> {
    db.call(move |conn| {
        let sql = format!(
            "SELECT c.ticker, c.name, COUNT(DISTINCT t.transcript_id), {NET_SENTIMENT}
             FROM companies c
             JOIN transcripts t USING (ticker)
             JOIN utterances u USING (transcript_id)
             JOIN sentiment_facts s USING (utterance_id)
             WHERE c.sector = ?
             GROUP BY c.ticker, c.name
             ORDER BY {NET_SENTIMENT} DESC NULLS LAST"
        );
        let mut stmt = conn.prepare(&sql)?;
        let rows = stmt.query_map(params![sector], |r| {
            Ok(SectorCompany {
                ticker: r.get(0)?,
                name: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                transcripts: r.get(2)?,
                avg_sentiment: r.get(3)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    })
    .await
}

fn render_list(sectors: Vec<SectorSummary>) -> String {
    view! {
        <section class="card">
            <h1>"Sectors"</h1>
            <p class="muted">
                "Average management tone by sector. Open a sector to compare its companies — \
                 an outlier (unusually upbeat or cautious relative to peers) is worth a look."
            </p>
            <table class="tbl">
                <thead>
                    <tr><th>"Sector"</th><th class="num">"Companies"</th>
                        <th class="num">"Transcripts"</th><th class="num">"Avg tone ×1000"</th></tr>
                </thead>
                <tbody>
                {sectors.into_iter().map(|s| {
                    let href = format!("/sector/{}", app::urlencode(&s.sector));
                    let pill = app::pill_class(s.avg_sentiment);
                    view! {
                        <tr>
                            <td><a href=href>{s.sector.clone()}</a></td>
                            <td class="num">{s.companies}</td>
                            <td class="num">{s.transcripts}</td>
                            <td class="num"><span class=pill>{app::fmt_sentiment(s.avg_sentiment)}</span></td>
                        </tr>
                    }
                }).collect_view()}
                </tbody>
            </table>
        </section>
    }
    .to_html()
}

fn render_detail(sector: &str, companies: Vec<SectorCompany>) -> String {
    // Sector mean = simple mean of company averages (equal weight per company).
    let vals: Vec<f64> = companies.iter().filter_map(|c| c.avg_sentiment).collect();
    let mean = if vals.is_empty() {
        0.0
    } else {
        vals.iter().sum::<f64>() / vals.len() as f64
    };
    let n_companies = companies.len();
    let total_transcripts: i64 = companies.iter().map(|c| c.transcripts).sum();

    // Extremes for the callout (first/last with data).
    let most_upbeat = companies.iter().find(|c| c.avg_sentiment.is_some());
    let most_cautious = companies.iter().rev().find(|c| c.avg_sentiment.is_some());
    let callout = match (most_upbeat, most_cautious) {
        (Some(u), Some(d)) if u.ticker != d.ticker => format!(
            r#"<p>Most upbeat: <a href="/company/{ut}"><strong>{ut}</strong></a> ({uv}). Most cautious: <a href="/company/{dt}"><strong>{dt}</strong></a> ({dv}).</p>"#,
            ut = app::escape(&u.ticker),
            uv = app::fmt_sentiment(u.avg_sentiment),
            dt = app::escape(&d.ticker),
            dv = app::fmt_sentiment(d.avg_sentiment),
        ),
        _ => String::new(),
    };

    let rows: String = companies
        .into_iter()
        .enumerate()
        .map(|(i, c)| {
            let pill = app::pill_class(c.avg_sentiment);
            let delta = c.avg_sentiment.map(|v| v - mean);
            let delta_pill = app::pill_class(delta);
            format!(
                r#"<tr>
  <td class="num mono">{rank}</td>
  <td><a href="/company/{tk}"><strong class="mono">{tk}</strong></a></td>
  <td>{name}</td>
  <td class="num">{tr}</td>
  <td class="num"><span class="{pill}">{sent}</span></td>
  <td class="num"><span class="{dpill}">{delta}</span></td>
</tr>"#,
                rank = i + 1,
                tk = app::escape(&c.ticker),
                name = app::escape(&c.name),
                tr = c.transcripts,
                pill = pill,
                sent = app::fmt_sentiment(c.avg_sentiment),
                dpill = delta_pill,
                delta = app::fmt_sentiment(delta),
            )
        })
        .collect();

    let mpill = app::pill_class(Some(mean));
    format!(
        r#"<section class="card">
  <p class="muted"><a href="/sectors">← All sectors</a></p>
  <h1>{sector}</h1>
  <div class="stat-row">
    <div class="stat"><span class="k">Companies</span><span class="v">{n}</span></div>
    <div class="stat"><span class="k">Transcripts</span><span class="v">{tt}</span></div>
    <div class="stat"><span class="k">Sector avg tone ×1000</span><span class="v"><span class="{mpill}">{mean}</span></span></div>
  </div>
  {callout}
</section>
<section class="card">
  <h2>Companies ranked by tone</h2>
  <p class="muted">Average net sentiment across all of each company's calls, with each company's deviation from the sector average.</p>
  <table class="tbl">
    <thead><tr><th class="num">#</th><th>Ticker</th><th>Company</th><th class="num">Transcripts</th><th class="num">Avg tone</th><th class="num">vs sector</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>"#,
        sector = app::escape(sector),
        n = n_companies,
        tt = total_transcripts,
        mpill = mpill,
        mean = app::fmt_sentiment(Some(mean)),
        callout = callout,
        rows = rows,
    )
}
