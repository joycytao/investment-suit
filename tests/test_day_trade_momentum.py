import importlib
import os
import sys
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from zoneinfo import ZoneInfo

import pandas as pd


MODULE_NAME = "scripts.day_trade_momentum"
CENTRAL_TZ = ZoneInfo("America/Chicago")


class DayTradeMomentumTests(unittest.TestCase):
    def _import_module(self):
        sys.modules.pop(MODULE_NAME, None)
        return importlib.import_module(MODULE_NAME)

    def _build_bars_frame(self, symbol, closes, volumes=None):
        timestamps = pd.date_range("2026-05-06 13:30:00", periods=len(closes), freq="min", tz="UTC")
        close_series = pd.Series(closes, index=timestamps, dtype=float)
        volume_series = pd.Series(volumes or [1_000_000] * len(closes), index=timestamps, dtype=float)
        frame = pd.DataFrame(
            {
                "open": close_series - 0.1,
                "high": close_series + 0.2,
                "low": close_series - 0.2,
                "close": close_series,
                "volume": volume_series,
            }
        )
        frame["symbol"] = symbol
        return frame.set_index("symbol", append=True).swaplevel(0, 1)

    def test_get_runtime_symbol_reads_symbol_env_var(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
                "SYMBOL": "SPY",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()
                self.assertEqual(module.get_runtime_symbol(), "SPY")

    def test_determine_exit_reason_returns_ema_dead_cross(self):
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

        latest_bar_time = datetime(2026, 5, 6, 10, 25, tzinfo=CENTRAL_TZ)
        market_close = datetime(2026, 5, 6, 15, 0, tzinfo=CENTRAL_TZ)

        reason = module.determine_exit_reason(
            position=module.PositionState(
                entry_price=100.0,
                qty=100,
                entry_time=datetime(2026, 5, 6, 10, 5, tzinfo=CENTRAL_TZ),
                stop_loss_price=98.5,
            ),
            current_bar=pd.Series({"low": 99.8, "close": 101.2, "ema_9": 100.1, "ema_21": 100.4}),
            current_time=latest_bar_time,
            market_close_time=market_close,
        )

        self.assertEqual(reason, module.EXIT_REASON_EMA_DEAD_CROSS)

    def test_momentum_agent_submits_buy_for_matrix_symbol(self):
        symbol = "SPY"
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
                "SYMBOL": symbol,
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                module = self._import_module()

        entry_frame = self._build_bars_frame(symbol, [100 + (0.12 * index) for index in range(60)])
        mock_data_client = Mock()
        mock_data_client.get_stock_bars.return_value = SimpleNamespace(df=entry_frame)
        mock_trading_client = Mock()

        indicator_frame = pd.DataFrame(
            {
                "close": [100.0, 100.4],
                "low": [99.8, 100.2],
                "ema_9": [100.1, 100.6],
                "ema_21": [99.9, 100.2],
                "vwap": [99.9, 100.3],
                "orb_high": [100.2, 100.3],
                "stop_loss_price": [98.5, 98.9],
            },
            index=pd.date_range("2026-05-06 10:00:00", periods=2, freq="5min", tz=CENTRAL_TZ),
        )

        with patch.object(module, "data_client", mock_data_client):
            with patch.object(module, "trading_client", mock_trading_client):
                with patch.object(module, "fetch_signal_frame", return_value=indicator_frame):
                    with patch.object(module, "build_momentum_signal_series", return_value=pd.Series([False, True], index=indicator_frame.index)):
                        with patch.object(module, "get_current_central_time", return_value=datetime(2026, 5, 6, 10, 5, tzinfo=CENTRAL_TZ)):
                            with patch("builtins.print"):
                                with patch(
                                    "scripts.day_trade_momentum.asyncio.sleep",
                                    new=AsyncMock(side_effect=RuntimeError("stop loop")),
                                ):
                                    with self.assertRaisesRegex(RuntimeError, "stop loop"):
                                        module.asyncio.run(module.day_trade_momentum_agent(symbol=symbol))

        self.assertEqual(mock_trading_client.submit_order.call_count, 1)
        buy_order = mock_trading_client.submit_order.call_args_list[0].args[0]
        self.assertEqual(buy_order.symbol, symbol)
        self.assertEqual(str(buy_order.side), str(module.OrderSide.BUY))


if __name__ == "__main__":
    unittest.main()