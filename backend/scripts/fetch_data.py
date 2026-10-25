"""Download January 2026 wind actuals (FUELHH) and forecasts (WINDFOR) into data/*.json.

Run from the repo root:  python backend/scripts/fetch_data.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import data  # noqa: E402

if __name__ == "__main__":
    print("Fetching FUELHH (WIND) and WINDFOR from Elexon ...")
    actuals, forecasts = data.fetch_all()
    print(f"  actuals rows:   {len(actuals)}")
    print(f"  forecasts rows: {len(forecasts)}")
    if actuals.empty or forecasts.empty:
        sys.exit("No rows returned - check the date window and the Elexon API status.")
    data.save_raw(actuals, forecasts)
    print(f"Saved to {data.DATA_DIR}")
