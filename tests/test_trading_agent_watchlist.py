import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
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

    def test_validate_news_with_ai_aggregates_recent_headlines(self):
        news_items = [
            SimpleNamespace(
                created_at="2026-05-04T08:35:00Z",
                headline="FDA approval secured",
                summary="Company secured a major approval.",
            ),
            SimpleNamespace(
                created_at="2026-05-04T08:36:00Z",
                headline="No dilution mentioned",
                summary="Balance sheet remains unchanged.",
            ),
        ]
        mock_client = Mock()
        mock_client.get_news.return_value = SimpleNamespace(news=news_items)

        with patch("scripts.trading_agent.NewsRequest", return_value="request") as mock_request:
            with patch("scripts.trading_agent.news_client", mock_client, create=True):
                with patch(
                    "scripts.trading_agent.ask_ai_sentiment",
                    new=AsyncMock(return_value="[YES] Reason: strong catalyst."),
                ) as mock_ask_ai_sentiment:
                    result = trading_agent.asyncio.run(trading_agent.validate_news_with_ai("GOOD"))

        self.assertTrue(result)
        mock_request.assert_called_once_with(symbols="GOOD", limit=5)
        aggregated_news = mock_ask_ai_sentiment.await_args.args[1]
        self.assertIn("FDA approval secured", aggregated_news)
        self.assertIn("No dilution mentioned", aggregated_news)

    def test_validate_news_with_ai_rejects_symbol_when_news_lookup_fails(self):
        mock_client = Mock()
        mock_client.get_news.side_effect = RuntimeError("news unavailable")

        with patch("scripts.trading_agent.NewsRequest", return_value="request"):
            with patch("scripts.trading_agent.news_client", mock_client, create=True):
                result = trading_agent.asyncio.run(trading_agent.validate_news_with_ai("GOOD"))

        self.assertFalse(result)

    def test_validate_news_with_ai_rejects_symbol_when_ai_cannot_evaluate(self):
        news_items = [
            SimpleNamespace(
                created_at="2026-05-04T08:35:00Z",
                headline="Catalyst pending confirmation",
                summary="Headline exists but AI evaluation is unavailable.",
            )
        ]
        mock_client = Mock()
        mock_client.get_news.return_value = SimpleNamespace(news=news_items)

        with patch("scripts.trading_agent.NewsRequest", return_value="request"):
            with patch("scripts.trading_agent.news_client", mock_client, create=True):
                with patch(
                    "scripts.trading_agent.ask_ai_sentiment",
                    new=AsyncMock(return_value=None),
                ):
                    result = trading_agent.asyncio.run(trading_agent.validate_news_with_ai("GOOD"))

        self.assertFalse(result)

    def test_validate_news_with_ai_requires_explicit_yes_verdict(self):
        news_items = [
            SimpleNamespace(
                created_at="2026-05-04T08:35:00Z",
                headline="Speculative partnership rumor",
                summary="No formal catalyst was announced.",
            )
        ]
        mock_client = Mock()
        mock_client.get_news.return_value = SimpleNamespace(news=news_items)

        with patch("scripts.trading_agent.NewsRequest", return_value="request"):
            with patch("scripts.trading_agent.news_client", mock_client, create=True):
                with patch(
                    "scripts.trading_agent.ask_ai_sentiment",
                    new=AsyncMock(return_value="[NO] Reason: yes, the headline sounds positive, but the news is not actionable."),
                ):
                    result = trading_agent.asyncio.run(trading_agent.validate_news_with_ai("RISKY"))

        self.assertFalse(result)

    def test_filter_watchlist_by_news_keeps_order_without_mutating_input(self):
        watchlist = ["BAD1", "BAD2", "GOOD"]

        with patch(
            "scripts.trading_agent.validate_news_with_ai",
            new=AsyncMock(side_effect=[False, False, True]),
        ):
            filtered_watchlist = trading_agent.asyncio.run(
                trading_agent.filter_watchlist_by_news(watchlist)
            )

        self.assertEqual(filtered_watchlist, ["GOOD"])
        self.assertEqual(watchlist, ["BAD1", "BAD2", "GOOD"])

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