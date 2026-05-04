import unittest
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()