//! Pure-SVG line charts — no JS, server-rendered. Values are net-sentiment
//! (roughly ±0.02); we plot them raw and label the axis ×1000 for legibility.

use crate::app::escape;

/// One labelled series. `class` is a CSS colour class (e.g. "s-ceo").
pub struct Series {
    pub label: String,
    pub class: String,
    pub values: Vec<Option<f64>>,
}

const W: f64 = 680.0;
const H: f64 = 260.0;
const ML: f64 = 46.0;
const MR: f64 = 12.0;
const MT: f64 = 12.0;
const MB: f64 = 34.0;

/// Render a multi-series line chart to an SVG string. `x_labels` has one entry
/// per data point (per call); each series' `values` must be the same length.
pub fn line_chart(x_labels: &[String], series: &[Series]) -> String {
    let n = x_labels.len();
    if n == 0 {
        return r#"<p class="muted">No sentiment data for this company yet.</p>"#.to_string();
    }
    let iw = W - ML - MR;
    let ih = H - MT - MB;

    let mut maxabs = 0.0f64;
    for s in series {
        for v in s.values.iter().flatten() {
            maxabs = maxabs.max(v.abs());
        }
    }
    if maxabs <= 0.0 {
        maxabs = 0.02;
    }
    let ymax = maxabs * 1.15;

    let x_at = |i: usize| -> f64 {
        if n == 1 {
            ML + iw / 2.0
        } else {
            ML + iw * (i as f64) / ((n - 1) as f64)
        }
    };
    let y_at = |v: f64| -> f64 { MT + ih / 2.0 - (v / ymax) * (ih / 2.0) };

    let mut svg = String::new();
    svg.push_str(&format!(
        r#"<svg class="chart" viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet">"#
    ));

    // Horizontal gridlines + y tick labels.
    for frac in [-1.0f64, -0.5, 0.0, 0.5, 1.0] {
        let yv = ymax * frac;
        let y = y_at(yv);
        let cls = if frac == 0.0 { "zero" } else { "grid" };
        svg.push_str(&format!(
            r#"<line class="{cls}" x1="{ML:.1}" y1="{y:.1}" x2="{x2:.1}" y2="{y:.1}"/>"#,
            x2 = ML + iw
        ));
        svg.push_str(&format!(
            r#"<text class="tick" x="{tx:.1}" y="{ty:.1}" text-anchor="end">{val:+.0}</text>"#,
            tx = ML - 6.0,
            ty = y + 3.0,
            val = yv * 1000.0
        ));
    }

    // X tick labels — a subset so they don't collide.
    let step = (((n as f64) / 8.0).ceil() as usize).max(1);
    let mut i = 0;
    while i < n {
        svg.push_str(&format!(
            r#"<text class="tick" x="{x:.1}" y="{y:.1}" text-anchor="middle">{lbl}</text>"#,
            x = x_at(i),
            y = H - 12.0,
            lbl = escape(&x_labels[i])
        ));
        i += step;
    }

    // Series: one path (broken at gaps) + dots with hover titles.
    for s in series {
        let mut d = String::new();
        let mut pen_down = false;
        for (idx, v) in s.values.iter().enumerate() {
            match v {
                Some(val) => {
                    let (x, y) = (x_at(idx), y_at(*val));
                    if pen_down {
                        d.push_str(&format!(" L{x:.1},{y:.1}"));
                    } else {
                        d.push_str(&format!("M{x:.1},{y:.1}"));
                        pen_down = true;
                    }
                }
                None => pen_down = false,
            }
        }
        if !d.is_empty() {
            svg.push_str(&format!(
                r#"<path class="series {cls}" d="{d}"/>"#,
                cls = escape(&s.class)
            ));
        }
        for (idx, v) in s.values.iter().enumerate() {
            if let Some(val) = v {
                svg.push_str(&format!(
                    r#"<circle class="dot {cls}" cx="{x:.1}" cy="{y:.1}" r="2.5"><title>{lbl} · {name}: {sv:+.1}</title></circle>"#,
                    cls = escape(&s.class),
                    x = x_at(idx),
                    y = y_at(*val),
                    lbl = escape(&x_labels[idx]),
                    name = escape(&s.label),
                    sv = val * 1000.0
                ));
            }
        }
    }

    svg.push_str("</svg>");
    svg
}

