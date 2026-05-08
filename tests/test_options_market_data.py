from types import SimpleNamespace
import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from backend import options_market_data as market_data


MARKET_TZ = ZoneInfo("America/New_York")


class OptionsMarketDataTests(unittest.TestCase):
    def test_normalize_option_chain_snapshot_flattens_snapshot_objects(self):
        snapshots = {
            "QQQ260512C00512000": SimpleNamespace(
                greeks=SimpleNamespace(delta=0.51),
                latest_quote=SimpleNamespace(bid_price=2.00, ask_price=2.08),
                latest_trade=SimpleNamespace(price=2.04, size=120, timestamp=None),
                open_interest=1800,
                implied_volatility=0.24,
            )
        }

        frame = market_data.normalize_option_chain_snapshot(
            snapshots=snapshots,
            signal_time=datetime(2026, 5, 8, 10, 0, tzinfo=MARKET_TZ),
        )

        self.assertEqual(frame.iloc[0]["symbol"], "QQQ260512C00512000")
        self.assertEqual(frame.iloc[0]["delta"], 0.51)
        self.assertEqual(frame.iloc[0]["bid_price"], 2.00)
        self.assertEqual(frame.iloc[0]["ask_price"], 2.08)
        self.assertEqual(frame.iloc[0]["volume"], 120)
        self.assertEqual(frame.iloc[0]["open_interest"], 1800)

    def test_build_exit_bid_price_from_bar_close_and_spread_proxy(self):
        exit_bid = market_data.derive_exit_bid_price(option_close=2.50, spread_pct=0.08)

        self.assertAlmostEqual(exit_bid, 2.40, places=6)


if __name__ == "__main__":
    unittest.main()