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
    let db = Db::new(&db_path);

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
