//! `/` — description, search box, and the most-covered companies.

use axum::{extract::State, response::{Html, IntoResponse, Response}};
use leptos::prelude::*;

use crate::app;
use crate::db::Db;
use crate::types::CoveredCompany;

pub async fn handler(State(db): State<Db>) -> Response {
    match load(&db).await {
        Ok(companies) => Html(app::shell("Home", &render(companies))).into_response(),
        Err(e) => app::error_response(e),
    }
}

async fn load(db: &Db) -> anyhow::Result<Vec<CoveredCompany>> {
    db.call(|conn| {
        let mut stmt = conn.prepare(
            "SELECT c.ticker, c.name, COUNT(*) AS n
             FROM transcripts t JOIN companies c USING (ticker)
             GROUP BY 1, 2 ORDER BY n DESC, c.ticker LIMIT 24",
        )?;
        let rows = stmt.query_map([], |r| {
            Ok(CoveredCompany {
                ticker: r.get(0)?,
                name: r.get::<_, Option<String>>(1)?.unwrap_or_default(),
                transcripts: r.get(2)?,
            })
        })?;
        rows.collect::<Result<Vec<_>, _>>().map_err(Into::into)
    })
    .await
}

fn render(companies: Vec<CoveredCompany>) -> String {
    view! {
        <section class="hero">
            <h1>"Subtext"</h1>
            <p class="lede">
                "Earnings calls, read between the lines. Subtext applies NLP to management \
                 commentary — tracking tone shifts, CEO-versus-CFO divergence, and the gap \
                 between prepared remarks and the unscripted Q&A."
            </p>
            <form class="searchbar" action="/search" method="get">
                <input type="search" name="q" placeholder="Search across all transcripts…"
                    aria-label="Search transcripts"/>
                <button type="submit">"Search"</button>
            </form>
        </section>
        <section class="card">
            <h2>"Most-covered companies"</h2>
            <p class="muted">"The companies with the most earnings calls in the dataset."</p>
            <ul class="company-grid">
                {companies.into_iter().map(|c| {
                    let href = format!("/company/{}", c.ticker);
                    view! {
                        <li>
                            <a href=href>
                                <span class="ticker">{c.ticker}</span>
                                <span class="cname">{c.name}</span>
                                <span class="count">{c.transcripts}" calls"</span>
                            </a>
                        </li>
                    }
                }).collect_view()}
            </ul>
        </section>
    }
    .to_html()
}
