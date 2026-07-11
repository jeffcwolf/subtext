//! `/company/{ticker}` — the company dashboard: sentiment timeline, CEO-vs-CFO
//! and prepared-vs-Q&A panels, and recent transcripts.

use axum::{
    extract::{Path, State},
    response::{Html, IntoResponse, Response},
};
use duckdb::params;
use leptos::prelude::*;

use crate::app;
use crate::chart::{self, Series};
use crate::db::Db;
use crate::types::{CallPoint, CompanyHeader};

pub async fn handler(State(db): State<Db>, Path(ticker): Path<String>) -> Response {
    let ticker = ticker.to_uppercase();
    match load(&db, ticker.clone()).await {
        Ok(Some((header, calls))) => {
            let title = header.name.clone();
            Html(app::shell(&title, &render(header, calls))).into_response()
        }
        Ok(None) => app::not_found(&format!("No company with ticker “{ticker}”.")),
        Err(e) => app::error_response(e),
    }
}

/// One expression that computes net sentiment for a filtered subset of a call.
fn net_expr(filter: &str) -> String {
    format!(
        "(SUM(CASE WHEN {f} THEN s.positive_count ELSE 0 END) \
          - SUM(CASE WHEN {f} THEN s.negative_count ELSE 0 END))::DOUBLE \
         / NULLIF(SUM(CASE WHEN {f} THEN s.total_words ELSE 0 END), 0)",
        f = filter
    )
}

async fn load(db: &Db, ticker: String) -> anyhow::Result<Option<(CompanyHeader, Vec<CallPoint>)>> {
    db.call(move |conn| {
        // Header (LEFT JOIN so a known ticker with no calls still returns a row).
        let mut hs = conn.prepare(
            "SELECT c.name, c.sector, COUNT(t.transcript_id),
                    CAST(MIN(t.call_date) AS VARCHAR), CAST(MAX(t.call_date) AS VARCHAR)
             FROM companies c LEFT JOIN transcripts t USING (ticker)
             WHERE c.ticker = ? GROUP BY c.name, c.sector",
        )?;
        let mut hrows = hs.query_map(params![ticker], |r| {
            Ok(CompanyHeader {
                ticker: ticker.clone(),
                name: r.get::<_, Option<String>>(0)?.unwrap_or_default(),
                sector: r.get(1)?,
                transcripts: r.get(2)?,
                first_date: r.get(3)?,
                last_date: r.get(4)?,
            })
        })?;
        let header = match hrows.next() {
            Some(h) => h?,
            None => return Ok(None),
        };
        drop(hrows);
        drop(hs);

        let sql = format!(
            "SELECT t.transcript_id, t.fiscal_year, t.fiscal_quarter,
                    CAST(t.call_date AS VARCHAR),
                    {overall} AS overall, {ceo} AS ceo, {cfo} AS cfo,
                    {prep} AS prepared, {qa} AS qa,
                    MAX(f.eps_fwd) AS eps_fwd, MAX(f.pe_fwd) AS pe_fwd
             FROM transcripts t
             JOIN utterances u USING (transcript_id)
             JOIN sentiment_facts s USING (utterance_id)
             LEFT JOIN financials f USING (transcript_id)
             WHERE t.ticker = ?
             GROUP BY t.transcript_id, t.fiscal_year, t.fiscal_quarter, t.call_date
             ORDER BY t.call_date NULLS LAST, t.fiscal_year, t.fiscal_quarter",
            overall = net_expr("TRUE"),
            ceo = net_expr("u.speaker_role = 'CEO'"),
            cfo = net_expr("u.speaker_role = 'CFO'"),
            prep = net_expr("u.section = 'prepared_remarks'"),
            qa = net_expr("u.section = 'qa_response'"),
        );
        let mut stmt = conn.prepare(&sql)?;
        let rows = stmt.query_map(params![ticker], |r| {
            let year: Option<i32> = r.get(1)?;
            let quarter: Option<String> = r.get(2)?;
            let label = match (year, quarter.as_deref()) {
                (Some(y), Some(q)) => format!("{y} {q}"),
                (Some(y), None) => y.to_string(),
                _ => "—".to_string(),
            };
            Ok(CallPoint {
                transcript_id: r.get(0)?,
                call_date: r.get(3)?,
                label,
                overall: r.get(4)?,
                ceo: r.get(5)?,
                cfo: r.get(6)?,
                prepared: r.get(7)?,
                qa: r.get(8)?,
                eps_fwd: r.get(9)?,
                pe_fwd: r.get(10)?,
            })
        })?;
        let calls = rows.collect::<Result<Vec<_>, _>>()?;
        Ok(Some((header, calls)))
    })
    .await
}

