import importlib
import os
import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pandas as pd


MODULE_NAME = "scripts.day_trade_options"
MARKET_TZ = ZoneInfo("America/New_York")


class DayTradeOptionsTests(unittest.TestCase):
    def _import_module(self):
        sys.modules.pop(MODULE_NAME, None)
        return importlib.import_module(MODULE_NAME)

    def test_get_runtime_symbol_reads_symbol_env_var(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
                "SYMBOL": "NVDA",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()
                self.assertEqual(module.get_runtime_symbol(), "NVDA")

    def test_build_option_trade_plan_formats_occ_symbol(self):
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

        trade_plan = module.build_option_trade_plan(
            symbol="QQQ",
            signal_side=1,
            spot_price=512.4,
            option_price=2.35,
            current_time=datetime(2026, 5, 6, 10, 5, tzinfo=MARKET_TZ),
            buying_power=25_000,
        )

        self.assertEqual(trade_plan.side, 1)
        self.assertEqual(trade_plan.contract_type, "call")
        self.assertEqual(trade_plan.expiry.strftime("%Y-%m-%d"), "2026-05-08")
        self.assertEqual(trade_plan.contract_symbol, "QQQ260508C00512000")
        self.assertGreaterEqual(trade_plan.contracts, 1)

    def test_determine_exit_reason_returns_full_target(self):
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

        reason = module.determine_exit_reason(
            position=module.OptionPositionState(
                symbol="QQQ",
                side=1,
                contracts=8,
                entry_time=datetime(2026, 5, 6, 10, 0, tzinfo=MARKET_TZ),
                entry_spot=510.0,
                entry_option_price=2.0,
                strike=512,
                expiry=datetime(2026, 5, 8, 16, 0, tzinfo=MARKET_TZ),
                contract_symbol="QQQ260508C00512000",
                partial_exit_taken=False,
            ),
            current_bar={
                "close": 513.8,
                "ema_20_1m": 512.1,
                "bb_upper_5m": 515.0,
                "bb_lower_5m": 508.0,
                "option_price": 3.1,
            },
            current_time=datetime(2026, 5, 6, 10, 12, tzinfo=MARKET_TZ),
        )

        self.assertEqual(reason, module.EXIT_REASON_FULL_TARGET)

    def test_select_trade_plan_from_chain_uses_shared_selector(self):
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

        chain = pd.DataFrame(
            [
                {
                    "symbol": "QQQ260512C00512000",
                    "expiration_date": "2026-05-12",
                    "delta": 0.49,
                    "volume": 300,
                    "open_interest": 900,
                    "bid_price": 2.00,
                    "ask_price": 2.06,
                }
            ]
        )

        trade_plan = module.select_trade_plan_from_chain(
            symbol="QQQ",
            signal_side=1,
            spot_price=512.4,
            current_time=datetime(2026, 5, 8, 10, 5, tzinfo=MARKET_TZ),
            buying_power=25_000,
            chain=chain,
        )

        self.assertIsNotNone(trade_plan)
        self.assertEqual(trade_plan.contract_symbol, "QQQ260512C00512000")


if __name__ == "__main__":
    unittest.main()