"""Server-rendered SVG charts for the visualisation layer.

Pure functions that return inline-SVG strings, themed with the app's CSS
variables (CGC palette) and the four risk-band colours. No client library, no
build step — consistent with the in-app guide diagrams and the case report,
printable, and FI-scoped by whatever data the caller passes in.

Risk-band colours come from scoring.BAND_META so charts always match the rest
of the app.
"""
from __future__ import annotations

import math
from typing import Dict, List, Sequence, Tuple

from app.core.scoring import BAND_META, BANDS

# Bottom-to-top stacking order (worst on top so deterioration is visible).
STACK_ORDER = ["Low Risk", "Moderate Risk", "High Risk", "Very High Risk"]


def rm_short(v: float) -> str:
    v = float(v or 0)
    if v >= 1e6:
        return f"RM {v / 1e6:.1f}m"
    if v >= 1e3:
        return f"RM {v / 1e3:.0f}k"
    return f"RM {v:.0f}"


def _c(band: str) -> str:
    return BAND_META[band]["color"]


def donut(counts: Dict[str, int], size: int = 168, stroke: int = 26) -> str:
    """Risk-band distribution as a donut; centre shows the total."""
    total = sum(counts.get(b, 0) for b in BANDS)
    r = (size - stroke) / 2 - 2
    c = size / 2
    circ = 2 * math.pi * r
    parts = [f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" '
             f'stroke="var(--line)" stroke-width="{stroke}"/>']
    acc = 0.0
    for band in BANDS:
        n = counts.get(band, 0)
        frac = (n / total) if total else 0.0
        dash = frac * circ
        if dash > 0:
            parts.append(
                f'<circle cx="{c}" cy="{c}" r="{r:.1f}" fill="none" stroke="{_c(band)}" '
                f'stroke-width="{stroke}" stroke-dasharray="{dash:.2f} {circ - dash:.2f}" '
                f'stroke-dashoffset="{-acc:.2f}" transform="rotate(-90 {c} {c})"/>')
        acc += dash
    centre = (f'<text x="{c}" y="{c - 1}" text-anchor="middle" font-size="24" '
              f'font-weight="700" fill="var(--ink)">{total}</text>'
              f'<text x="{c}" y="{c + 17}" text-anchor="middle" font-size="11" '
              f'fill="var(--muted)">accounts</text>')
    return (f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
            f'role="img" aria-label="Risk band distribution donut">{"".join(parts)}{centre}</svg>')


def hbars(items: Sequence[Tuple[str, float, str]], width: int = 330,
          value_fmt=rm_short, label_w: int = 92) -> str:
    """Horizontal bars: items = [(label, value, colour)]."""
    maxv = max((v for _, v, _ in items), default=1.0) or 1.0
    bar_max = width - label_w - 70
    row_h, gap, pad = 20, 12, 4
    out, y = [], pad
    for label, value, color in items:
        w = (value / maxv) * bar_max if maxv else 0
        out.append(f'<text x="0" y="{y + 14}" font-size="12" fill="var(--ink)">{label}</text>')
        out.append(f'<rect x="{label_w}" y="{y + 1}" width="{max(0, w):.1f}" height="{row_h - 5}" '
                   f'rx="3" fill="{color}"/>')
        out.append(f'<text x="{label_w + max(0, w) + 6:.1f}" y="{y + 14}" font-size="11.5" '
                   f'fill="var(--muted)">{value_fmt(value)}</text>')
        y += row_h + gap
    h = y + pad
    return (f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" '
            f'aria-label="Exposure at risk by band">{"".join(out)}</svg>')


def stacked_area(trend: List[Dict], width: int = 540, height: int = 190) -> str:
    """Band populations over runs as a stacked area — deterioration as a shape."""
    if len(trend) < 2:
        return ""
    pl, pr, pt, pb = 42, 12, 12, 24
    pw, ph = width - pl - pr, height - pt - pb
    n = len(trend)
    xs = [pl + (i / (n - 1)) * pw for i in range(n)]
    totals = [sum(t.get(b, 0) for b in BANDS) for t in trend]
    maxt = max(totals) or 1

    def yv(v: float) -> float:
        return pt + ph - (v / maxt) * ph

    base = [0.0] * n
    layers = []
    for band in STACK_ORDER:
        top = [base[i] + trend[i].get(band, 0) for i in range(n)]
        pts_top = " ".join(f"{xs[i]:.1f},{yv(top[i]):.1f}" for i in range(n))
        pts_base = " ".join(f"{xs[i]:.1f},{yv(base[i]):.1f}" for i in range(n - 1, -1, -1))
        layers.append(f'<polygon points="{pts_top} {pts_base}" fill="{_c(band)}" opacity="0.85"/>')
        base = top
    xlabels = []
    step = max(1, n // 6)
    for i, t in enumerate(trend):
        if i % step == 0 or i == n - 1:
            xlabels.append(f'<text x="{xs[i]:.1f}" y="{height - 6}" font-size="10" '
                           f'fill="var(--muted)" text-anchor="middle">{str(t.get("created_at",""))[5:]}</text>')
    yax = (f'<text x="{pl - 6}" y="{yv(maxt) + 4:.1f}" font-size="10" fill="var(--muted)" '
           f'text-anchor="end">{maxt}</text>'
           f'<text x="{pl - 6}" y="{yv(0):.1f}" font-size="10" fill="var(--muted)" text-anchor="end">0</text>'
           f'<line x1="{pl}" y1="{pt}" x2="{pl}" y2="{pt + ph}" stroke="var(--line)"/>')
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
            f'aria-label="Risk band trend over runs">{"".join(layers)}{"".join(xlabels)}{yax}</svg>')