fn render(header: CompanyHeader, calls: Vec<CallPoint>) -> String {
    let labels: Vec<String> = calls.iter().map(|c| c.label.clone()).collect();
    let overall = Series {
        label: "Overall".into(),
        class: "s-overall".into(),
        values: calls.iter().map(|c| c.overall).collect(),
    };
    let ceo_cfo = [
        Series {
            label: "CEO".into(),
            class: "s-ceo".into(),
            values: calls.iter().map(|c| c.ceo).collect(),
        },
        Series {
            label: "CFO".into(),
            class: "s-cfo".into(),
            values: calls.iter().map(|c| c.cfo).collect(),
        },
    ];
    let sections = [
        Series {
            label: "Prepared remarks".into(),
            class: "s-prepared".into(),
            values: calls.iter().map(|c| c.prepared).collect(),
        },
        Series {
            label: "Q&A responses".into(),
            class: "s-qa".into(),
            values: calls.iter().map(|c| c.qa).collect(),
        },
    ];

    let timeline = chart::line_chart(&labels, std::slice::from_ref(&overall));
    let timeline_legend = chart::legend(std::slice::from_ref(&overall));
    let cc_svg = chart::line_chart(&labels, &ceo_cfo);
    let cc_legend = chart::legend(&ceo_cfo);
    let sec_svg = chart::line_chart(&labels, &sections);
    let sec_legend = chart::legend(&sections);

    // Fundamentals (glopardo) — only shown when we matched financials.
    let eps_vals: Vec<Option<f64>> = calls.iter().map(|c| c.eps_fwd).collect();
    let pe_vals: Vec<Option<f64>> = calls.iter().map(|c| c.pe_fwd).collect();
    let has_fin = eps_vals.iter().any(Option::is_some);
    let fundamentals_html = if has_fin {
        render_fundamentals(&labels, &eps_vals, &pe_vals, &compute_divergences(&calls))
    } else {
        String::new()
    };

    let date_range = match (&header.first_date, &header.last_date) {
        (Some(a), Some(b)) => format!("{a} – {b}"),
        _ => "—".to_string(),
    };
    let sector_html = match &header.sector {
        Some(s) if !s.is_empty() => format!(
            r#"<a href="/sector/{}">{}</a>"#,
            app::urlencode(s),
            app::escape(s)
        ),
        _ => "—".to_string(),
    };
    let recent: Vec<CallPoint> = calls.iter().rev().take(8).cloned().collect();
    let charted = calls.len();

    view! {
        <section class="card">
            <h1>{header.name.clone()}" "<span class="ticker mono">{header.ticker.clone()}</span></h1>
            <div class="stat-row">
                <div class="stat"><span class="k">"Sector"</span><span class="v" inner_html=sector_html></span></div>
                <div class="stat"><span class="k">"Transcripts"</span><span class="v">{header.transcripts}</span></div>
                <div class="stat"><span class="k">"Date range"</span><span class="v">{date_range}</span></div>
                <div class="stat"><span class="k">"Calls charted"</span><span class="v">{charted}</span></div>
            </div>
        </section>

        <section class="card">
            <h2>"Sentiment timeline"</h2>
            <p class="muted">"Net Loughran-McDonald sentiment per call (×1000), earliest → latest."</p>
            <div class="chartwrap" inner_html=timeline></div>
            <div inner_html=timeline_legend></div>
        </section>

        <div class="panels">
            <section class="card">
                <h2>"CEO vs CFO"</h2>
                <p class="muted">"Average sentiment of each executive's remarks per call. Divergence is a signal."</p>
                <div class="chartwrap" inner_html=cc_svg></div>
                <div inner_html=cc_legend></div>
            </section>
            <section class="card">
                <h2>"Prepared remarks vs Q&A"</h2>
                <p class="muted">"Scripted tone vs unscripted answers. The gap is information."</p>
                <div class="chartwrap" inner_html=sec_svg></div>
                <div inner_html=sec_legend></div>
            </section>
        </div>

        <div inner_html=fundamentals_html></div>

        <section class="card">
            <h2>"Recent transcripts"</h2>
            <table class="tbl">
                <thead>
                    <tr><th>"Call"</th><th>"Date"</th><th class="num">"Sentiment ×1000"</th>
                        <th class="num">"Fwd EPS"</th><th class="num">"Fwd P/E"</th><th></th></tr>
                </thead>
                <tbody>
                {recent.into_iter().map(|c| {
                    let href = format!("/transcript/{}", c.transcript_id);
                    let pill = format!("pill {}", app::sentiment_class(c.overall));
                    view! {
                        <tr>
                            <td>{c.label.clone()}</td>
                            <td class="mono">{c.call_date.clone().unwrap_or_else(|| "—".to_string())}</td>
                            <td class="num"><span class=pill>{app::fmt_sentiment(c.overall)}</span></td>
                            <td class="num">{app::fmt_money(c.eps_fwd)}</td>
                            <td class="num">{app::fmt_ratio(c.pe_fwd)}</td>
                            <td><a href=href>"View →"</a></td>
                        </tr>
                    }
                }).collect_view()}
                </tbody>
            </table>
        </section>
    }
    .to_html()
}

