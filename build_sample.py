#!/usr/bin/env python3
"""Render the client-facing HTML sample from outputs/summary.json.

Every number in the page is read from summary.json (produced by main.py);
nothing is typed by hand.  Usage:
  python3 -I build_sample.py --summary outputs/summary.json --out sample.html --retrieved 2026-10-20
"""
from __future__ import annotations

import argparse
import html
import json
from string import Template
from pathlib import Path

SELECTED = [
    "Homicide: Murder", "Assault: Domestic violence related assault", "Assault: Non-domestic violence related assault",
    "Sexual offences: Sexual assault", "Intimidation, stalking and harassment", "Coercive Control",
    "Theft: Break and enter dwelling", "Theft: Motor vehicle theft", "Theft: Steal from retail store",
    "Theft: Fraud", "Malicious damage to property", "Drug offences: Possession and/or use of cannabis",
]
CHARTS = ["Assault: Domestic violence related assault", "Sexual offences: Sexual assault",
          "Theft: Break and enter dwelling", "Theft: Steal from retail store"]
SRC = {
    "bocsar_data": "https://bocsar.nsw.gov.au/content/dcj/bocsar/bocsar-home/statistics-dashboards/open-datasets/criminal-offences-data.html",
    "bocsar_file": "https://bocsar.nsw.gov.au/content/dam/dcj/bocsar/documents/open-datasets/Incident_by_NSW.xlsx",
    "bocsar_using": "https://bocsar.nsw.gov.au/statistics-dashboards/crime-and-policing/using_crime_statistics.html",
    "abs_api": "https://data.api.abs.gov.au/rest/data/ABS,ERP_Q,1.0.0/1.3.TOT.1.Q?startPeriod=1994-Q1",
    "abs_erp": "https://www.abs.gov.au/statistics/people/population/national-state-and-territory-population",
    "abs_rc": "https://www.abs.gov.au/statistics/people/crime-and-justice/recorded-crime-victims",
    "anzsoc": "https://www.abs.gov.au/statistics/classifications/australian-and-new-zealand-standard-offence-classification-anzsoc",
}
e = html.escape


def fmt(x, d=0):
    return f"{x:,.{d}f}"


def pct(x, d=1):
    return f"{x:+.{d}f}%"


def short(name):
    return name.split(": ", 1)[-1]


PAN = (2020, 2021)


def svg_line(series, label, color, w=520, h=240):
    xs = [r["year"] for r in series]
    ys = [r["rate_per_100k"] for r in series]
    x0, x1, ymax = min(xs), max(xs), max(ys) * 1.1
    px = lambda x: 44 + (x - x0) / (x1 - x0) * (w - 60)
    py = lambda y: h - 28 - y / ymax * (h - 48)
    pts = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in zip(xs, ys))
    grid = ""
    for frac in (0, 0.5, 1):
        yv = ymax / 1.1 * frac
        grid += (f'<line x1="44" x2="{w-16}" y1="{py(yv):.1f}" y2="{py(yv):.1f}" class="g"/>'
                 f'<text x="38" y="{py(yv)+4:.1f}" text-anchor="end" class="t">{fmt(yv)}</text>')
    ticks = "".join(f'<text x="{px(x):.1f}" y="{h-8}" text-anchor="middle" class="t">{x}</text>'
                    for x in xs if x % 5 == 0)
    p0, p1 = PAN
    shade = (f'<rect x="{px(p0 - 0.5):.1f}" y="20" width="{px(p1 + 0.5) - px(p0 - 0.5):.1f}" height="{h-48}" class="pan"/>')
    last = series[-1]
    return (f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="{e(label)} rate per 100,000, '
            f'{x0} to {x1}">{shade}{grid}{ticks}<polyline points="{pts}" fill="none" stroke="{color}" '
            f'stroke-width="2.5"/><circle cx="{px(last["year"]):.1f}" cy="{py(last["rate_per_100k"]):.1f}" r="4" '
            f'fill="{color}"/></svg>')


