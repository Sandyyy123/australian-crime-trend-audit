"""Trend tests.

* kendall_60m: our re-implementation of the BOCSAR convention (Kendall's tau-b on
  monthly counts over 60 months, p<.05; no test if any 12-month total < 20;
  average annual % change from the first and last 12-month totals).
* rate_trend_qp: quasi-Poisson regression of annual counts with log(ERP) offset,
  giving the annual percent change in the RATE with a 95% CI (t-based, scale
  estimated from Pearson chi-square so over-dispersion widens the interval).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy import stats


def kendall_60m(series: pd.Series, end: pd.Timestamp | None = None, months: int = 60,
                min_annual: int = 20) -> dict:
    s = series.sort_index()
    if end is not None:
        s = s[s.index <= end]
    s = s.iloc[-months:]
    if len(s) < months:
        return {"tested": False, "reason": "fewer than 60 months"}
    if s.isna().any():
        return {"tested": False, "reason": "missing months in the 60-month window"}
    s = s.astype(float)
    totals = s.values.reshape(months // 12, 12).sum(axis=1)
    out = {"window_start": s.index[0].strftime("%Y-%m"), "window_end": s.index[-1].strftime("%Y-%m"),
           "first_12m": int(totals[0]), "last_12m": int(totals[-1])}
    if (totals < min_annual).any():
        return {**out, "tested": False, "reason": "a 12-month total is below 20"}
    tau, p = stats.kendalltau(np.arange(months), s.values)  # tau-b by default
    years = months // 12
    aapc = ((totals[-1] / totals[0]) ** (1 / (years - 1)) - 1) * 100 if totals[0] > 0 else np.nan
    if p < 0.05:
        direction = "up" if tau > 0 else "down"
    else:
        direction = "stable"
    return {**out, "tested": True, "tau_b": float(tau), "p_value": float(p),
            "direction": direction, "avg_annual_pct_change": float(aapc)}


def rate_trend_qp(annual: pd.DataFrame, start: int, end: int, exclude: tuple[int, ...] = ()) -> dict:
    """annual: one offence, columns year, count, erp."""
    d = annual[(annual["year"] >= start) & (annual["year"] <= end) & ~annual["year"].isin(exclude)]
    d = d.sort_values("year")
    if len(d) < 5 or d["count"].sum() == 0 or (d["count"] == 0).mean() > 0.5:
        return {"fitted": False, "reason": "too few non-zero years"}
    X = sm.add_constant((d["year"] - start).astype(float))
    model = sm.GLM(d["count"].astype(float), X, family=sm.families.Poisson(),
                   offset=np.log(d["erp"].astype(float)))
    fit = model.fit(scale="X2")
    b, se = float(fit.params.iloc[1]), float(fit.bse.iloc[1])
    dfree = len(d) - 2
    tq = stats.t.ppf(0.975, dfree)
    p = 2 * stats.t.sf(abs(b / se), dfree) if se > 0 else 0.0
    return {"fitted": True, "years": f"{start}-{end}", "n_years": int(len(d)),
            "excluded": list(exclude), "apc": float(np.expm1(b) * 100),
            "apc_lo": float(np.expm1(b - tq * se) * 100), "apc_hi": float(np.expm1(b + tq * se) * 100),
            "p_value": float(p), "dispersion": float(fit.scale)}
