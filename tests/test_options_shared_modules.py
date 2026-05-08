import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from backend import options_contract_selector as selector
from backend import options_execution_pricer as pricer


MARKET_TZ = ZoneInfo("America/New_York")


class OptionsContractSelectorTests(unittest.TestCase):
    def test_select_contract_filters_by_dte_delta_and_liquidity(self):
        signal_time = datetime(2026, 5, 8, 10, 0, tzinfo=MARKET_TZ)
        chain = pd.DataFrame(
            [
                {
                    "symbol": "QQQ_bad_dte",
                    "expiration_date": "2026-05-16",
                    "delta": 0.50,
                    "volume": 500,
                    "open_interest": 1000,
                    "bid_price": 1.90,
                    "ask_price": 2.00,
                },
                {
                    "symbol": "QQQ_bad_delta",
                    "expiration_date": "2026-05-12",
                    "delta": 0.22,
                    "volume": 500,
                    "open_interest": 1000,
                    "bid_price": 1.90,
                    "ask_price": 2.00,
                },
                {
                    "symbol": "QQQ_bad_spread",
                    "expiration_date": "2026-05-12",
                    "delta": 0.49,
                    "volume": 500,
                    "open_interest": 1000,
                    "bid_price": 1.50,
                    "ask_price": 1.80,
                },
                {
                    "symbol": "QQQ_good",
                    "expiration_date": "2026-05-12",
                    "delta": 0.49,
                    "volume": 500,
                    "open_interest": 1000,
                    "bid_price": 1.95,
                    "ask_price": 2.00,
                },
            ]
        )

        contract = selector.select_contract(
            chain=chain,
            signal_time=signal_time,
            option_side=1,
        )

        self.assertIsNotNone(contract)
        self.assertEqual(contract["symbol"], "QQQ_good")

    def test_select_contract_allows_zero_dte_and_ignores_missing_open_interest(self):
        signal_time = datetime(2026, 5, 8, 10, 0, tzinfo=MARKET_TZ)
        chain = pd.DataFrame(
            [
                {
                    "symbol": "QQQ_zero_dte_missing_oi",
                    "expiration_date": "2026-05-08",
                    "delta": 0.50,
                    "volume": 500,
                    "open_interest": 0,
                    "bid_price": 1.96,
                    "ask_price": 2.00,
                },
                {
                    "symbol": "QQQ_zero_dte_bad_spread",
                    "expiration_date": "2026-05-08",
                    "delta": 0.50,
                    "volume": 500,
                    "open_interest": 0,
                    "bid_price": 1.50,
                    "ask_price": 2.00,
                },
            ]
        )

        contract = selector.select_contract(
            chain=chain,
            signal_time=signal_time,
            option_side=1,
        )

        self.assertIsNotNone(contract)
        self.assertEqual(contract["symbol"], "QQQ_zero_dte_missing_oi")

    def test_select_contract_tie_breaks_by_delta_then_spread_then_volume(self):
        signal_time = datetime(2026, 5, 8, 10, 0, tzinfo=MARKET_TZ)
        chain = pd.DataFrame(
            [
                {
                    "symbol": "QQQ_wider_spread",
                    "expiration_date": "2026-05-12",
                    "delta": 0.50,
                    "volume": 900,
                    "open_interest": 1500,
                    "bid_price": 1.90,
                    "ask_price": 2.00,
                },
                {
                    "symbol": "QQQ_best",
                    "expiration_date": "2026-05-12",
                    "delta": 0.50,
                    "volume": 800,
                    "open_interest": 1500,
                    "bid_price": 1.94,
                    "ask_price": 2.00,
                },
                {
                    "symbol": "QQQ_more_volume_same_spread_lower_delta_fit",
                    "expiration_date": "2026-05-12",
                    "delta": 0.47,
                    "volume": 5000,
                    "open_interest": 3000,
                    "bid_price": 1.97,
                    "ask_price": 2.00,
                },
            ]
        )

        contract = selector.select_contract(
            chain=chain,
            signal_time=signal_time,
            option_side=1,
        )

        self.assertEqual(contract["symbol"], "QQQ_best")


class OptionsExecutionPricerTests(unittest.TestCase):
    def test_compute_entry_and_exit_prices_use_ask_and_bid(self):
        entry_quote = {"bid_price": 1.90, "ask_price": 2.10}
        exit_quote = {"bid_price": 2.40, "ask_price": 2.60}

        self.assertEqual(pricer.get_entry_price(entry_quote), 2.10)
        self.assertEqual(pricer.get_exit_price(exit_quote), 2.40)

    def test_missing_quote_after_fallback_returns_none(self):
        quotes = pd.DataFrame(
            {
                "bid_price": [None, None],
                "ask_price": [None, None],
            },
            index=pd.to_datetime([
                "2026-05-08 10:00:00",
                "2026-05-08 10:01:00",
            ]).tz_localize(MARKET_TZ),
        )

        quote = pricer.get_quote_with_fallback(
            quotes=quotes,
            timestamp=datetime(2026, 5, 8, 10, 0, tzinfo=MARKET_TZ),
        )

        self.assertIsNone(quote)


if __name__ == "__main__":
    unittest.main()