/// A quarter where management tone moved opposite to the forward EPS estimate.
struct Divergence {
    label: String,
    ds: f64, // change in overall sentiment vs prior call
    de: f64, // change in forward EPS estimate vs prior call
    note: &'static str,
}

impl Divergence {
    fn to_html(&self) -> String {
        let (sa, sc) = if self.ds > 0.0 {
            ("↑", "up")
        } else {
            ("↓", "down")
        };
        let (ea, ec) = if self.de > 0.0 {
            ("↑", "up")
        } else {
            ("↓", "down")
        };
        format!(
            r#"<li><span class="when">{lbl}</span>
<span class="arrow">tone <span class="{sc}">{sa} {sv:+.1}</span></span>
<span class="arrow">fwd EPS <span class="{ec}">{ea} {ev:+.2}</span></span>
<span class="note">{note}</span></li>"#,
            lbl = app::escape(&self.label),
            sc = sc,
            sa = sa,
            sv = self.ds * 1000.0,
            ec = ec,
            ea = ea,
            ev = self.de,
            note = self.note,
        )
    }
}

/// Flag calls where overall sentiment and the forward EPS estimate moved in
/// opposite directions quarter-over-quarter (both beyond a small threshold).
fn compute_divergences(calls: &[CallPoint]) -> Vec<Divergence> {
    let mut out = Vec::new();
    for w in calls.windows(2) {
        let (a, b) = (&w[0], &w[1]);
        if let (Some(s0), Some(s1), Some(e0), Some(e1)) =
            (a.overall, b.overall, a.eps_fwd, b.eps_fwd)
        {
            if e0.abs() < 1e-9 {
                continue;
            }
            let ds = s1 - s0;
            let de = e1 - e0;
            let rel_de = de / e0.abs();
            if ds.abs() >= 0.002 && rel_de.abs() >= 0.01 && (ds > 0.0) != (de > 0.0) {
                let note = if ds > 0.0 {
                    "Tone rose while the forward EPS estimate was cut."
                } else {
                    "Tone cooled even as the forward EPS estimate rose."
                };
                out.push(Divergence {
                    label: b.label.clone(),
                    ds,
                    de,
                    note,
                });
            }
        }
    }
    out
}

fn render_fundamentals(
    labels: &[String],
    eps: &[Option<f64>],
    pe: &[Option<f64>],
    divergences: &[Divergence],
) -> String {
    let mut h = String::from(
        r#"<section class="card"><h2>Tone vs forward expectations</h2>
<p class="muted">Management tone next to Wall Street's forward-looking numbers (glopardo): the 12-month forward EPS estimate and the forward P/E per call.</p>
<div class="subgrid">"#,
    );
    h.push_str(&format!(
        r#"<div><h3 class="muted">Forward EPS estimate</h3>{}</div>"#,
        chart::metric_chart(labels, eps, "s-eps", "$")
    ));
    h.push_str(&format!(
        r#"<div><h3 class="muted">Forward P/E</h3>{}</div>"#,
        chart::metric_chart(labels, pe, "s-pe", "")
    ));
    h.push_str("</div>");
    if divergences.is_empty() {
        h.push_str(r#"<p class="muted">No notable tone-vs-estimate divergences detected.</p>"#);
    } else {
        h.push_str(
            r#"<h3>Divergence watch <span class="flag">⚑</span></h3>
<p class="muted">Quarters where tone and the forward EPS estimate moved opposite ways.</p>
<ul class="divergence">"#,
        );
        for d in divergences {
            h.push_str(&d.to_html());
        }
        h.push_str("</ul>");
    }
    h.push_str("</section>");
    h
}
