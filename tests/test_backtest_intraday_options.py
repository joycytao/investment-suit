import importlib.util
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backtest" / "backtest_intraday_options.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backtest_intraday_options", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class IntradayOptionsBacktestTests(unittest.TestCase):
    def test_build_entry_signal_series_uses_opening_range_and_swing_breakout_layers(self):
        module = load_module()
        index = pd.to_datetime(
            [
                "2026-05-06 09:55:00",
                "2026-05-06 09:56:00",
            ]
        ).tz_localize(module.MARKET_TIMEZONE)
        frame = pd.DataFrame(
            {
                "entry_window_open": [True, True],
                "liquidity_ok": [True, True],
                "volume_breakout_up": [True, True],
                "volume_breakout_down": [False, False],
                "breaks_opening_range_high": [True, True],
                "breaks_opening_range_low": [False, False],
                "breaks_swing_high": [False, True],
                "breaks_swing_low": [False, False],
                "ma_trend_bull": [True, True],
                "ma_trend_bear": [False, False],
                "macd_bull_bias": [True, True],
                "macd_bear_bias": [False, False],
                "rsi_bull_filter_ok": [True, True],
                "rsi_bear_filter_ok": [False, False],
            },
            index=index,
        )

        signal_series = module.build_entry_signal_series(frame)

        self.assertEqual(signal_series.tolist(), [0, 1])

    def test_build_entry_signal_series_allows_trend_bias_not_just_fresh_cross(self):
        module = load_module()
        index = pd.to_datetime(
            [
                "2026-05-06 10:00:00",
            ]
        ).tz_localize(module.MARKET_TIMEZONE)
        frame = pd.DataFrame(
            {
                "entry_window_open": [True],
                "liquidity_ok": [True],
                "volume_breakout_up": [True],
                "volume_breakout_down": [False],
                "breaks_opening_range_high": [True],
                "breaks_opening_range_low": [False],
                "breaks_swing_high": [True],
                "breaks_swing_low": [False],
                "ma_trend_bull": [True],
                "ma_trend_bear": [False],
                "macd_bull_bias": [True],
                "macd_bear_bias": [False],
                "rsi_bull_filter_ok": [True],
                "rsi_bear_filter_ok": [False],
            },
            index=index,
        )

        signal_series = module.build_entry_signal_series(frame)

        self.assertEqual(signal_series.tolist(), [1])

    def test_build_entry_signal_series_uses_rsi_as_filter_not_direction_driver(self):
        module = load_module()
        index = pd.to_datetime([
            "2026-05-06 10:01:00",
            "2026-05-06 10:02:00",
        ]).tz_localize(module.MARKET_TIMEZONE)
        frame = pd.DataFrame(
            {
                "entry_window_open": [True, True],
                "liquidity_ok": [True, True],
                "volume_breakout_up": [True, True],
                "volume_breakout_down": [False, False],
                "breaks_opening_range_high": [True, True],
                "breaks_opening_range_low": [False, False],
                "breaks_swing_high": [True, True],
                "breaks_swing_low": [False, False],
                "ma_trend_bull": [True, True],
                "ma_trend_bear": [False, False],
                "macd_bull_bias": [True, True],
                "macd_bear_bias": [False, False],
                "rsi_bull_filter_ok": [False, True],
                "rsi_bear_filter_ok": [False, False],
            },
            index=index,
        )

        signal_series = module.build_entry_signal_series(frame)

        self.assertEqual(signal_series.tolist(), [0, 1])

    def test_simulate_option_trades_scales_out_then_hits_full_target(self):
        module = load_module()
        frame = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.5],
                "ema_20_1m": [99.7, 100.3, 101.1],
                "bb_upper_5m": [103.0, 103.5, 104.0],
                "bb_lower_5m": [98.0, 98.0, 98.0],
                "option_price": [2.00, 2.70, 3.10],
                "signal": [1, 0, 0],
                "signal_side": [1, 0, 0],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=3, freq="min", tz=module.MARKET_TIMEZONE),
        )

        trades = module.simulate_option_trades(frame, starting_capital=10_000)

        self.assertEqual(len(trades), 1)
        self.assertAlmostEqual(trades.iloc[0]["realized_return"], 0.425, places=6)
        self.assertEqual(trades.iloc[0]["partials_taken"], 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], module.EXIT_REASON_FULL_TARGET)

    def test_simulate_option_trades_uses_entry_ask_and_exit_bid_quotes(self):
        module = load_module()
        frame = pd.DataFrame(
            {
                "close": [100.0, 101.0, 102.5],
                "ema_20_1m": [99.7, 100.3, 101.1],
                "bb_upper_5m": [103.0, 103.5, 104.0],
                "bb_lower_5m": [98.0, 98.0, 98.0],
                "entry_ask": [2.00, None, None],
                "exit_bid": [None, 2.70, 3.10],
                "signal": [1, 0, 0],
                "signal_side": [1, 0, 0],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=3, freq="min", tz=module.MARKET_TIMEZONE),
        )

        trades = module.simulate_option_trades(frame, starting_capital=10_000)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["entry_option_price"], 2.00)
        self.assertEqual(trades.iloc[0]["exit_option_price"], 3.10)

    def test_simulate_option_trades_skips_trade_when_quote_data_missing(self):
        module = load_module()
        frame = pd.DataFrame(
            {
                "close": [100.0, 101.0],
                "ema_20_1m": [99.7, 100.3],
                "bb_upper_5m": [103.0, 103.5],
                "bb_lower_5m": [98.0, 98.0],
                "entry_ask": [None, None],
                "exit_bid": [None, None],
                "signal": [1, 0],
                "signal_side": [1, 0],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=2, freq="min", tz=module.MARKET_TIMEZONE),
        )

        trades = module.simulate_option_trades(frame, starting_capital=10_000)

        self.assertTrue(trades.empty)


if __name__ == "__main__":
    unittest.main()