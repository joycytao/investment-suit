import importlib
import os
import sys
import unittest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
from unittest.mock import patch


MODULE_NAME = "scripts.qqq_dt_agent"
CENTRAL_TZ = ZoneInfo("America/Chicago")


class QqqDayTradeAgentTests(unittest.TestCase):
    def _import_module(self):
        sys.modules.pop(MODULE_NAME, None)
        return importlib.import_module(MODULE_NAME)

    def test_build_data_client_uses_repo_alpaca_env_vars(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                with patch("alpaca.data.historical.StockHistoricalDataClient") as mock_client:
                    module = self._import_module()

                    module.build_data_client()

        mock_client.assert_called_with("alpaca-test", "secret-test")

    def test_build_data_client_raises_clear_error_when_alpaca_keys_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("dotenv.load_dotenv"):
                with patch("alpaca.data.historical.StockHistoricalDataClient"):
                    module = self._import_module()

                    with self.assertRaises(RuntimeError) as ctx:
                        module.build_data_client()

        self.assertIn("ALPACA_API_KEY", str(ctx.exception))
        self.assertIn("ALPACA_SECRET_KEY", str(ctx.exception))

    def test_build_buy_signal_series_matches_backtest_logic(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        frame = pd.DataFrame(
            {
                "MACDh_12_26_9": [-0.8, -0.4],
                "close": [100.2, 99.5],
                module.BOLLINGER_MIDDLE_COLUMN: [100.0, 100.0],
                "J": [20.0, 26.0],
                "RSI_14": [44.0, 43.0],
                "volume": [1_000_000, 1_500_000],
            },
            index=pd.date_range("2026-05-06 08:30:00", periods=2, freq="5min"),
        )

        signal_series = module.build_buy_signal_series(frame)

        self.assertFalse(bool(signal_series.iloc[0]))
        self.assertTrue(bool(signal_series.iloc[-1]))

    def test_determine_exit_reason_returns_take_profit_within_one_hour(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        entry_time = datetime(2026, 5, 6, 8, 45, tzinfo=CENTRAL_TZ)
        current_time = entry_time + timedelta(minutes=30)
        market_close = datetime(2026, 5, 6, 15, 0, tzinfo=CENTRAL_TZ)

        reason = module.determine_exit_reason(
            entry_price=100.0,
            current_price=120.0,
            entry_time=entry_time,
            current_time=current_time,
            market_close_time=market_close,
        )

        self.assertEqual(reason, module.EXIT_REASON_TAKE_PROFIT)

    def test_determine_exit_reason_returns_stop_loss(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        entry_time = datetime(2026, 5, 6, 8, 45, tzinfo=CENTRAL_TZ)
        current_time = entry_time + timedelta(minutes=10)
        market_close = datetime(2026, 5, 6, 15, 0, tzinfo=CENTRAL_TZ)

        reason = module.determine_exit_reason(
            entry_price=100.0,
            current_price=99.79,
            entry_time=entry_time,
            current_time=current_time,
            market_close_time=market_close,
        )

        self.assertEqual(reason, module.EXIT_REASON_STOP_LOSS)

    def test_determine_exit_reason_returns_max_hold_after_sixty_minutes(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        entry_time = datetime(2026, 5, 6, 8, 45, tzinfo=CENTRAL_TZ)
        current_time = entry_time + timedelta(minutes=60)
        market_close = datetime(2026, 5, 6, 15, 0, tzinfo=CENTRAL_TZ)

        reason = module.determine_exit_reason(
            entry_price=100.0,
            current_price=100.5,
            entry_time=entry_time,
            current_time=current_time,
            market_close_time=market_close,
        )

        self.assertEqual(reason, module.EXIT_REASON_MAX_HOLD)

    def test_determine_exit_reason_returns_market_close_within_five_minutes(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        entry_time = datetime(2026, 5, 6, 14, 30, tzinfo=CENTRAL_TZ)
        current_time = datetime(2026, 5, 6, 14, 56, tzinfo=CENTRAL_TZ)
        market_close = datetime(2026, 5, 6, 15, 0, tzinfo=CENTRAL_TZ)

        reason = module.determine_exit_reason(
            entry_price=100.0,
            current_price=100.1,
            entry_time=entry_time,
            current_time=current_time,
            market_close_time=market_close,
        )

        self.assertEqual(reason, module.EXIT_REASON_MARKET_CLOSE)


if __name__ == "__main__":
    unittest.main()