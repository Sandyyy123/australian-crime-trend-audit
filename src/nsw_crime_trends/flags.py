"""Data-quality and interpretation flags.

The flags never 'correct' the data. They tell the reader where a change in the
numbers may come from counting rules, new offences, policing activity or a
recording/definition change rather than from a change in offending.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# Offences BOCSAR names as largely detected by police, so recorded levels track
# policing activity ("Using crime statistics", BOCSAR, page updated 5 Feb 2025).
POLICING_SENSITIVE_CATEGORIES = {"Drug offences"}
POLICING_SENSITIVE_OFFENCES = {"Disorderly conduct: Offensive conduct", "Disorderly conduct: Offensive language",
                               "Theft: Receiving or handling stolen goods"}


def first_nonzero(monthly: pd.Series) -> pd.Timestamp | None:
    m = monthly.dropna()
    nz = m[m > 0]
    return nz.index[0] if len(nz) else None


def level_shifts(annual_counts: pd.Series, z: float = 3.5, min_change: float = 0.5) -> list[dict]:
    """Year-on-year jumps that are extreme relative to the series' own variability.

    Uses a robust z-score of log ratios (median/MAD), and also requires at least a
    50% change so that tiny, noisy series do not dominate.
    """
    s = annual_counts.sort_index()
    s = s[s > 0]
    if len(s) < 6:
        return []
    lr = np.log(s).diff().dropna()
    med = lr.median()
    mad = (lr - med).abs().median() * 1.4826
    if mad == 0:
        return []
    out = []
    for yr, v in lr.items():
        rz = (v - med) / mad
        if abs(rz) >= z and abs(np.expm1(v)) >= min_change:
            out.append({"year": int(yr), "pct_change": float(np.expm1(v) * 100), "robust_z": float(rz)})
    return out


def build_flags(monthly: pd.DataFrame, annual: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for off, g in monthly.groupby("offence"):
        s = g.set_index("month")["count"].sort_index()
        cat, unit = g["category"].iloc[0], g["unit"].iloc[0]
        flags = []
        n_missing = int(s.isna().sum())
        if n_missing:
            flags.append(f"MISSING_MONTHS: {n_missing} blank month(s); affected years excluded from annual totals")
        if unit == "victims":
            flags.append("COUNTING_UNIT: counted as victims, not incidents")
        fnz = first_nonzero(s)
        if fnz is not None and fnz > s.index[0] + pd.DateOffset(months=12):
            flags.append(f"NEW_SERIES: zero until {fnz.strftime('%Y-%m')} (new offence or recording category)")
        if cat in POLICING_SENSITIVE_CATEGORIES or off in POLICING_SENSITIVE_OFFENCES:
            flags.append("POLICING_SENSITIVE: mainly detected by police; trend reflects enforcement")
        a = annual[annual["offence"] == off].set_index("year")["count"]
        for ls in level_shifts(a):
            flags.append(f"LEVEL_SHIFT: {ls['year']} {ls['pct_change']:+.0f}% vs prior year "
                         f"(check for recording/definition change)")
        rows.append({"offence": off, "flags": flags})
    return pd.DataFrame(rows)
