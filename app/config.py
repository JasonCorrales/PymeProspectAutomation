from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


load_dotenv(dotenv_path=Path.cwd() / ".env")


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://pyme:pyme_dev_password@localhost:5432/pyme_prospects",
    )
    app_title: str = os.getenv("APP_TITLE", "Costa Rica PYME Prospect Automation")


settings = Settings()
