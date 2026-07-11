//! Subtext web app — Leptos 0.8 SSR served by Axum 0.8, reading a DuckDB file.

mod about;
mod app;
mod chart;
mod company;
mod db;
mod home;
mod lexicon;
mod search;
mod sectors;
mod transcript;
mod types;

use axum::{http::header, response::IntoResponse, routing::get, Router};

use db::Db;

/// Locate the DuckDB file. `SUBTEXT_DB` wins; otherwise search for
/// `data/subtext.duckdb` up the directory tree from the current dir and from
/// the crate dir, so `cargo run` works from either `site/` or the repo root
/// without any env var.
fn resolve_db_path() -> String {
    if let Ok(p) = std::env::var("SUBTEXT_DB") {
        return p;
    }
    let mut starts: Vec<std::path::PathBuf> = Vec::new();
    if let Ok(cwd) = std::env::current_dir() {
        starts.push(cwd);
    }
    starts.push(std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")));
    for start in starts {
        let mut dir = Some(start.as_path());
        while let Some(d) = dir {
            let candidate = d.join("data").join("subtext.duckdb");
            if candidate.exists() {
                return candidate.to_string_lossy().into_owned();
            }
            dir = d.parent();
        }
    }
    "data/subtext.duckdb".to_string() // fall through to the fail-fast message
}

#[tokio::main]
async fn main() {
    let db_path = resolve_db_path();
    let abs = std::fs::canonicalize(&db_path)
        .map(|p| p.display().to_string())
        .unwrap_or_else(|_| db_path.clone());

    // Fail fast (with a clear message) rather than serving empty pages when the
    // path is wrong — the usual mistake is launching from site/ without pointing
    // SUBTEXT_DB at the repo-root data/subtext.duckdb.
    if !std::path::Path::new(&db_path).exists() {
        eprintln!(
            "ERROR: could not find data/subtext.duckdb (searched up from {}).\n\
             Build it with `./ingest/run_ingest.sh`, or set SUBTEXT_DB to its path.",
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

    // Load the Loughran-McDonald word sets for inline highlighting (optional).
    let lex = lexicon::load(&db, &db_path).await;
    let (np, nn) = lex.len();
    if np + nn > 0 {
        println!("Sentiment lexicon: {np} positive, {nn} negative words");
    } else {
        println!("Sentiment lexicon: not found — transcript highlighting disabled");
    }
    lexicon::set(lex);

    let router = Router::new()
        .route("/", get(home::handler))
        .route("/company/{ticker}", get(company::handler))
        .route("/transcript/{id}", get(transcript::handler))
        .route("/sectors", get(sectors::list_handler))
        .route("/sector/{name}", get(sectors::detail_handler))
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
