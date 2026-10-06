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
    contact_discovery_provider: str = os.getenv("CONTACT_DISCOVERY_PROVIDER", "serpapi")
    contact_discovery_enabled: bool = os.getenv("CONTACT_DISCOVERY_ENABLED", "true").lower() == "true"
    contact_discovery_query_templates: str = os.getenv(
        "CONTACT_DISCOVERY_QUERY_TEMPLATES",
        "{company_name} Costa Rica contacto|{legal_name} correo teléfono|{tax_id} {company_name} Costa Rica|site:linkedin.com/company {company_name} Costa Rica|site:facebook.com {company_name} Costa Rica",
    )
    contact_discovery_max_queries: int = int(os.getenv("CONTACT_DISCOVERY_MAX_QUERIES", "5"))
    contact_discovery_max_results: int = int(os.getenv("CONTACT_DISCOVERY_MAX_RESULTS", "8"))
    contact_discovery_timeout_seconds: float = float(
        os.getenv("CONTACT_DISCOVERY_TIMEOUT_SECONDS", "120")
    )
    brave_search_api_key: str | None = os.getenv("BRAVE_SEARCH_API_KEY")
    brave_search_endpoint: str = os.getenv(
        "BRAVE_SEARCH_ENDPOINT",
        "https://api.search.brave.com/res/v1/web/search",
    )
    brave_search_country: str = os.getenv("BRAVE_SEARCH_COUNTRY", "CR")
    brave_search_language: str = os.getenv("BRAVE_SEARCH_LANGUAGE", "es")
    serper_api_key: str | None = os.getenv("SERPER_API_KEY")
    serper_search_endpoint: str = os.getenv(
        "SERPER_SEARCH_ENDPOINT",
        "https://google.serper.dev/search",
    )
    serper_country: str = os.getenv("SERPER_COUNTRY", "cr")
    serper_language: str = os.getenv("SERPER_LANGUAGE", "es")
    serpapi_api_key: str | None = os.getenv("SERPAPI_API_KEY")
    serpapi_search_endpoint: str = os.getenv(
        "SERPAPI_SEARCH_ENDPOINT",
        "https://serpapi.com/search.json",
    )
    serpapi_country: str = os.getenv("SERPAPI_COUNTRY", "cr")
    serpapi_language: str = os.getenv("SERPAPI_LANGUAGE", "es")


settings = Settings()
