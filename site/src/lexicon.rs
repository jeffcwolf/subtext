//! Loughran-McDonald positive/negative word sets, for inline highlighting of
//! sentiment words in transcript text.
//!
//! Loaded once at startup: preferring a `lm_words` table in the database (which
//! the ingest pipeline exports), and falling back to the Master Dictionary CSV
//! next to the database (or at $SUBTEXT_LM / $LM_DICT). If neither is available,
//! highlighting is silently disabled and text renders plainly.

use std::collections::HashSet;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use crate::app::escape;
use crate::db::Db;

pub struct Lexicon {
    pub positive: HashSet<String>,
    pub negative: HashSet<String>,
}

impl Lexicon {
    fn empty() -> Self {
        Self { positive: HashSet::new(), negative: HashSet::new() }
    }
    pub fn is_empty(&self) -> bool {
        self.positive.is_empty() && self.negative.is_empty()
    }
    pub fn len(&self) -> (usize, usize) {
        (self.positive.len(), self.negative.len())
    }
}

static LEXICON: OnceLock<Lexicon> = OnceLock::new();

pub fn set(lex: Lexicon) {
    let _ = LEXICON.set(lex);
}

/// Load the word sets: DB `lm_words` table first, then a Master Dictionary CSV.
pub async fn load(db: &Db, db_path: &str) -> Lexicon {
    if let Ok(lex) = db
        .call(|conn| {
            let mut pos = HashSet::new();
            let mut neg = HashSet::new();
            let mut stmt = conn.prepare("SELECT word, category FROM lm_words")?;
            let rows = stmt.query_map([], |r| {
                Ok((r.get::<_, String>(0)?, r.get::<_, String>(1)?))
            })?;
            for row in rows {
                let (w, c) = row?;
                match c.as_str() {
                    "positive" => {
                        pos.insert(w.to_uppercase());
                    }
                    "negative" => {
                        neg.insert(w.to_uppercase());
                    }
                    _ => {}
                }
            }
            Ok(Lexicon { positive: pos, negative: neg })
        })
        .await
    {
        if !lex.is_empty() {
            return lex;
        }
    }
    load_from_csv(db_path).unwrap_or_else(Lexicon::empty)
}

fn find_dictionary(db_path: &str) -> Option<PathBuf> {
    for var in ["SUBTEXT_LM", "LM_DICT"] {
        if let Ok(p) = std::env::var(var) {
            let path = PathBuf::from(p);
            if path.exists() {
                return Some(path);
            }
        }
    }
    // Search the database's own directory for a Master Dictionary CSV.
    // `parent()` of a bare filename is an empty path, not None — treat it as ".".
    let dir = match Path::new(db_path).parent() {
        Some(p) if !p.as_os_str().is_empty() => p.to_path_buf(),
        _ => PathBuf::from("."),
    };
    let entries = std::fs::read_dir(&dir).ok()?;
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().to_lowercase();
        if name.ends_with(".csv") && name.contains("master") && name.contains("dictionar") {
            return Some(entry.path());
        }
    }
    None
}

fn load_from_csv(db_path: &str) -> Option<Lexicon> {
    let path = find_dictionary(db_path)?;
    let text = std::fs::read_to_string(&path).ok()?;
    let mut lines = text.lines();
    let header = lines.next()?;
    let cols: Vec<String> = header
        .trim_start_matches('\u{feff}')
        .split(',')
        .map(|s| s.trim().to_lowercase())
        .collect();
    let idx = |name: &str| cols.iter().position(|c| c == name);
    let (wi, pi, ni) = (idx("word")?, idx("positive")?, idx("negative")?);

    let mut positive = HashSet::new();
    let mut negative = HashSet::new();
    let nonzero = |s: &str| !matches!(s.trim(), "" | "0" | "0.0");
    for line in lines {
        let f: Vec<&str> = line.split(',').collect();
        let word = match f.get(wi) {
            Some(w) if !w.trim().is_empty() => w.trim().to_uppercase(),
            _ => continue,
        };
        if f.get(pi).is_some_and(|v| nonzero(v)) {
            positive.insert(word.clone());
        }
        if f.get(ni).is_some_and(|v| nonzero(v)) {
            negative.insert(word);
        }
    }
    if positive.is_empty() && negative.is_empty() {
        return None;
    }
    Some(Lexicon { positive, negative })
}

/// Escape `text`, wrapping Loughran-McDonald positive/negative words in coloured
/// spans. Falls back to plain escaping if no lexicon was loaded.
pub fn highlight(text: &str) -> String {
    let lex = match LEXICON.get() {
        Some(l) if !l.is_empty() => l,
        _ => return escape(text),
    };
    let mut out = String::with_capacity(text.len() + 16);
    let mut word = String::new();
    let flush = |out: &mut String, word: &mut String| {
        if word.is_empty() {
            return;
        }
        let key = word.to_uppercase();
        if lex.positive.contains(&key) {
            out.push_str(r#"<span class="w-pos">"#);
            out.push_str(&escape(word));
            out.push_str("</span>");
        } else if lex.negative.contains(&key) {
            out.push_str(r#"<span class="w-neg">"#);
            out.push_str(&escape(word));
            out.push_str("</span>");
        } else {
            out.push_str(&escape(word));
        }
        word.clear();
    };
    for ch in text.chars() {
        if ch.is_alphabetic() || ch == '\'' {
            word.push(ch);
        } else {
            flush(&mut out, &mut word);
            match ch {
                '&' => out.push_str("&amp;"),
                '<' => out.push_str("&lt;"),
                '>' => out.push_str("&gt;"),
                '"' => out.push_str("&quot;"),
                _ => out.push(ch),
            }
        }
    }
    flush(&mut out, &mut word);
    out
}
