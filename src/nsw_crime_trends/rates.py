"""Counts to population-adjusted rates."""
from __future__ import annotations

import pandas as pd

PER = 100_000


def annual_counts(monthly: pd.DataFrame) -> pd.DataFrame:
    """Calendar-year totals per offence.

    A series-year is kept only if that offence has a non-missing count for all
    12 months; otherwise it is excluded (so a missing month can never
    undercount a year).  Excluded series-years are listed in
    ``result.attrs["excluded_series_years"]``.
    """
    m = monthly.assign(year=monthly["month"].dt.year)
    cov = (m.groupby(["offence", "year"])
             .agg(n_months=("month", "nunique"), n_present=("count", lambda c: int(c.notna().sum())))
             .reset_index())
    cov["complete"] = (cov["n_months"] == 12) & (cov["n_present"] == 12)
    keep = cov.loc[cov["complete"], ["offence", "year"]]
    out = (m.merge(keep, on=["offence", "year"], how="inner")
            .groupby(["offence", "category", "unit", "year"], as_index=False)["count"].sum())
    out["count"] = out["count"].astype(int)
    out.attrs["excluded_series_years"] = cov.loc[~cov["complete"], ["offence", "year", "n_months", "n_present"]] \
        .to_dict("records")
    return out


def add_rates(annual: pd.DataFrame, erp_june: pd.Series) -> pd.DataFrame:
    """Rate per 100,000 residents using the June ERP of the same year."""
    df = annual.merge(erp_june.rename("erp"), left_on="year", right_index=True, how="left")
    if df["erp"].isna().any():
        missing = sorted(df.loc[df["erp"].isna(), "year"].unique())
        raise ValueError(f"No ERP denominator for years {missing}")
    df["rate_per_100k"] = df["count"] / df["erp"] * PER
    return df


def fixed_denominator_bias(annual_with_rates: pd.DataFrame, fixed_pop: float, year: int) -> pd.DataFrame:
    """Show how much a single fixed population would distort a historical rate."""
    d = annual_with_rates[annual_with_rates["year"] == year].copy()
    d["rate_fixed_pop"] = d["count"] / fixed_pop * PER
    d["pct_understated"] = (d["rate_fixed_pop"] / d["rate_per_100k"] - 1) * 100
    return d
