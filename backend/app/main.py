from __future__ import annotations

import os
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import data, logic

app = FastAPI(title="Wind Forecast Desk", version="1.0.0")

# Allow the deployed Vercel frontend to call this Render API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://wind-forecast-desk-hazel.vercel.app",
    ],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)

DEFAULT_CUTOFF = (9, 0)
CUTOFF_CHOICES = [(8, 0), (9, 0), (10, 0), (11, 0), (12, 0)]


@lru_cache(maxsize=1)
def store() -> dict:
    try:
        return data.load()
    except Exception as exc:
        # Surface data-loading errors as readable API errors.
        raise HTTPException(503, f"Data unavailable: {exc}") from exc


@lru_cache(maxsize=32)
def frame(hour: int, minute: int):
    s = store()
    return logic.decision_frame(
        s["actuals"],
        s["forecasts"],
        hour,
        minute,
    )


def _check_cutoff(hour: int, minute: int) -> None:
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise HTTPException(422, "Cutoff must be a valid UK clock time")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/meta")
def meta():
    s = store()
    return logic.clean(
        {
            "decision_start": logic.DECISION_START,
            "decision_end": logic.DECISION_END,
            "default_cutoff": {
                "hour": DEFAULT_CUTOFF[0],
                "minute": DEFAULT_CUTOFF[1],
            },
            "cutoff_choices": [
                {"hour": h, "minute": m}
                for h, m in CUTOFF_CHOICES
            ],
            "actual_rows": len(s["actuals"]),
            "forecast_rows": len(s["forecasts"]),
            "fetched_at": s["meta"].get("fetched_at"),
        }
    )


@app.get("/api/decision")
def decision(
    decision_date: date,
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
):
    """Return tomorrow's forecast as available at the decision-time cutoff."""
    _check_cutoff(cutoff_hour, cutoff_minute)

    iso = decision_date.isoformat()

    if not (logic.DECISION_START <= iso <= logic.DECISION_END):
        raise HTTPException(
            422,
            f"Decision date must be between "
            f"{logic.DECISION_START} and {logic.DECISION_END}",
        )

    out = logic.delivery_day(
        frame(cutoff_hour, cutoff_minute),
        iso,
    )

    if not out["series"]:
        raise HTTPException(
            404,
            "No forecast was published before the cutoff for that delivery day",
        )

    out["decision_date"] = iso
    out["delivery_date"] = (
        decision_date + timedelta(days=1)
    ).isoformat()

    return logic.clean(out)


@app.get("/api/evaluation")
def evaluation(
    cutoff_hour: int = 9,
    cutoff_minute: int = 0,
):
    """Evaluate decision-time forecast accuracy across January."""
    _check_cutoff(cutoff_hour, cutoff_minute)

    df = frame(cutoff_hour, cutoff_minute)
    scored = df.dropna(subset=["actual", "forecast"])

    if scored.empty:
        raise HTTPException(
            404,
            "No overlapping actuals and forecasts to evaluate",
        )

    series = scored[
        ["startTime", "forecast", "actual"]
    ].to_dict("records")

    sensitivity = []

    for h, m in CUTOFF_CHOICES:
        summary = logic.summarise(frame(h, m))

        if summary.get("n"):
            sensitivity.append(
                {
                    "hour": h,
                    "minute": m,
                    "mae": summary["mae"],
                    "wmape_pct": summary["wmape_pct"],
                    "n": summary["n"],
                }
            )

    return logic.clean(
        {
            "cutoff": {
                "hour": cutoff_hour,
                "minute": cutoff_minute,
            },
            "metrics": logic.summarise(df),
            "by_slot": logic.by_slot(df),
            "by_day": logic.by_day(df),
            "by_horizon": logic.by_horizon(df),
            "series": series,
            "cutoff_sensitivity": sensitivity,
        }
    )

STATIC = Path(
    os.getenv(
        "STATIC_DIR",
        Path(__file__).resolve().parents[2] / "static",
    )
)

if STATIC.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=STATIC / "assets"),
        name="assets",
    )

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API route")

        candidate = STATIC / path

        if (
            path
            and candidate.is_file()
            and STATIC in candidate.resolve().parents
        ):
            return FileResponse(candidate)

        return FileResponse(STATIC / "index.html")
