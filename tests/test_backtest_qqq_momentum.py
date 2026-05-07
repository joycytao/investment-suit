import importlib.util
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "backtest" / "backtest_qqq_momentum.py"


def load_module():
    spec = importlib.util.spec_from_file_location("backtest_qqq", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MomentumBreakoutBacktestTests(unittest.TestCase):
    def test_build_momentum_signal_series_requires_ema_vwap_and_orb_breakout(self):
        module = load_module()
        frame = pd.DataFrame(
            {
                "ema_9": [100.0, 100.4, 101.0],
                "ema_21": [99.8, 100.0, 100.3],
                "close": [100.1, 100.35, 100.6],
                "vwap": [100.0, 100.1, 100.3],
                "orb_high": [100.4, 100.4, 100.5],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=3, freq="5min"),
        )

        signal_series = module.build_momentum_signal_series(frame)

        self.assertEqual(signal_series.tolist(), [False, False, True])

    def test_simulate_momentum_trades_exits_on_ema_dead_cross(self):
        module = load_module()
        frame = pd.DataFrame(
            {
                "close": [99.5, 100.0, 101.2, 103.0, 102.0],
                "low": [99.4, 99.8, 101.0, 102.7, 101.8],
                "ema_9": [99.4, 100.1, 101.0, 100.8, 100.1],
                "ema_21": [99.6, 99.9, 100.4, 101.1, 100.6],
                "stop_loss_price": [98.0, 98.5, 99.0, 99.5, 99.5],
                "signal": [0, 1, 0, 0, 0],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=5, freq="5min"),
        )

        trades = module.simulate_momentum_trades(frame)

        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["exit_reason"], module.EXIT_REASON_EMA_DEAD_CROSS)
        self.assertEqual(trades.iloc[0]["entry_time"], frame.index[1])
        self.assertEqual(trades.iloc[0]["exit_time"], frame.index[3])
        self.assertAlmostEqual(trades.iloc[0]["ret"], 0.03, places=6)


if __name__ == "__main__":
    unittest.main()