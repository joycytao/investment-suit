import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.trading_agent_env import load_runtime_config


class TradingAgentEnvTests(unittest.TestCase):
    def test_loads_required_keys_from_dotenv(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            env_path = Path(temp_dir) / ".env"
            env_path.write_text(
                "FMP_API_KEY=fmp-test\n"
                "ALPACA_API_KEY=alpaca-test\n"
                "ALPACA_SECRET_KEY=secret-test\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {}, clear=True):
                with patch("os.getcwd", return_value=temp_dir):
                    config = load_runtime_config()

        self.assertEqual(config.fmp_api_key, "fmp-test")
        self.assertEqual(config.alpaca_api_key, "alpaca-test")
        self.assertEqual(config.alpaca_secret_key, "secret-test")

    def test_raises_clear_error_when_required_keys_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {}, clear=True):
                with patch("scripts.trading_agent_env._load_local_dotenv"):
                    with self.assertRaises(RuntimeError) as ctx:
                        load_runtime_config()

        self.assertIn("Missing required environment variables", str(ctx.exception))
        self.assertIn("FMP_API_KEY", str(ctx.exception))
        self.assertIn("ALPACA_API_KEY", str(ctx.exception))
        self.assertIn("ALPACA_SECRET_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()