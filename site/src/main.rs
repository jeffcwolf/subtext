//! Subtext web app — Leptos 0.8 SSR served by Axum 0.8, reading a DuckDB file.

mod about;
mod app;
mod chart;
mod company;
mod db;
mod home;
mod search;
mod transcript;
mod types;

use axum::{http::header, response::IntoResponse, routing::get, Router};

use db::Db;

#[tokio::main]
async fn main() {
    let db_path = std::env::var("SUBTEXT_DB").unwrap_or_else(|_| "data/subtext.duckdb".to_string());
    let abs = std::fs::canonicalize(&db_path)
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| db_path.clone());

    // Fail fast (with a clear message) rather than serving empty pages when the
    // path is wrong — the usual mistake is launching from site/ without pointing
    // SUBTEXT_DB at the repo-root data/subtext.duckdb.
    if !std::path::Path::new(&db_path).exists() {
        eprintln!(
            "ERROR: database not found at '{db_path}' (looked in {})\n\
             Point SUBTEXT_DB at the file built by the ingest pipeline, e.g.:\n\
             \x20   SUBTEXT_DB=../data/subtext.duckdb cargo run --release",
            std::env::current_dir().map(|d| d.display().to_string()).unwrap_or_default()
        );
        std::process::exit(1);
    }

    let db = Db::new(&db_path);
    match db
        .call(|conn| {
            let n = |sql: &str| -> anyhow::Result<i64> {
                Ok(conn.query_row(sql, [], |r| r.get(0))?)
            };
            Ok((
                n("SELECT COUNT(*) FROM companies")?,
                n("SELECT COUNT(*) FROM transcripts")?,
                n("SELECT COUNT(*) FROM utterances")?,
                n("SELECT COUNT(*) FROM financials")?,
            ))
        })
        .await
    {
        Ok((c, t, u, f)) => {
            println!("Database: {abs}");
            println!("  {c} companies · {t} transcripts · {u} utterances · {f} financials");
            if c == 0 || t == 0 {
                eprintln!("WARNING: the database looks empty — did the ingest pipeline run?");
            }
        }
        Err(e) => {
            eprintln!("ERROR reading database at '{abs}': {e}");
            std::process::exit(1);
        }
    }

    let router = Router::new()
        .route("/", get(home::handler))
        .route("/company/{ticker}", get(company::handler))
        .route("/transcript/{id}", get(transcript::handler))
        .route("/search", get(search::handler))
        .route("/about", get(about::handler))
        .route("/style.css", get(style))
        .with_state(db);

    let addr = std::env::var("SUBTEXT_ADDR").unwrap_or_else(|_| "127.0.0.1:3000".to_string());
    let listener = tokio::net::TcpListener::bind(&addr)
        .await
        .unwrap_or_else(|e| panic!("failed to bind {addr}: {e}"));
    println!("Subtext listening on http://{addr}  (db: {db_path})");
    axum::serve(listener, router).await.expect("server error");
}

/// Serve the single stylesheet, embedded at compile time.
async fn style() -> impl IntoResponse {
    (
        [(header::CONTENT_TYPE, "text/css; charset=utf-8")],
        include_str!("../style/main.css"),
    )
}
