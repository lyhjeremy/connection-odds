"""Draw the page figures as SVG from tables/.

Each SVG carries its own <style> whose colors read the page's CSS variables with the
light workshop palette as the fallback, so the same file is themed inline on the
site (light and dark) and still renders on GitHub as a plain image.
Outputs: figures/curves_<HUB>.svg (ten panels), figures/curves_top10.svg (the ten
together, for the README), figures/heatmap_l95.svg, figures/shortcut.svg,
figures/calibration.svg.
"""
from __future__ import annotations

import json
from pathlib import Path
from xml.sax.saxutils import escape

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
TAB, FIG = ROOT / "tables", ROOT / "figures"

STYLE = """<style>
.co-t{font-family:var(--font-body,var(--sans,"IBM Plex Sans",Helvetica,Arial,sans-serif));fill:var(--ink-2,var(--muted,#4B504D));font-size:12px}
.co-n{font-family:var(--font-mono,var(--mono,"IBM Plex Mono",Menlo,monospace))}
.co-h{fill:var(--ink,#191B1A);font-weight:600;font-size:14px}
.co-g{stroke:var(--rule,#C3C6C1);stroke-width:1;fill:none}
.co-a{stroke:var(--edge,var(--muted,#727773));stroke-width:1;fill:none}
.co-s1{stroke:var(--signal,var(--accent,#2F6243));stroke-width:2.2;fill:none}
.co-s2{stroke:var(--signal-2,var(--accent2,#7C5A26));stroke-width:2.2;fill:none}
.co-s0{stroke:var(--ink-2,var(--muted,#4B504D));stroke-width:1.4;fill:none;stroke-dasharray:4 3}
.co-band{fill:var(--signal,var(--accent,#2F6243));opacity:.16}
.co-f1{fill:var(--signal,var(--accent,#2F6243))}
.co-f2{fill:var(--signal-2,var(--accent2,#7C5A26))}
.co-f0{fill:var(--ink-2,var(--muted,#4B504D))}
.co-cell{fill:var(--signal,var(--accent,#2F6243))}
.co-na{fill:var(--panel,var(--card,#F2F3EF));stroke:var(--rule,#C3C6C1)}
.co-ct{font-size:10.5px;fill:var(--ink,#191B1A)}
.co-ci{font-size:10.5px;fill:var(--paper,#E9EAE6)}
</style>"""


def svg(w, h, body, label):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" '
            f'aria-label="{escape(label)}">{STYLE}{body}</svg>\n')


def path(xs, ys, cls):
    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    return f'<polyline class="{cls}" points="{pts}"/>'


def text(x, y, s, cls="co-t", anchor="start", extra=""):
    return f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" {extra}>{escape(str(s))}</text>'


def pct(v, d=0):
    return f"{100 * v:.{d}f}%"


def axes(x0, x1, y0, y1, xt, yt, xfmt, yfmt, sx, sy):
    out = []
    for v in yt:
        y = sy(v)
        out.append(f'<line class="co-g" x1="{x0}" x2="{x1}" y1="{y:.1f}" y2="{y:.1f}"/>')
        out.append(text(x0 - 6, y + 4, yfmt(v), "co-t co-n", "end"))
    for v in xt:
        x = sx(v)
        out.append(f'<line class="co-a" x1="{x:.1f}" x2="{x:.1f}" y1="{y0}" y2="{y0 + 4}"/>')
        out.append(text(x, y0 + 17, xfmt(v), "co-t co-n", "middle"))
    out.append(f'<line class="co-a" x1="{x0}" x2="{x1}" y1="{y0}" y2="{y0}"/>')
    return "".join(out)


