"""Pure analysis logic: no web framework, no network. Everything here is unit-tested.

Key idea
--------
A buyer trading in the day-ahead market for delivery day D must decide by a
cutoff time on day D-1 (default 09:00 UK time). For every half-hour of D the
forecast they could actually have seen is the *latest* WINDFOR forecast whose
publishTime is at or before that cutoff. Using any later forecast would be
look-ahead bias, so accuracy is always measured on this "decision-time" forecast.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

LONDON = "Europe/London"
DECISION_START = "2026-01-01"  # purchase decisions made in January 2026
DECISION_END = "2026-01-31"
HORIZON_BUCKET_H = 6


# --------------------------------------------------------------------------- prep
def prepare_actuals(raw: pd.DataFrame) -> pd.DataFrame:
    """FUELHH rows (already WIND only) -> startTime (UTC), generation (MW)."""
    a = raw.copy()
    a["startTime"] = pd.to_datetime(a["startTime"], utc=True)
    a["generation"] = pd.to_numeric(a["generation"], errors="coerce")
    if "publishTime" in a.columns:
        a["publishTime"] = pd.to_datetime(a["publishTime"], utc=True)
        a = a.sort_values(["startTime", "publishTime"])
    else:
        a = a.sort_values("startTime")
    a = a.dropna(subset=["generation"]).drop_duplicates("startTime", keep="last")
    return a[["startTime", "generation"]].reset_index(drop=True)


def prepare_forecasts(raw: pd.DataFrame) -> pd.DataFrame:
    f = raw.copy()
    f["startTime"] = pd.to_datetime(f["startTime"], utc=True)
    f["publishTime"] = pd.to_datetime(f["publishTime"], utc=True)
    f["generation"] = pd.to_numeric(f["generation"], errors="coerce")
    f = f.dropna(subset=["generation"])
    return f[["startTime", "publishTime", "generation"]].reset_index(drop=True)


# ------------------------------------------------------------ decision-time forecast
def latest_forecasts(forecasts: pd.DataFrame, cutoff_hour: int = 9, cutoff_minute: int = 0) -> pd.DataFrame:
    """For each target half-hour keep the newest forecast published by the cutoff on the previous UK day."""
    f = forecasts.copy()
    local_day = f["startTime"].dt.tz_convert(LONDON).dt.tz_localize(None).dt.normalize()
    cutoff_local = local_day - pd.Timedelta(days=1) + pd.Timedelta(hours=cutoff_hour, minutes=cutoff_minute)
    f["cutoff"] = cutoff_local.dt.tz_localize(LONDON, ambiguous="NaT", nonexistent="shift_forward").dt.tz_convert("UTC")
    f["delivery_date"] = local_day.dt.strftime("%Y-%m-%d")
    f["decision_date"] = (local_day - pd.Timedelta(days=1)).dt.strftime("%Y-%m-%d")
    f = f[f["publishTime"] <= f["cutoff"]]
    f = f.sort_values(["startTime", "publishTime"]).drop_duplicates("startTime", keep="last")
    f["horizon_h"] = (f["startTime"] - f["publishTime"]).dt.total_seconds() / 3600.0
    return f.rename(columns={"generation": "forecast"}).reset_index(drop=True)


def decision_frame(
    actuals: pd.DataFrame,
    forecasts: pd.DataFrame,
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
    decision_start: str = DECISION_START,
    decision_end: str = DECISION_END,
) -> pd.DataFrame:
    """Decision-time forecast joined to actuals (actual is NaN where not yet observed)."""
    f = latest_forecasts(forecasts, cutoff_hour, cutoff_minute)
    f = f[(f["decision_date"] >= decision_start) & (f["decision_date"] <= decision_end)]
    a = actuals.rename(columns={"generation": "actual"})
    df = f.merge(a, on="startTime", how="left")
    local = df["startTime"].dt.tz_convert(LONDON)
    df["slot"] = local.dt.strftime("%H:%M")
    df["error"] = df["actual"] - df["forecast"]  # >0: wind beat the forecast
    df["abs_error"] = df["error"].abs()
    return df.sort_values("startTime").reset_index(drop=True)


# ------------------------------------------------------------------------ metrics
def summarise(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["actual", "forecast"])
    if d.empty:
        return {"n": 0}
    err = d["actual"] - d["forecast"]
    ae = err.abs()
    shortfall = d["forecast"] - d["actual"]  # >0: forecast overstated wind -> buyer is short
    total_actual = float(d["actual"].sum())
    return {
        "n": int(len(d)),
        "mean_actual": float(d["actual"].mean()),
        "mean_forecast": float(d["forecast"].mean()),
        "mae": float(ae.mean()),
        "rmse": float(math.sqrt((err**2).mean())),
        "bias": float(err.mean()),
        "wmape_pct": float(100 * ae.sum() / total_actual) if total_actual > 0 else None,
        "p50_abs_err": float(np.quantile(ae, 0.5)),
        "p90_abs_err": float(np.quantile(ae, 0.9)),
        "p95_abs_err": float(np.quantile(ae, 0.95)),
        "overforecast_share_pct": float(100 * (shortfall > 0).mean()),
        "p90_shortfall": float(max(np.quantile(shortfall, 0.9), 0.0)),
        "p95_shortfall": float(max(np.quantile(shortfall, 0.95), 0.0)),
    }


def _group(df: pd.DataFrame, key: str, extra_actual: bool = False) -> list[dict]:
    d = df.dropna(subset=["actual", "forecast"])
    out = []
    for k, g in d.groupby(key, sort=True):
        row = {
            key: k if not isinstance(k, (np.floating, np.integer)) else float(k),
            "n": int(len(g)),
            "mae": float(g["abs_error"].mean()),
            "bias": float(g["error"].mean()),
        }
        if extra_actual:
            row["mean_actual"] = float(g["actual"].mean())
        out.append(row)
    return out


def by_slot(df: pd.DataFrame) -> list[dict]:
    return _group(df, "slot")


def by_day(df: pd.DataFrame) -> list[dict]:
    return _group(df, "delivery_date", extra_actual=True)


def by_horizon(df: pd.DataFrame) -> list[dict]:
    d = df.dropna(subset=["actual", "forecast"]).copy()
    if d.empty:
        return []
    d["bucket"] = (np.floor(d["horizon_h"] / HORIZON_BUCKET_H) * HORIZON_BUCKET_H).astype(int)
    rows = _group(d, "bucket")
    for r in rows:
        lo = int(r["bucket"])
        r["label"] = f"{lo}-{lo + HORIZON_BUCKET_H}h"
    return rows


# ----------------------------------------------------------- one delivery day view
def error_bands(df: pd.DataFrame, decision_date: str) -> dict:
    """10th/90th percentile of (actual - forecast) using only outcomes known at decision time.

    At 09:00 on decision day D-1 the actuals for delivery day D-1 are not complete,
    so only delivery days strictly before the decision date are usable. If there
    is not enough history we fall back to all days and say so (in-sample).
    """
    known = df.dropna(subset=["actual"])
    hist = known[known["delivery_date"] < decision_date]
    basis = "prior_days"
    if hist["delivery_date"].nunique() < 2:
        hist, basis = known, "all_days_in_sample"
    if hist.empty:
        return {"q_low": 0.0, "q_high": 0.0, "basis": "none", "days": 0}
    return {
        "q_low": float(np.quantile(hist["error"], 0.10)),
        "q_high": float(np.quantile(hist["error"], 0.90)),
        "basis": basis,
        "days": int(hist["delivery_date"].nunique()),
    }


def delivery_day(df: pd.DataFrame, decision_date: str) -> dict:
    day = df[df["decision_date"] == decision_date].copy()
    if day.empty:
        return {"series": [], "summary": None}
    bands = error_bands(df, decision_date)
    day["low"] = (day["forecast"] + bands["q_low"]).clip(lower=0)
    day["high"] = day["forecast"] + bands["q_high"]
    series = day[["startTime", "slot", "forecast", "publishTime", "horizon_h", "actual", "low", "high"]].to_dict("records")
    summary = {
        "delivery_date": str(day["delivery_date"].iloc[0]),
        "mean_forecast": float(day["forecast"].mean()),
        "peak_forecast": float(day["forecast"].max()),
        "min_forecast": float(day["forecast"].min()),
        "mean_reliable": float(day["low"].mean()),
        "first_publish": day["publishTime"].min(),
        "last_publish": day["publishTime"].max(),
        "cutoff": day["cutoff"].iloc[0],
        "slots": int(len(day)),
        "bands": bands,
    }
    return {"series": series, "summary": summary}


# -------------------------------------------------------------------- json helper
def clean(o):
    if o is pd.NaT:
        return None
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, pd.Timestamp):
        return o.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(o, (float, np.floating)):
        return None if (math.isnan(o) or math.isinf(o)) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    return o
