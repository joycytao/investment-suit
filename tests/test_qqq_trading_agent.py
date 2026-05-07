import importlib
import os
import sys
import unittest
import pandas as pd
from unittest.mock import Mock, patch


MODULE_NAME = "scripts.qqq_trading_agent"


class QqqTradingAgentTests(unittest.TestCase):
    def _import_module(self):
        sys.modules.pop(MODULE_NAME, None)
        return importlib.import_module(MODULE_NAME)

    def test_build_data_client_uses_repo_alpaca_env_vars(self):
        with patch.dict(
            os.environ,
            {
                "ALPACA_API_KEY": "alpaca-test",
                "ALPACA_SECRET_KEY": "secret-test",
            },
            clear=True,
        ):
            with patch("dotenv.load_dotenv"):
                with patch("alpaca.data.historical.StockHistoricalDataClient") as mock_client:
                    module = self._import_module()

                    module.build_data_client()

        mock_client.assert_called_with("alpaca-test", "secret-test")

    def test_build_data_client_raises_clear_error_when_alpaca_keys_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("dotenv.load_dotenv"):
                with patch("alpaca.data.historical.StockHistoricalDataClient"):
                    module = self._import_module()

                    with self.assertRaises(RuntimeError) as ctx:
                        module.build_data_client()

        self.assertIn("ALPACA_API_KEY", str(ctx.exception))
        self.assertIn("ALPACA_SECRET_KEY", str(ctx.exception))

    def test_run_qqq_backtest_uses_symbol_or_symbols_request_field(self):
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

        mock_client = Mock()
        mock_client.get_stock_bars.side_effect = RuntimeError("stop after request")

        with patch.object(module, "build_data_client", return_value=mock_client):
            with patch.object(module, "StockBarsRequest") as mock_request:
                with self.assertRaisesRegex(RuntimeError, "stop after request"):
                    module.run_qqq_backtest()

        self.assertEqual(mock_request.call_args.kwargs["symbol_or_symbols"], ["QQQ"])

    def test_add_indicators_populates_explicit_20_period_bollinger_column(self):
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

        index = pd.date_range("2026-05-01 09:30:00", periods=40, freq="5min")
        df = pd.DataFrame(
            {
                "open": [100 + i * 0.1 for i in range(40)],
                "high": [101 + i * 0.1 for i in range(40)],
                "low": [99 + i * 0.1 for i in range(40)],
                "close": [100 + i * 0.1 for i in range(40)],
                "volume": [1_000_000 + i * 1_000 for i in range(40)],
            },
            index=index,
        )

        result = module.add_indicators(df)

        self.assertIn("BBL_20_2.0_2.0", result.columns)
        self.assertIn("BBM_20_2.0_2.0", result.columns)

    def test_uses_explicit_20_period_bollinger_middle_column_name(self):
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

        self.assertEqual(module.BOLLINGER_MIDDLE_COLUMN, "BBM_20_2.0_2.0")


if __name__ == "__main__":
    unittest.main()