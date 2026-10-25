"""Elexon data access: fetch (chunked), cache to data/*.json, load into DataFrames."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

from . import logic

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
DATA_DIR = Path(os.getenv("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))

# Decisions are made 1-31 Jan 2026 for delivery 2-Jan..1-Feb 2026 (UK time == UTC in January).
ACTUALS_FROM = datetime(2026, 1, 2, tzinfo=timezone.utc)
ACTUALS_TO = datetime(2026, 2, 2, 1, 30, tzinfo=timezone.utc)
# Forecasts: anything published from late Dec (long horizons) up to the last cutoff on 31 Jan.
FORECAST_FROM = datetime(2025, 12, 28, tzinfo=timezone.utc)
FORECAST_TO = datetime(2026, 2, 1, 0, 0, tzinfo=timezone.utc)

CHUNK_DAYS = 7  # keep each request small; Elexon stream endpoints can time out on big ranges


def _iso(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%MZ")


def _get(dataset: str, params: dict) -> list[dict]:
    r = requests.get(f"{BASE}/{dataset}/stream", params=params, timeout=90)
    r.raise_for_status()
    js = r.json()
    return js if isinstance(js, list) else js.get("data", [])


def fetch_range(dataset: str, start: datetime, end: datetime, extra: dict | None = None) -> list[dict]:
    rows: list[dict] = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=CHUNK_DAYS), end)
        params = {"publishDateTimeFrom": _iso(cur), "publishDateTimeTo": _iso(nxt), **(extra or {})}
        rows.extend(_get(dataset, params))
        cur = nxt
    return rows


def fetch_all() -> tuple[pd.DataFrame, pd.DataFrame]:
    actual_rows = fetch_range("FUELHH", ACTUALS_FROM, ACTUALS_TO, {"fuelType": "WIND"})
    actual_rows = [r for r in actual_rows if r.get("fuelType", "WIND") == "WIND"]
    forecast_rows = fetch_range("WINDFOR", FORECAST_FROM, FORECAST_TO)
    return pd.DataFrame(actual_rows), pd.DataFrame(forecast_rows)


def save_raw(actuals: pd.DataFrame, forecasts: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    actuals.to_json(DATA_DIR / "actuals.json", orient="records", date_format="iso")
    forecasts.to_json(DATA_DIR / "forecasts.json", orient="records", date_format="iso")
    (DATA_DIR / "meta.json").write_text(json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(), "source": "Elexon Insights API"}))


def load() -> dict:
    """Load cached data; if absent, fetch live and cache it."""
    a_path, f_path = DATA_DIR / "actuals.json", DATA_DIR / "forecasts.json"
    if not (a_path.exists() and f_path.exists()):
        raw_a, raw_f = fetch_all()
        save_raw(raw_a, raw_f)
    raw_a, raw_f = pd.read_json(a_path), pd.read_json(f_path)
    meta_path = DATA_DIR / "meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    actuals, forecasts = logic.prepare_actuals(raw_a), logic.prepare_forecasts(raw_f)
    if actuals.empty or forecasts.empty:
        raise RuntimeError("Cached data is empty; delete data/*.json and re-run scripts/fetch_data.py")
    return {"actuals": actuals, "forecasts": forecasts, "meta": meta}