def curve_panel(hub, name, c, avg, ymax, W=320, H=210):
    L, R, T, B = 40, 10, 30, 30
    sx = lambda v: L + (v - 30) / 150 * (W - L - R)
    sy = lambda v: H - B - v / ymax * (H - T - B)
    body = [axes(L, W - R, H - B, T, [30, 60, 90, 120, 150, 180], [i / 10 for i in range(int(ymax * 10 + 1e-9) + 1)],
                 lambda v: f"{v}", lambda v: pct(v), sx, sy)]
    body.append(path([sx(x + 2.5) for x in avg["layover_bin"]], [sy(v) for v in avg["rate"]], "co-s0"))
    band = [f"{sx(x + 2.5):.1f},{sy(v):.1f}" for x, v in zip(c["layover_bin"], c["hi"])] + \
           [f"{sx(x + 2.5):.1f},{sy(v):.1f}" for x, v in zip(reversed(c["layover_bin"].to_list()), reversed(c["lo"].to_list()))]
    body.append(f'<polygon class="co-band" points="{" ".join(band)}"/>')
    body.append(path([sx(x + 2.5) for x in c["layover_bin"]], [sy(v) for v in c["rate"]], "co-s1"))
    r45 = c.filter(pl.col("layover_bin") == 45)["rate"]
    body.append(text(L, 16, f"{hub} {name}", "co-t co-h"))
    if r45.len():
        body.append(text(W - R, 16, f"45 min: {pct(r45[0])}", "co-t co-n", "end"))
    lab = f"{name}: missed connections fall from {pct(c['rate'][0])} at 30 minutes to {pct(c['rate'][-1])} at 175 to 180 minutes"
    return svg(W, H, "".join(body), lab)


def curves(hubs, names):
    ch = pl.read_csv(TAB / "curves_hub.csv")
    avg = pl.read_csv(TAB / "curve_all.csv")
    top = hubs[:10]
    ymax = float(ch.filter(pl.col("hub").is_in(top))["hi"].max())
    ymax = (int(ymax * 20) + 1) / 20
    panels = {}
    for h in top:
        s = curve_panel(h, names[h], ch.filter(pl.col("hub") == h), avg, ymax)
        (FIG / f"curves_{h}.svg").write_text(s)
        panels[h] = s
    # composite for the README: two columns of five
    W, H = 320, 210
    parts = []
    for i, h in enumerate(top):
        inner = panels[h].split(STYLE, 1)[1].rsplit("</svg>", 1)[0]
        parts.append(f'<g transform="translate({(i % 2) * W},{(i // 2) * H})">{inner}</g>')
    (FIG / "curves_top10.svg").write_text(svg(2 * W, 5 * H, "".join(parts),
                                              "Missed-connection rate against scheduled layover at the ten busiest hubs"))
    return ymax


def heatmap(hubs, col="L95", fname="heatmap_l95.svg"):
    t = pl.read_csv(TAB / "layover_needed_hub_hour.csv")
    hours = sorted(t.filter(pl.col("pairs") >= 2000)["arr_hour"].unique().to_list())
    cw, rh, L, T = 30, 19, 46, 34
    W, H = L + cw * len(hours) + 8, T + rh * len(hubs) + 30
    body = [text(L, 14, "Arrival hour (local)", "co-t")]
    for j, hr in enumerate(hours):
        body.append(text(L + j * cw + cw / 2, T - 6, hr, "co-t co-n", "middle"))
    for i, h in enumerate(hubs):
        y = T + i * rh
        body.append(text(L - 6, y + rh - 5, h, "co-t co-n", "end"))
        for j, hr in enumerate(hours):
            x = L + j * cw
            r = t.filter((pl.col("hub") == h) & (pl.col("arr_hour") == hr))
            v = r[col][0] if r.height else None
            enough = r.height and r["pairs"][0] >= 2000
            if not enough:
                body.append(f'<rect class="co-na" x="{x + .5}" y="{y + .5}" width="{cw - 1}" height="{rh - 1}"/>')
                continue
            if v is None:
                body.append(f'<rect class="co-cell" x="{x + .5}" y="{y + .5}" width="{cw - 1}" height="{rh - 1}" opacity="1"/>')
                body.append(text(x + cw / 2, y + rh - 5.5, "+", "co-t co-ci co-n", "middle"))
                continue
            op = 0.12 + 0.68 * (v - 30) / 150
            light = op > 0.5
            body.append(f'<rect class="co-cell" x="{x + .5}" y="{y + .5}" width="{cw - 1}" height="{rh - 1}" opacity="{op:.2f}"/>')
            body.append(text(x + cw / 2, y + rh - 5.5, v, "co-t co-n " + ("co-ci" if light else "co-ct"), "middle"))
    body.append(text(L, H - 8, "Minutes of layover for a 95% chance; + means not reached by 180; blank means under 2,000 pairs", "co-t"))
    s = svg(W, H, "".join(body), "Layover needed for a 95% chance of making the connection, by hub and arrival hour")
    (FIG / fname).write_text(s)


