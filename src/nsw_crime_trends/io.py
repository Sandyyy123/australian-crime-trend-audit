"""Readers for the two public inputs.

1. BOCSAR "Recorded Criminal Incidents by month - All of NSW" (Incident_by_NSW.xlsx):
   one row per offence, one column per month from Jan 1995.
2. ABS Data API, dataflow ERP_Q (Quarterly Population Estimates), NSW, persons, all ages.

Both files are treated as untrusted data: they are parsed, never executed.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import openpyxl
import pandas as pd

ID_COLS = ("State", "Offence category", "Subcategory")


def load_bocsar(path: str | Path) -> pd.DataFrame:
    """Return a long table: offence, category, subcategory, month, count, unit.

    BOCSAR marks murder and manslaughter with an asterisk; for those rows the
    counting unit is victims, for every other row it is criminal incidents.
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb["Data"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    if tuple(header[:3]) != ID_COLS:
        raise ValueError(f"Unexpected BOCSAR header: {header[:5]}")
    month_idx = [i for i, h in enumerate(header) if isinstance(h, (dt.datetime, dt.date))]
    pop_cols = {str(h): i for i, h in enumerate(header) if isinstance(h, str) and "population" in h}
    records = []
    for r in rows[1:]:
        if r[0] is None:
            continue
        cat, sub = r[1], r[2]
        sub_clean = sub.replace("*", "").strip() if isinstance(sub, str) else None
        offence = f"{cat}: {sub_clean}" if sub_clean else cat
        unit = "victims" if isinstance(sub, str) and "*" in sub else "incidents"
        for i in month_idx:
            v = r[i]
            records.append({
                "offence": offence, "category": cat, "subcategory": sub_clean,
                "month": pd.Timestamp(header[i]), "count": int(v) if v is not None else pd.NA,
                "unit": unit,
            })
    df = pd.DataFrame.from_records(records)
    df["count"] = df["count"].astype("Int64")  # blank cells stay missing, never silently 0
    df.attrs["bocsar_population_columns"] = {k: rows[1][i] for k, i in pop_cols.items()}
    return df


def load_erp_june(path: str | Path) -> pd.Series:
    """Return June-quarter ERP (persons) indexed by calendar year.

    The June quarter is the ABS reference point for annual ERP, so it is used as
    the mid-year denominator for calendar-year rates.
    """
    erp = pd.read_csv(path, dtype={"TIME_PERIOD": str})
    need = {"TIME_PERIOD", "OBS_VALUE", "REGION", "SEX", "AGE", "MEASURE"}
    if not need.issubset(erp.columns):
        raise ValueError("Unexpected ABS ERP_Q columns")
    erp = erp[(erp["REGION"].astype(str) == "1") & (erp["SEX"].astype(str) == "3")
              & (erp["AGE"].astype(str) == "TOT") & (erp["MEASURE"].astype(str) == "1")]
    june = erp[erp["TIME_PERIOD"].str.endswith("-Q2")].copy()
    june["year"] = june["TIME_PERIOD"].str[:4].astype(int)
    return june.set_index("year")["OBS_VALUE"].astype(int).sort_index()
