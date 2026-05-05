import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pandas as pd

import scripts.trading_agent as trading_agent


class TradingAgentSniperTests(unittest.TestCase):
    def _build_bars_frame(self, symbol, closes, volumes=None):
        timestamps = pd.date_range("2026-05-04 08:30:00", periods=len(closes), freq="min")
        close_series = pd.Series(closes, index=timestamps, dtype=float)
        volume_series = pd.Series(volumes or [100_000] * len(closes), index=timestamps, dtype=float)

        frame = pd.DataFrame(
            {
                "open": close_series - 0.05,
                "high": close_series + 0.15,
                "low": close_series - 0.15,
                "close": close_series,
                "volume": volume_series,
            }
        )
        frame["symbol"] = symbol
        return frame.set_index("symbol", append=True).swaplevel(0, 1)

    def test_sniper_agent_submits_buy_when_price_breaks_vwap_and_ema20(self):
        symbol = "GOOD"
        bars_frame = self._build_bars_frame(symbol, [5 + (0.13 * index) for index in range(40)])
        mock_data_client = Mock()
        mock_data_client.get_stock_bars.return_value = SimpleNamespace(df=bars_frame)
        mock_trading_client = Mock()
        daily_profit_tracker = {"profit": 0}

        with patch.object(trading_agent, "data_client", mock_data_client):
            with patch.object(trading_agent, "trading_client", mock_trading_client):
                with patch("builtins.print"):
                    with patch(
                        "scripts.trading_agent.asyncio.sleep",
                        new=AsyncMock(side_effect=RuntimeError("stop loop")),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "stop loop"):
                            trading_agent.asyncio.run(
                                trading_agent.sniper_agent(symbol, daily_profit_tracker)
                            )

        self.assertEqual(mock_trading_client.submit_order.call_count, 1)
        buy_order = mock_trading_client.submit_order.call_args_list[0].args[0]
        self.assertEqual(buy_order.symbol, symbol)
        self.assertEqual(buy_order.qty, 100)
        self.assertEqual(str(buy_order.side), str(trading_agent.OrderSide.BUY))
        self.assertEqual(daily_profit_tracker["profit"], 0)

    def test_sniper_agent_sells_full_position_on_hard_stop(self):
        symbol = "STOP"
        entry_frame = self._build_bars_frame(symbol, [5 + (0.13 * index) for index in range(40)])
        stop_frame = self._build_bars_frame(symbol, [5.1 + (0.118 * index) for index in range(39)] + [9.2])
        mock_data_client = Mock()
        mock_data_client.get_stock_bars.side_effect = [
            SimpleNamespace(df=entry_frame),
            SimpleNamespace(df=stop_frame),
        ]
        mock_trading_client = Mock()
        daily_profit_tracker = {"profit": 0}

        with patch.object(trading_agent, "data_client", mock_data_client):
            with patch.object(trading_agent, "trading_client", mock_trading_client):
                with patch("builtins.print"):
                    with patch(
                        "scripts.trading_agent.asyncio.sleep",
                        new=AsyncMock(return_value=None),
                    ):
                        trading_agent.asyncio.run(
                            trading_agent.sniper_agent(symbol, daily_profit_tracker)
                        )

        self.assertEqual(mock_trading_client.submit_order.call_count, 2)
        buy_order = mock_trading_client.submit_order.call_args_list[0].args[0]
        sell_order = mock_trading_client.submit_order.call_args_list[1].args[0]
        self.assertEqual(str(buy_order.side), str(trading_agent.OrderSide.BUY))
        self.assertEqual(str(sell_order.side), str(trading_agent.OrderSide.SELL))
        self.assertEqual(sell_order.qty, 100)
        self.assertLess(daily_profit_tracker["profit"], 0)
        self.assertAlmostEqual(daily_profit_tracker["profit"], -87.0, places=2)

    def test_sniper_agent_takes_partial_profit_after_ten_percent_gain(self):
        symbol = "WIN"
        entry_frame = self._build_bars_frame(symbol, [5 + (0.13 * index) for index in range(40)])
        profit_frame = self._build_bars_frame(symbol, [5.5 + (0.145 * index) for index in range(39)] + [11.2])
        mock_data_client = Mock()
        mock_data_client.get_stock_bars.side_effect = [
            SimpleNamespace(df=entry_frame),
            SimpleNamespace(df=profit_frame),
        ]
        mock_trading_client = Mock()
        daily_profit_tracker = {"profit": 0}

        with patch.object(trading_agent, "data_client", mock_data_client):
            with patch.object(trading_agent, "trading_client", mock_trading_client):
                with patch("builtins.print"):
                    with patch(
                        "scripts.trading_agent.asyncio.sleep",
                        new=AsyncMock(side_effect=[None, RuntimeError("stop loop")]),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "stop loop"):
                            trading_agent.asyncio.run(
                                trading_agent.sniper_agent(symbol, daily_profit_tracker)
                            )

        self.assertEqual(mock_trading_client.submit_order.call_count, 2)
        buy_order = mock_trading_client.submit_order.call_args_list[0].args[0]
        partial_sell_order = mock_trading_client.submit_order.call_args_list[1].args[0]
        self.assertEqual(str(buy_order.side), str(trading_agent.OrderSide.BUY))
        self.assertEqual(str(partial_sell_order.side), str(trading_agent.OrderSide.SELL))
        self.assertEqual(partial_sell_order.qty, 50)
        self.assertAlmostEqual(daily_profit_tracker["profit"], 56.5, places=2)


if __name__ == "__main__":
    unittest.main()