def shortcut():
    sc = pl.read_csv(TAB / "shortcut_all.csv")
    W, H, L, R, T, B = 640, 330, 48, 16, 20, 40
    ymax = (int(max(sc["naive"].max(), sc["paired"].max()) * 20) + 1) / 20
    sx = lambda v: L + (v - 30) / 150 * (W - L - R)
    sy = lambda v: H - B - v / ymax * (H - T - B)
    body = [axes(L, W - R, H - B, T, [30, 45, 60, 90, 120, 150, 180], [i / 20 for i in range(int(ymax * 20) + 1) if i % 2 == 0],
                 lambda v: f"{v}", lambda v: pct(v), sx, sy)]
    x = [sx(v + 2.5) for v in sc["layover_bin"]]
    body.append(path(x, [sy(v) for v in sc["naive"]], "co-s2"))
    body.append(path(x, [sy(v) for v in sc["paired"]], "co-s1"))
    i = 6
    body.append(text(x[i] + 6, sy(sc["naive"][i]) - 8, "inbound delay only", "co-t", "start", 'style="fill:var(--signal-2,var(--accent2,#7C5A26))"'))
    body.append(text(x[i] - 4, sy(sc["paired"][i]) + 18, "both flights", "co-t", "end", 'style="fill:var(--signal,var(--accent,#2F6243))"'))
    body.append(text((W + L) / 2, H - 6, "Scheduled layover, minutes", "co-t", "middle"))
    s = svg(W, H, "".join(body), "Missed-connection rate by layover, reading both flights against reading only the inbound flight")
    (FIG / "shortcut.svg").write_text(s)


def calibration():
    c = pl.read_csv(TAB / "calibration.csv")
    W, H, L, R, T, B = 640, 360, 48, 16, 20, 40
    m = float(max(c["predicted"].max(), c["observed"].max()))
    m = (int(m * 10) + 1) / 10
    sx = lambda v: L + v / m * (W - L - R)
    sy = lambda v: H - B - v / m * (H - T - B)
    ticks = [i / 10 for i in range(int(m * 10) + 1)]
    body = [axes(L, W - R, H - B, T, ticks, ticks, pct, pct, sx, sy)]
    body.append(f'<line class="co-a" x1="{sx(0)}" y1="{sy(0)}" x2="{sx(m)}" y2="{sy(m)}" stroke-dasharray="2 3"/>')
    cls = {"lookup": ("co-s1", "co-f1"), "model": ("co-s2", "co-f2"), "naive": ("co-s0", "co-f0")}
    for est, (ln, dot) in cls.items():
        g = c.filter(pl.col("estimator") == est)
        body.append(path([sx(v) for v in g["predicted"]], [sy(v) for v in g["observed"]], ln))
        for a, b in zip(g["predicted"], g["observed"]):
            body.append(f'<circle class="{dot}" cx="{sx(a):.1f}" cy="{sy(b):.1f}" r="3"/>')
    labels = {"lookup": ("cell average", "var(--signal,var(--accent,#2F6243))"),
              "model": ("logistic model", "var(--signal-2,var(--accent2,#7C5A26))"),
              "naive": ("inbound delay only", "var(--ink-2,var(--muted,#4B504D))")}
    for i, (est, (lab, col)) in enumerate(labels.items()):
        y0 = T + 34 + i * 18
        body.append(f'<line x1="{L + 8}" x2="{L + 30}" y1="{y0 - 4}" y2="{y0 - 4}" class="{cls[est][0]}"/>')
        body.append(text(L + 36, y0, lab, "co-t", "start", f'style="fill:{col}"'))
    body.append(text((W + L) / 2, H - 6, "Predicted miss rate (decile mean)", "co-t", "middle"))
    body.append(text(L + 6, T + 10, "Observed", "co-t"))
    s = svg(W, H, "".join(body), "Calibration of three estimators on March to August 2026: predicted against observed miss rate by decile")
    (FIG / "calibration.svg").write_text(s)


def main():
    FIG.mkdir(exist_ok=True)
    tool = json.loads((ROOT / "assets" / "tool.json").read_text()) if (ROOT / "assets" / "tool.json").exists() else None
    hubs = pl.read_csv(TAB / "hubs.csv")["origin"].to_list()
    names = {h["code"]: h["name"] for h in tool["hubs"]} if tool else {h: h for h in hubs}
    curves(hubs, names)
    heatmap(hubs)
    heatmap(hubs, "L95_if_both_fly", "heatmap_l95_flown.svg")
    shortcut()
    calibration()
    print("figures written")


if __name__ == "__main__":
    main()
