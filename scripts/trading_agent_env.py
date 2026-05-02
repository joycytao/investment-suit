import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


REQUIRED_ENV_VARS = ("FMP_API_KEY", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")


@dataclass(frozen=True)
class RuntimeConfig:
    fmp_api_key: str
    alpaca_api_key: str
    alpaca_secret_key: str


def _load_local_dotenv() -> None:
    dotenv_candidates = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ]
    loaded_paths = set()
    for dotenv_path in dotenv_candidates:
        resolved = dotenv_path.resolve()
        if resolved in loaded_paths or not resolved.is_file():
            continue
        load_dotenv(resolved, override=False)
        loaded_paths.add(resolved)


def load_runtime_config() -> RuntimeConfig:
    _load_local_dotenv()

    env_values = {name: (os.getenv(name) or "").strip() for name in REQUIRED_ENV_VARS}
    missing = [name for name, value in env_values.items() if not value]
    if missing:
        missing_names = ", ".join(missing)
        raise RuntimeError(
            "Missing required environment variables: "
            f"{missing_names}. Local runs load values from .env; GitHub Actions runs require matching repository secrets."
        )

    return RuntimeConfig(
        fmp_api_key=env_values["FMP_API_KEY"],
        alpaca_api_key=env_values["ALPACA_API_KEY"],
        alpaca_secret_key=env_values["ALPACA_SECRET_KEY"],
    )