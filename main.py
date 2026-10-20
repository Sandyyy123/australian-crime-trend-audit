#!/usr/bin/env python3
"""Run the NSW recorded-crime trend pipeline end to end.

Usage:
  python3 -I main.py --bocsar data_raw/Incident_by_NSW.xlsx \
      --erp data_raw/ABS_ERP_Q_NSW_persons.csv --out outputs
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "src"))

import pandas as pd  # noqa: E402

from nsw_crime_trends import __version__  # noqa: E402
from nsw_crime_trends.flags import build_flags  # noqa: E402
from nsw_crime_trends.io import load_bocsar, load_erp_june  # noqa: E402
from nsw_crime_trends.rates import add_rates, annual_counts, fixed_denominator_bias  # noqa: E402
from nsw_crime_trends.trends import kendall_60m, rate_trend_qp  # noqa: E402

TREND_START, TREND_END = 2016, 2025
PANDEMIC_YEARS = (2020, 2021)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(bocsar: Path, erp: Path, out: Path) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    monthly = load_bocsar(bocsar)
    erp_june = load_erp_june(erp)
    ann = annual_counts(monthly)
    excluded = ann.attrs.get("excluded_series_years", [])
    annual = add_rates(ann, erp_june)
    flags = build_flags(monthly, annual)
    last_month = monthly["month"].max()

    trend_rows = []
    for off, g in annual.groupby("offence"):
        ms = monthly[monthly["offence"] == off].set_index("month")["count"]
        k = kendall_60m(ms, end=last_month)
        q = rate_trend_qp(g, TREND_START, TREND_END)
        qs = rate_trend_qp(g, TREND_START, TREND_END, exclude=PANDEMIC_YEARS)
        if not ({TREND_START, TREND_END} <= set(g["year"])):
            raise ValueError(f"{off}: incomplete months in {TREND_START} or {TREND_END}; see excluded_series_years")
        latest = g[g["year"] == TREND_END].iloc[0]
        base = g[g["year"] == TREND_START].iloc[0]
        trend_rows.append({
            "offence": off, "category": g["category"].iloc[0], "unit": g["unit"].iloc[0],
            f"count_{TREND_START}": int(base["count"]), f"count_{TREND_END}": int(latest["count"]),
            f"rate_{TREND_START}": round(float(base["rate_per_100k"]), 2),
            f"rate_{TREND_END}": round(float(latest["rate_per_100k"]), 2),
            "kendall": k, "qp": q, "qp_excl_pandemic": qs,
            "flags": flags.loc[flags["offence"] == off, "flags"].iloc[0],
        })

    annual.to_csv(out / "annual_counts_rates.csv", index=False)
    flat = pd.json_normalize(trend_rows, sep=".")
    flat["flags"] = flat["flags"].apply(lambda f: " | ".join(f))
    flat.to_csv(out / "trend_summary.csv", index=False)

    bocsar_pops = monthly.attrs.get("bocsar_population_columns", {})
    bocsar_2025 = bocsar_pops.get("2025 population")
    denom = None
    if bocsar_2025:
        # Use one incident series: summing all offences would mix incidents
        # with the victim-counted murder and manslaughter series.
        example_offence = "Theft: Steal from retail store"
        example = annual.loc[annual["offence"] == example_offence]
        if example.empty or set(example["unit"]) != {"incidents"}:
            raise ValueError("Denominator example requires the retail-theft incident series")
        b = fixed_denominator_bias(example, float(bocsar_2025), 1995)
        if len(b) != 1:
            raise ValueError("Denominator example requires exactly one complete 1995 observation")
        count = int(b["count"].iloc[0])
        denom = {"bocsar_file_2025_population": int(bocsar_2025),
                 "abs_erp_june_2025": int(erp_june.loc[2025]),
                 "abs_erp_june_1995": int(erp_june.loc[1995]),
                 "example_offence": example_offence,
                 "example_unit": "incidents",
                 "example_1995_count": count,
                 "example_1995_rate_with_1995_erp": round(count / erp_june.loc[1995] * 1e5, 1),
                 "example_1995_rate_with_fixed_2025_pop": round(count / bocsar_2025 * 1e5, 1)}

    summary = {
        "tool_version": __version__,
        "inputs": {"bocsar": {"file": bocsar.name, "sha256": sha256(bocsar)},
                   "erp": {"file": erp.name, "sha256": sha256(erp)}},
        "coverage": {"first_month": monthly["month"].min().strftime("%Y-%m"),
                     "last_month": last_month.strftime("%Y-%m"),
                     "n_offence_series": int(monthly["offence"].nunique()),
                     "full_years": [int(annual["year"].min()), int(annual["year"].max())]},
        "trend_window_years": [TREND_START, TREND_END], "pandemic_years_sensitivity": list(PANDEMIC_YEARS),
        "denominator_check": denom,
        "excluded_series_years": excluded,
        "erp_june": {int(k): int(v) for k, v in erp_june.items()},
        "offences": trend_rows,
        "annual": {off: g[["year", "count", "rate_per_100k"]].round(2).to_dict("records")
                   for off, g in annual.groupby("offence")},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=float))
    return summary


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bocsar", type=Path, required=True)
    ap.add_argument("--erp", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "outputs")
    a = ap.parse_args(argv)
    s = run(a.bocsar, a.erp, a.out)
    n_up = sum(1 for o in s["offences"] if o["kendall"].get("direction") == "up")
    n_down = sum(1 for o in s["offences"] if o["kendall"].get("direction") == "down")
    print(f"{s['coverage']['n_offence_series']} offence series, {s['coverage']['first_month']} to "
          f"{s['coverage']['last_month']}; 60-month trend up={n_up} down={n_down}; outputs in {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
