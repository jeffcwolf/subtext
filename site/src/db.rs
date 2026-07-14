//! Read-only DuckDB access, wrapped in `spawn_blocking`.
//!
//! `duckdb::Connection` is synchronous and not `Send` across await points, so
//! every query runs on a blocking thread with its own short-lived read-only
//! connection (DuckDB allows many concurrent readers of one file).

use std::path::{Path, PathBuf};

use duckdb::{AccessMode, Config, Connection};

#[derive(Clone)]
pub struct Db {
    path: PathBuf,
}

/// Open a fresh read-only connection and apply memory guardrails.
///
/// The app runs on a small, shared host (~2 GB RAM). Left unbounded, a heavy
/// query — e.g. BM25 over millions of utterances — allocates until the box is
/// out of memory and swap-thrashes, freezing every container on the host. Two
/// settings prevent that:
///   * `memory_limit` caps how much a query may hold before it spills to disk.
///   * `temp_directory` points that spill at a writable path. The DB itself is
///     on a read-only mount, so DuckDB's default temp location (beside the file)
///     is unwritable — without this, a query that needs to spill can't, and
///     falls back to exhausting RAM.
///   * `threads` matches the 2-vCPU box so we don't oversubscribe.
///
/// Best-effort: a settings hiccup must never break page loads, and the
/// container's cgroup memory limit (set in compose) is the hard backstop
/// regardless. Applied per connection because each query opens its own.
fn open_tuned(path: &Path) -> anyhow::Result<Connection> {
    let config = Config::default().access_mode(AccessMode::ReadOnly)?;
    let conn = Connection::open_with_flags(path, config)?;
    if let Err(e) =
        conn.execute_batch("SET memory_limit='512MB'; SET threads=2; SET temp_directory='/tmp';")
    {
        eprintln!("warning: could not apply DuckDB memory guardrails: {e}");
    }
    Ok(conn)
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
            let conn = open_tuned(&path)?;
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
            let conn = open_tuned(&path)?;
            conn.execute_batch("LOAD fts;")?;
            f(&conn)
        })
        .await?
    }
}
