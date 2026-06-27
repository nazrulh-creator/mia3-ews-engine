"""Central configuration for the MIA3 Early Warning Engine.

Settings come from environment variables (see .env.example). The most
consequential setting is MIA3_ENV, which selects the ringfenced LIVE or
TEST environment — each with its own database and audit chain.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RUNTIME_DIR = DATA_DIR / "runtime"
SYNTHETIC_DIR = DATA_DIR / "synthetic"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
# Uploaded model artifacts live under the data dir so they persist on the
# mounted volume (DATA_DIR is /app/data in the deployed TEST app).
MODELS_DIR = DATA_DIR / "models"

for _d in (RUNTIME_DIR, SYNTHETIC_DIR, ARTIFACTS_DIR, UPLOAD_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    """Resolved runtime settings. Constructed once via get_settings()."""

    def __init__(self) -> None:
        # Ringfence — TEST or LIVE. Anything that is not exactly "LIVE"
        # is treated as TEST, so LIVE is never reached by accident.
        raw_env = os.getenv("MIA3_ENV", "TEST").strip().upper()
        self.environment: str = "LIVE" if raw_env == "LIVE" else "TEST"
        self.is_live: bool = self.environment == "LIVE"

        default_db = f"sqlite:///{(RUNTIME_DIR / ('mia3_' + self.environment.lower() + '.db')).as_posix()}"
        self.database_url: str = os.getenv("MIA3_DATABASE_URL", default_db)

        self.secret_key: str = os.getenv("MIA3_SECRET_KEY", "dev-only-change-me")

        model_path = os.getenv("MIA3_MODEL_PATH", "").strip()
        self.model_path: Optional[Path] = Path(model_path) if model_path else None

        # Claude-written narrative is OFF by default and force-disabled on LIVE.
        self.enable_llm_narrative: bool = (
            _bool(os.getenv("MIA3_ENABLE_LLM_NARRATIVE"), False) and not self.is_live
        )

        # Team ownership marks (the app carries SDA marks, never CGC branding).
        self.owner_team: str = "Strategic Data Analytics"
        self.owner_short: str = "SDA"
        self.app_name: str = "MIA3 Early Warning Engine"

    # --- UI ringfence cues -------------------------------------------------
    @property
    def banner_color(self) -> str:
        # On-brand environment cue: CGC Blue for LIVE, CGC Orange for TEST.
        return "#003A70" if self.is_live else "#FF8819"

    @property
    def env_watermark(self) -> Optional[str]:
        return None if self.is_live else "TEST — NOT LIVE DATA"

    @property
    def id_prefix(self) -> str:
        """Run/record id prefix; TEST records are visibly tagged."""
        return "" if self.is_live else "TEST-"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