def build(s, retrieved):
    offs = {o["offence"]: o for o in s["offences"]}
    cov, dn = s["coverage"], s["denominator_check"]
    ty0, ty1 = s["trend_window_years"]
    n_series = cov["n_offence_series"]
    n_up = sum(o["kendall"].get("direction") == "up" for o in s["offences"])
    n_down = sum(o["kendall"].get("direction") == "down" for o in s["offences"])
    n_stable = sum(o["kendall"].get("direction") == "stable" for o in s["offences"])
    n_nt = sum(not o["kendall"].get("tested") for o in s["offences"])
    kwin = next(o["kendall"] for o in s["offences"] if o["kendall"].get("tested"))
    n_flagged = sum(bool(o["flags"]) for o in s["offences"])
    under = (dn["abs_erp_june_1995"] / dn["bocsar_file_2025_population"] - 1) * 100
    gap = (dn["abs_erp_june_2025"] - dn["bocsar_file_2025_population"])
    n_months = (int(cov["last_month"][:4]) - int(cov["first_month"][:4])) * 12 + int(cov["last_month"][5:]) - int(cov["first_month"][5:]) + 1

    # headline table
    trs = ""
    for name in SELECTED:
        o = offs[name]; q, k = o["qp"], o["kendall"]
        qtxt = (f'{pct(q["apc"])} <span class="ci">({pct(q["apc_lo"])} to {pct(q["apc_hi"])})</span>'
                if q.get("fitted") else '<span class="muted">not estimable</span>')
        if k.get("tested"):
            arrow = {"up": "▲", "down": "▼", "stable": "●"}[k["direction"]]
            if k["direction"] == "stable":
                ktxt = f'<span class="k-stable">{arrow} stable</span> <span class="ci">(p={k["p_value"]:.2f})</span>'
            else:
                ktxt = f'<span class="k-{k["direction"]}">{arrow} {k["direction"]}</span> <span class="ci">{pct(k["avg_annual_pct_change"])}/yr</span>'
        else:
            ktxt = f'<span class="muted">not tested: {e(k.get("reason", ""))}</span>'
        fl = "".join(f'<span class="flag">{e(f.split(":")[0])}</span>' for f in o["flags"]) or '<span class="muted">none</span>'
        trs += (f'<tr><td>{e(short(name))}</td><td>{e(o["unit"])}</td><td class="n">{fmt(o[f"count_{ty1}"])}</td>'
                f'<td class="n">{fmt(o[f"rate_{ty1}"], 1)}</td><td>{qtxt}</td><td>{ktxt}</td><td>{fl}</td></tr>')

    # charts
    colors = ["#a29bfe", "#00cec9", "#fdcb6e", "#ff7675"]
    charts = ""
    for name, c in zip(CHARTS, colors):
        ser = s["annual"][name]
        first, last = ser[0], ser[-1]
        charts += (f'<div class="chart"><h4>{e(short(name))}</h4>{svg_line(ser, short(name), c)}'
                   f'<p class="cap">Rate per 100,000: {fmt(first["rate_per_100k"], 1)} in {first["year"]}, '
                   f'{fmt(last["rate_per_100k"], 1)} in {last["year"]}. Shaded band: {s["pandemic_years_sensitivity"][0]}-'
                   f'{s["pandemic_years_sensitivity"][1]}.</p></div>')

    # window-disagreement bars
    dis = []
    for o in s["offences"]:
        k, q = o["kendall"], o["qp"]
        if k.get("tested") and q.get("fitted") and k["direction"] != "stable":
            sig_q = q["apc_lo"] > 0 or q["apc_hi"] < 0
            if (k["direction"] == "up" and q["apc_hi"] < 0) or (k["direction"] == "down" and q["apc_lo"] > 0) \
               or (k["direction"] == "up" and not sig_q and k["avg_annual_pct_change"] > 5):
                dis.append(o)
    dis = sorted(dis, key=lambda o: -abs(o["kendall"]["avg_annual_pct_change"] - o["qp"]["apc"]))[:7]
    scale = max(max(abs(o["kendall"]["avg_annual_pct_change"]), abs(o["qp"]["apc"])) for o in dis)
    bars = ""
    for o in dis:
        a, b = o["kendall"]["avg_annual_pct_change"], o["qp"]["apc"]
        def bar(v, cls):
            wdt = abs(v) / scale * 50
            left = 50 if v >= 0 else 50 - wdt
            return f'<div class="bar {cls}" style="left:{left:.1f}%;width:{wdt:.1f}%"></div>'
        bars += (f'<div class="brow"><div class="blab">{e(short(o["offence"]))}</div><div class="btrack">'
                 f'<div class="zero"></div>{bar(a, "b60")}{bar(b, "b10")}</div><div class="bval">'
                 f'<span class="c60">{pct(a)}</span> / <span class="c10">{pct(b)}</span></div></div>')
    retail = offs["Theft: Steal from retail store"]

    # heatmap: rate index (first trend year = 100)
    hm_years = list(range(ty0, ty1 + 1))
    hm = '<div class="hm" style="grid-template-columns:minmax(150px,2.2fr) repeat(%d,minmax(34px,1fr))"><div></div>' % len(hm_years)
    hm += "".join(f'<div class="hy">{str(y)[2:]}</div>' for y in hm_years)
    for name in SELECTED:
        if name == "Coercive Control":
            continue
        rr = {r["year"]: r["rate_per_100k"] for r in s["annual"][name]}
        base = rr[ty0]
        hm += f'<div class="hl">{e(short(name))}</div>'
        for y in hm_years:
            idx = rr[y] / base * 100 if base else 0
            t = max(-1, min(1, (idx - 100) / 50))
            col = f"rgba(255,118,117,{abs(t):.2f})" if t > 0 else f"rgba(0,206,201,{abs(t):.2f})"
            hm += f'<div class="hc" style="background:{col}" title="{y}: {idx:.0f}">{idx:.0f}</div>'
    hm += "</div>"

    # flags list
    flag_items = ""
    for o in s["offences"]:
        for f in o["flags"]:
            if f.startswith(("NEW_SERIES", "LEVEL_SHIFT", "COUNTING_UNIT")):
                flag_items += f'<li><b>{e(short(o["offence"]))}</b>: {e(f)}</li>'
    n_pol = sum(any(f.startswith("POLICING") for f in o["flags"]) for o in s["offences"])
    cc = offs["Coercive Control"]
    cc_flag = next(f for f in cc["flags"] if f.startswith("NEW_SERIES"))
    murder = offs["Homicide: Murder"]

    vals = {k: v for k, v in locals().items() if isinstance(v, (str, int, float))}
    vals.update({f"src_{k}": v for k, v in SRC.items()})
    vals.update(bocsar_sha=s["inputs"]["bocsar"]["sha256"][:12], erp_sha=s["inputs"]["erp"]["sha256"][:12],
                cov_first=cov["first_month"], cov_last=cov["last_month"], fy0=cov["full_years"][0],
                fy1=cov["full_years"][1], dn_b=fmt(dn["bocsar_file_2025_population"]),
                dn_a25=fmt(dn["abs_erp_june_2025"]), dn_a95=fmt(dn["abs_erp_june_1995"]),
                dn_offence=e(short(dn["example_offence"])),
                dn_cnt=fmt(dn["example_1995_count"]), dn_r95=fmt(dn["example_1995_rate_with_1995_erp"], 1),
                dn_rfix=fmt(dn["example_1995_rate_with_fixed_2025_pop"], 1), under_s=f"{abs(under):.0f}",
                gap_s=fmt(gap), kw0=kwin["window_start"], kw1=kwin["window_end"],
                r_k=pct(retail["kendall"]["avg_annual_pct_change"]), r_q=pct(retail["qp"]["apc"]),
                r_lo=pct(retail["qp"]["apc_lo"]), r_hi=pct(retail["qp"]["apc_hi"]),
                pan0=s["pandemic_years_sensitivity"][0], pan1=s["pandemic_years_sensitivity"][1],
                cc_flag=e(cc_flag), cc_n=fmt(cc[f"count_{ty1}"]), m_n=fmt(murder[f"count_{ty1}"]),
                n_selected=len(SELECTED), n_dis=len(dis))
    return Template(TEMPLATE).substitute(vals)


TEMPLATE = open(Path(__file__).with_name("sample_template.html"), encoding="utf-8").read()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--summary", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--retrieved", required=True)
    a = ap.parse_args(argv)
    s = json.loads(a.summary.read_text())
    global PAN
    PAN = tuple(s["pandemic_years_sensitivity"])
    a.out.write_text(build(s, a.retrieved), encoding="utf-8")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
