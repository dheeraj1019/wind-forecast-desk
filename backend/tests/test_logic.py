import unittest

import numpy as np
import pandas as pd

from app import logic


def synthetic(days=6, start="2026-01-01"):
    """Known world: actual = 1000 + slot index; forecasts published hourly, 1..59h ahead."""
    idx = pd.date_range(start, periods=days * 48, freq="30min", tz="UTC")
    actual = pd.DataFrame({"startTime": idx, "generation": 1000 + np.arange(len(idx)) * 1.0})
    rows = []
    for t in idx:
        for k in range(1, 60):
            p = t - pd.Timedelta(hours=k)
            rows.append((t, p, 1000 + (t - idx[0]).total_seconds() / 1800 + (100 if k > 30 else 20)))
    fc = pd.DataFrame(rows, columns=["startTime", "publishTime", "generation"])
    return logic.prepare_actuals(actual), logic.prepare_forecasts(fc)


class TestLatestForecast(unittest.TestCase):
    def setUp(self):
        self.a, self.f = synthetic()

    def test_no_lookahead(self):
        lf = logic.latest_forecasts(self.f, 9, 0)
        self.assertTrue((lf["publishTime"] <= lf["cutoff"]).all())

    def test_picks_newest_before_cutoff(self):
        lf = logic.latest_forecasts(self.f, 9, 0)
        row = lf[lf["startTime"] == pd.Timestamp("2026-01-03 12:00", tz="UTC")].iloc[0]
        self.assertEqual(row["publishTime"], pd.Timestamp("2026-01-02 09:00", tz="UTC"))
        self.assertAlmostEqual(row["horizon_h"], 27.0)

    def test_earlier_cutoff_uses_older_forecast(self):
        late = logic.latest_forecasts(self.f, 12, 0)
        early = logic.latest_forecasts(self.f, 6, 0)
        t = pd.Timestamp("2026-01-04 00:00", tz="UTC")
        self.assertLess(early[early.startTime == t].publishTime.iloc[0], late[late.startTime == t].publishTime.iloc[0])

    def test_dst_cutoff_is_london_time(self):
        idx = pd.date_range("2026-07-02", periods=2, freq="30min", tz="UTC")
        f = pd.DataFrame({"startTime": idx, "publishTime": idx - pd.Timedelta(hours=30), "generation": [1, 2]})
        lf = logic.latest_forecasts(logic.prepare_forecasts(f), 9, 0)
        self.assertEqual(lf["cutoff"].iloc[0], pd.Timestamp("2026-07-01 08:00", tz="UTC"))  # 09:00 BST


class TestMetrics(unittest.TestCase):
    def test_known_errors(self):
        df = pd.DataFrame({"actual": [100.0, 200.0, 300.0, 400.0], "forecast": [110.0, 190.0, 330.0, 400.0]})
        df["error"] = df.actual - df.forecast
        df["abs_error"] = df.error.abs()
        m = logic.summarise(df)
        self.assertAlmostEqual(m["mae"], 12.5)
        self.assertAlmostEqual(m["bias"], -7.5)
        self.assertAlmostEqual(m["rmse"], float(np.sqrt((100 + 100 + 900) / 4)))
        self.assertAlmostEqual(m["wmape_pct"], 5.0)
        self.assertAlmostEqual(m["overforecast_share_pct"], 50.0)  # 110>100 and 330>300

    def test_decision_frame_window(self):
        a, f = synthetic(days=6)
        df = logic.decision_frame(a, f, 9, 0, "2026-01-01", "2026-01-03")
        self.assertEqual(df["decision_date"].min(), "2026-01-01")
        self.assertEqual(df["decision_date"].max(), "2026-01-03")
        self.assertEqual(len(df), 3 * 48)
        self.assertFalse(df["actual"].isna().any())

    def test_groups(self):
        a, f = synthetic(days=6)
        df = logic.decision_frame(a, f, 9, 0, "2026-01-01", "2026-01-04")
        self.assertEqual(len(logic.by_slot(df)), 48)
        self.assertEqual(len(logic.by_day(df)), 4)
        self.assertTrue(all("label" in r for r in logic.by_horizon(df)))


class TestDeliveryDay(unittest.TestCase):
    def test_bands_use_only_prior_days(self):
        a, f = synthetic(days=7)
        df = logic.decision_frame(a, f, 9, 0, "2026-01-01", "2026-01-05")
        b = logic.error_bands(df, "2026-01-04")
        self.assertEqual(b["basis"], "prior_days")
        self.assertLess(b["days"], 4)
        self.assertEqual(logic.error_bands(df, "2026-01-01")["basis"], "all_days_in_sample")

    def test_payload_is_json_safe(self):
        a, f = synthetic(days=7)
        df = logic.decision_frame(a, f, 9, 0, "2026-01-01", "2026-01-05")
        out = logic.clean(logic.delivery_day(df, "2026-01-03"))
        self.assertEqual(len(out["series"]), 48)
        self.assertEqual(out["summary"]["delivery_date"], "2026-01-04")
        self.assertTrue(out["series"][0]["publishTime"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
