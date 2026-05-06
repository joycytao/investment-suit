import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo
import os

import scripts.trading_agent as trading_agent


class TradingAgentWatchlistTests(unittest.TestCase):
    @patch("scripts.trading_agent.get_finviz_candidates")
    def test_filters_candidates_by_query_and_returns_matching_symbols(self, mock_candidates):
        mock_candidates.return_value = [
            {
                "symbol": "GOOD",
                "price": 12.4,
                "volume": 2_500_000,
                "changePercentage": 14.2,
            },
            {
                "symbol": "LOWPRICE",
                "price": 2.75,
                "volume": 4_000_000,
                "changePercentage": 11.0,
            },
            {
                "symbol": "HIGHCHANGE",
                "price": 9.1,
                "volume": 2_200_000,
                "changePercentage": 24.0,
            },
        ]

        watchlist = trading_agent.get_fmp_watchlist()

        self.assertEqual(watchlist, ["GOOD"])

    def test_builds_execution_window_in_central_time(self):
        utc_now = datetime(2026, 5, 4, 13, 30, tzinfo=ZoneInfo("UTC"))

        with patch.dict(os.environ, {}, clear=True):
            market_open, market_close = trading_agent.get_execution_window(utc_now)

        self.assertEqual(market_open.hour, 8)
        self.assertEqual(market_open.minute, 30)
        self.assertEqual(market_close.hour, 9)
        self.assertEqual(market_close.minute, 30)
        self.assertEqual(str(market_open.tzinfo), "America/Chicago")
        self.assertEqual(str(market_close.tzinfo), "America/Chicago")

    def test_builds_execution_window_with_env_duration_override(self):
        utc_now = datetime(2026, 5, 4, 13, 30, tzinfo=ZoneInfo("UTC"))

        with patch.dict(os.environ, {"EXECUTION_DURATION_MINUTES": "180"}, clear=False):
            market_open, market_close = trading_agent.get_execution_window(utc_now)

        self.assertEqual(market_open.hour, 8)
        self.assertEqual(market_open.minute, 30)
        self.assertEqual(market_close.hour, 11)
        self.assertEqual(market_close.minute, 30)

    @patch("scripts.trading_agent.bootstrap_runtime")
    @patch("scripts.trading_agent.get_current_central_time")
    def test_main_prints_outside_execution_time_after_market_close(self, mock_now, mock_bootstrap):
        mock_now.return_value = datetime(2026, 5, 4, 9, 31, tzinfo=ZoneInfo("America/Chicago"))

        with patch.dict(os.environ, {}, clear=True):
            with patch("builtins.print") as mock_print:
                trading_agent.asyncio.run(trading_agent.main())

        mock_bootstrap.assert_called_once()
        mock_print.assert_any_call(
            "⏰ Outside execution time. Current time 09:31 AM America/Chicago is outside the 08:30 AM-09:30 AM America/Chicago trading window."
        )


if __name__ == "__main__":
    unittest.main()