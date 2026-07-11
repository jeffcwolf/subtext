//! Read-only DuckDB access, wrapped in `spawn_blocking`.
//!
//! `duckdb::Connection` is synchronous and not `Send` across await points, so
//! every query runs on a blocking thread with its own short-lived read-only
//! connection (DuckDB allows many concurrent readers of one file).

use std::path::PathBuf;

use duckdb::{AccessMode, Config, Connection};

#[derive(Clone)]
pub struct Db {
    path: PathBuf,
}

impl Db {
    pub fn new(path: impl Into<PathBuf>) -> Self {
        Self { path: path.into() }
    }

    /// Run `f` against a fresh read-only connection on a blocking thread.
    pub async fn call<T, F>(&self, f: F) -> anyhow::Result<T>
    where
        F: FnOnce(&Connection) -> anyhow::Result<T> + Send + 'static,
        T: Send + 'static,
    {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || {
            let config = Config::default().access_mode(AccessMode::ReadOnly)?;
            let conn = Connection::open_with_flags(&path, config)?;
            f(&conn)
        })
        .await?
    }

    /// Like [`Db::call`], but loads the FTS extension first (needed for BM25 search).
    /// Returns an error the caller can degrade on if the extension is missing.
    pub async fn call_fts<T, F>(&self, f: F) -> anyhow::Result<T>
    where
        F: FnOnce(&Connection) -> anyhow::Result<T> + Send + 'static,
        T: Send + 'static,
    {
        let path = self.path.clone();
        tokio::task::spawn_blocking(move || {
            let config = Config::default().access_mode(AccessMode::ReadOnly)?;
            let conn = Connection::open_with_flags(&path, config)?;
            conn.execute_batch("LOAD fts;")?;
            f(&conn)
        })
        .await?
    }
}