/// A single-series line chart for a positive metric (forward EPS, P/E …),
/// auto-scaled to the data's own [min, max] rather than centred on zero.
/// `prefix` is prepended to axis labels (e.g. "$").
pub fn metric_chart(x_labels: &[String], values: &[Option<f64>], class: &str, prefix: &str) -> String {
    let n = x_labels.len();
    let present: Vec<f64> = values.iter().flatten().copied().collect();
    if n == 0 || present.is_empty() {
        return r#"<p class="muted">No data.</p>"#.to_string();
    }
    let iw = W - ML - MR;
    let ih = H - MT - MB;
    let (mut lo, mut hi) = (
        present.iter().cloned().fold(f64::INFINITY, f64::min),
        present.iter().cloned().fold(f64::NEG_INFINITY, f64::max),
    );
    if (hi - lo).abs() < 1e-9 {
        lo -= 1.0;
        hi += 1.0;
    }
    let pad = (hi - lo) * 0.08;
    let (lo, hi) = (lo - pad, hi + pad);

    let x_at = |i: usize| -> f64 {
        if n == 1 { ML + iw / 2.0 } else { ML + iw * (i as f64) / ((n - 1) as f64) }
    };
    let y_at = |v: f64| -> f64 { MT + ih - (v - lo) / (hi - lo) * ih };

    let mut svg = format!(
        r#"<svg class="chart" viewBox="0 0 {W} {H}" role="img" preserveAspectRatio="xMidYMid meet">"#
    );
    for frac in [0.0f64, 0.5, 1.0] {
        let v = lo + (hi - lo) * frac;
        let y = y_at(v);
        svg.push_str(&format!(
            r#"<line class="grid" x1="{ML:.1}" y1="{y:.1}" x2="{x2:.1}" y2="{y:.1}"/>"#,
            x2 = ML + iw
        ));
        svg.push_str(&format!(
            r#"<text class="tick" x="{tx:.1}" y="{ty:.1}" text-anchor="end">{p}{val:.2}</text>"#,
            tx = ML - 6.0, ty = y + 3.0, p = escape(prefix), val = v
        ));
    }
    let step = (((n as f64) / 8.0).ceil() as usize).max(1);
    let mut i = 0;
    while i < n {
        svg.push_str(&format!(
            r#"<text class="tick" x="{x:.1}" y="{y:.1}" text-anchor="middle">{lbl}</text>"#,
            x = x_at(i), y = H - 12.0, lbl = escape(&x_labels[i])
        ));
        i += step;
    }
    let mut d = String::new();
    let mut pen = false;
    for (idx, v) in values.iter().enumerate() {
        if let Some(val) = v {
            let (x, y) = (x_at(idx), y_at(*val));
            d.push_str(&format!("{}{x:.1},{y:.1}", if pen { " L" } else { "M" }));
            pen = true;
        } else {
            pen = false;
        }
    }
    svg.push_str(&format!(r#"<path class="series {cls}" d="{d}"/>"#, cls = escape(class)));
    for (idx, v) in values.iter().enumerate() {
        if let Some(val) = v {
            svg.push_str(&format!(
                r#"<circle class="dot {cls}" cx="{x:.1}" cy="{y:.1}" r="2.5"><title>{lbl}: {p}{val:.2}</title></circle>"#,
                cls = escape(class), x = x_at(idx), y = y_at(*val),
                lbl = escape(&x_labels[idx]), p = escape(prefix), val = val
            ));
        }
    }
    svg.push_str("</svg>");
    svg
}

/// A small HTML legend for a set of series.
pub fn legend(series: &[Series]) -> String {
    let mut out = String::from(r#"<div class="chart-legend">"#);
    for s in series {
        out.push_str(&format!(
            r#"<span><i class="swatch {cls}"></i>{label}</span>"#,
            cls = escape(&s.class),
            label = escape(&s.label)
        ));
    }
    out.push_str("</div>");
    out
}
