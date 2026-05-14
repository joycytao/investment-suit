import importlib.util
import unittest
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "trade_option-sell_put.py"
)


class TradeOptionSellPutImportTests(unittest.TestCase):
    def test_script_module_imports_with_installed_alpaca_version(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        self.assertTrue(callable(module.main))

    def test_monitor_retries_after_positions_timeout(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        option_position = SimpleNamespace(
            asset_class="us_option",
            symbol="SPY260619P00500000",
            underlying_symbol="SPY",
            unrealized_plpc="0.10",
            asset_id="asset-1",
        )
        mock_client = Mock()
        mock_client.get_all_positions.side_effect = [
            requests.exceptions.ConnectTimeout("positions timeout"),
            [option_position],
        ]
        mock_client.get_account.return_value = SimpleNamespace(account_number="paper-123")

        with patch.object(module, "get_trading_client", return_value=mock_client):
            result = module.run_monitor_and_check_risk()

        self.assertEqual(result, 1)
        self.assertEqual(mock_client.get_all_positions.call_count, 2)

    def test_monitor_counts_option_position_without_underlying_symbol_attribute(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        option_position = SimpleNamespace(
            asset_class="us_option",
            symbol="SPY260619P00500000",
            unrealized_plpc="0.10",
            asset_id="asset-1",
        )
        mock_client = Mock()
        mock_client.get_all_positions.return_value = [option_position]
        mock_client.get_account.return_value = SimpleNamespace(account_number="paper-123")

        with patch.object(module, "get_trading_client", return_value=mock_client):
            result = module.run_monitor_and_check_risk()

        self.assertEqual(result, 1)

    def test_get_sp100_tickers_wraps_html_in_string_io(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        html_response = SimpleNamespace(text="<html></html>", status_code=200)
        ticker_table = module.pd.DataFrame({"Symbol": ["MSFT", "AAPL"]})
        captured_source = None

        def fake_read_html(source, **_kwargs):
            nonlocal captured_source
            captured_source = source
            return [None, None, ticker_table]

        with patch.object(module.requests, "get", return_value=html_response):
            with patch.object(module.pd, "read_html", side_effect=fake_read_html):
                tickers = module.get_sp100_tickers()

        self.assertEqual(tickers, ["MSFT", "AAPL"])
        self.assertIsInstance(captured_source, StringIO)

    def test_get_sp100_tickers_uses_request_timeout(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        html_response = SimpleNamespace(text="<html></html>", status_code=200)
        ticker_table = module.pd.DataFrame({"Symbol": ["MSFT", "AAPL"]})

        with patch.object(module.requests, "get", return_value=html_response) as mock_get:
            with patch.object(module.pd, "read_html", return_value=[None, None, ticker_table]):
                module.get_sp100_tickers()

        self.assertEqual(mock_get.call_args.kwargs["timeout"], 10)

    def test_get_sp100_tickers_forces_lxml_parser(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        html_response = SimpleNamespace(text="<html></html>", status_code=200)
        ticker_table = module.pd.DataFrame({"Symbol": ["MSFT", "AAPL"]})

        with patch.object(module.requests, "get", return_value=html_response):
            with patch.object(module.pd, "read_html", return_value=[None, None, ticker_table]) as mock_read_html:
                module.get_sp100_tickers()

        self.assertEqual(mock_read_html.call_args.kwargs["flavor"], "lxml")

    def test_is_earnings_approaching_returns_false_when_lookup_degrades(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        with patch.object(module, "get_earnings_calendar", return_value=None):
            self.assertFalse(module.is_earnings_approaching("SPY"))

    def test_main_logs_candidate_fetch_boundaries(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        with patch.object(module, "get_stock_client", return_value=Mock()):
            with patch.object(module, "run_monitor_and_check_risk", return_value=1):
                with patch.object(module, "get_sp100_tickers", return_value=["MSFT", "AAPL"]):
                    with patch.object(module, "is_earnings_approaching", return_value=True):
                        with patch("builtins.print") as mock_print:
                            module.main()

        printed_lines = [" ".join(str(arg) for arg in call.args) for call in mock_print.call_args_list]
        self.assertIn("開始抓候選清單...", printed_lines)
        self.assertIn("候選清單數量: 2", printed_lines)

    def test_find_and_trade_put_uses_singular_snapshot_api(self):
        spec = importlib.util.spec_from_file_location(
            "trade_option_sell_put",
            MODULE_PATH,
        )
        module = importlib.util.module_from_spec(spec)

        assert spec.loader is not None
        spec.loader.exec_module(module)

        option_client = Mock()
        option_client.get_option_chain.return_value = {
            "T260618P00020000": object(),
            "T260618P00021000": object(),
        }
        option_client.get_option_snapshot.return_value = {
            "T260618P00020000": SimpleNamespace(greeks=SimpleNamespace(delta=-0.18)),
            "T260618P00021000": SimpleNamespace(greeks=SimpleNamespace(delta=-0.16)),
        }
        trading_client = Mock()

        with patch.object(module, "get_option_client", return_value=option_client):
            with patch.object(module, "get_trading_client", return_value=trading_client):
                with patch("builtins.print"):
                    module.find_and_trade_put("T")

        option_client.get_option_snapshot.assert_called_once()
        trading_client.submit_order.assert_called_once()
        submitted_order = trading_client.submit_order.call_args.args[0]
        self.assertEqual(submitted_order.symbol, "T260618P00020000")


if __name__ == "__main__":
    unittest.main()