def scatter(points: Sequence[Tuple[float, float, float, str]], width: int = 560,
            height: int = 320, cap: int = 800) -> str:
    """Probability x exposure risk map. points = (prob, ead, leverage, band).

    x = probability of MIA 3, y = EAD (log), bubble size = leverage (outstanding
    ratio), colour = band. The top-right (likely AND high-impact) quadrant is
    shaded — the accounts to act on first.
    """
    if not points:
        return ""
    if len(points) > cap:
        stepf = len(points) / cap
        points = [points[int(i * stepf)] for i in range(cap)]
    pl, pr, pt, pb = 54, 16, 18, 30
    x0, x1, y0, y1 = pl, width - pr, pt, height - pb
    lo, hi = 5e3, 3e6
    loglo, loghi = math.log10(lo), math.log10(hi)

    def xv(p: float) -> float:
        return x0 + max(0.0, min(1.0, p)) * (x1 - x0)

    def yv(ead: float) -> float:
        e = max(lo, min(hi, ead or lo))
        return y1 - (math.log10(e) - loglo) / (loghi - loglo) * (y1 - y0)

    def rad(lev: float) -> float:
        return 3 + min(1.4, max(0.0, lev or 0)) / 1.4 * 5

    qx, qy = xv(0.5), yv(2e5)
    chrome = [
        f'<rect x="{qx:.1f}" y="{y0}" width="{x1 - qx:.1f}" height="{qy - y0:.1f}" '
        f'fill="{_c("Very High Risk")}" opacity="0.06"/>',
        f'<text x="{x1 - 4}" y="{y0 + 14}" text-anchor="end" font-size="10.5" '
        f'fill="var(--muted)">act first — likely &amp; high impact</text>',
        f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="var(--line)"/>',
        f'<line x1="{x0}" y1="{y0}" x2="{x0}" y2="{y1}" stroke="var(--line)"/>',
        f'<line x1="{qx:.1f}" y1="{y0}" x2="{qx:.1f}" y2="{y1}" stroke="var(--muted)" '
        f'stroke-dasharray="3 3" opacity="0.45"/>',
        f'<line x1="{x0}" y1="{qy:.1f}" x2="{x1}" y2="{qy:.1f}" stroke="var(--muted)" '
        f'stroke-dasharray="3 3" opacity="0.45"/>',
    ]
    xt = [(0, "0%"), (0.25, "25%"), (0.5, "50%"), (0.75, "75%"), (1, "100%")]
    for p, lab in xt:
        chrome.append(f'<text x="{xv(p):.1f}" y="{y1 + 14}" font-size="10" fill="var(--muted)" '
                      f'text-anchor="middle">{lab}</text>')
    chrome.append(f'<text x="{(x0 + x1) / 2:.0f}" y="{height - 2}" font-size="10.5" '
                  f'fill="var(--muted)" text-anchor="middle">probability of MIA 3 &#8594;</text>')
    yt = [(5e3, "5k"), (5e4, "50k"), (2e5, "200k"), (5e5, "500k"), (3e6, "3m")]
    for e, lab in yt:
        chrome.append(f'<text x="{x0 - 6}" y="{yv(e) + 3:.1f}" font-size="10" fill="var(--muted)" '
                      f'text-anchor="end">{lab}</text>')
    chrome.append(f'<text x="14" y="{(y0 + y1) / 2:.0f}" font-size="10.5" fill="var(--muted)" '
                  f'text-anchor="middle" transform="rotate(-90 14 {(y0 + y1) / 2:.0f})">EAD (RM) &#8594;</text>')
    dots = "".join(
        f'<circle cx="{xv(p):.1f}" cy="{yv(e):.1f}" r="{rad(lev):.1f}" fill="{_c(b)}" opacity="0.78"/>'
        for (p, e, lev, b) in points)
    return (f'<svg viewBox="0 0 {width} {height}" width="100%" role="img" '
            f'aria-label="Probability versus exposure risk map">{"".join(chrome)}{dots}</svg>')
