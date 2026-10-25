# Wind Forecast Desk

A web app for a UK energy utility's day-ahead trading desk. It answers two questions using only Elexon national wind data:

1. **What is the latest wind forecast I can use for tomorrow's purchase?** The forecast published most recently before the day-ahead cutoff (default 09:00 UK time on the day before delivery).
2. **How accurate has that forecast been?** Average miss, bias, bad-day risk, error by time of day, forecast age, and delivery day.

Scope: wind only, national level, purchase decisions made 1-31 January 2026 (delivery 2 Jan - 1 Feb 2026).

**Live app:** _add your Heroku URL here_

## How the numbers are built

- Actuals: Elexon `FUELHH`, `fuelType = WIND`, field `generation` (MW) at `startTime`.
- Forecasts: Elexon `WINDFOR`, fields `startTime`, `publishTime`, `generation`.
- For each half-hour of delivery day D, the **decision-time forecast** is the `WINDFOR` row with the latest `publishTime` at or before the cutoff on D-1 (UK clock time, so DST-safe). No later forecast is ever used, which avoids look-ahead bias.
- Accuracy is computed on those decision-time forecasts vs actuals. `error = actual - forecast`. A **shortfall** is forecast minus actual, the extra power the buyer would have needed because wind was overstated.
- Metrics: MAE, RMSE, bias, weighted MAPE (sum of absolute error / sum of actuals, which avoids dividing by near-zero wind), percentiles of absolute error and shortfall.
- The "likely range" on the buying view adds the 10th/90th percentile of past errors to the forecast, using only delivery days whose actuals were already known at decision time. For the first days of January there is not enough history, so it falls back to all days and the UI says so.

**Assumptions to confirm with the client:** the 09:00 cutoff is configurable in the UI (08:00-12:00). Elexon times are UTC; January has no BST, but cutoffs are computed in `Europe/London` anyway.

## Layout

```
backend/
  app/logic.py        pure analysis (cutoff selection, metrics, bands) - unit tested
  app/data.py         Elexon fetch (7-day chunks) + JSON cache + loading
  app/main.py         FastAPI routes; also serves the built React app
  scripts/fetch_data.py   download Jan 2026 data into data/
  tests/test_logic.py     unit tests (run with unittest)
frontend/             React + Vite + Recharts
data/                 cached actuals.json / forecasts.json (commit these for deployment)
Dockerfile            multi-stage: build UI, then Python image serving API + UI
docker-compose.yml, heroku.yml
```

## Run it

```bash
# 1. get the data once (needs internet) and commit it
pip install -r backend/requirements.txt
python backend/scripts/fetch_data.py

# 2a. Docker
docker compose up --build        # http://localhost:8000

# 2b. or local dev
cd backend && uvicorn app.main:app --reload --port 8000
cd frontend && npm install && npm run dev   # http://localhost:5173 (proxies /api)
```

Tests: `cd backend && python -m unittest discover -s tests`

## Deploy

Heroku (Docker): `heroku create && heroku stack:set container && git push heroku main`. The container reads `$PORT`. Vercel cannot run this Docker image, so use Heroku (or Render/Fly) for the container deploy.

## Notes on AI use

Built with assistance from Claude (Anthropic). The cutoff logic, metrics and tests were reviewed and run by the author.

## Limitations

- National level only, no demand data, so "wind you can rely on" is a wind figure, not a purchase volume.
- Error bands are empirical percentiles from one month; a single winter month is a small sample.
