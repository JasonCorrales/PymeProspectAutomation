from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Company, CompanyContactDiscoveryResult, ContactMethodType, DiscoveryResultStatus


EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\(?506\)?[\s.-]?)?(?:\d[\s.-]?){8}(?!\d)")
CONTACT_FIELD_KEYS = {"email", "correo", "correo_electronico", "correo_electrónico", "phone", "telefono", "teléfono"}
TITLE_FIELD_KEYS = ("title", "name", "nombre")
URL_FIELD_KEYS = ("link", "url", "website", "sitio_web", "sitio web")
SOCIAL_HOST_TYPES = {
    "linkedin.com": ContactMethodType.linkedin,
    "facebook.com": ContactMethodType.facebook,
    "instagram.com": ContactMethodType.instagram,
}


@dataclass(frozen=True)
class SearchResult:
    query: str
    title: str | None
    url: str | None
    snippet: str | None


@dataclass(frozen=True)
class ContactCandidate:
    provider: str
    query: str
    source_title: str | None
    source_url: str | None
    snippet: str | None
    candidate_name: str | None
    contact_medium: str
    contact_type: ContactMethodType
    confidence: str


class ContactDiscoveryProvider(Protocol):
    name: str

    def search(self, queries: list[str]) -> list[SearchResult]:
        """Return bounded web search results for the supplied queries."""


class ContactDiscoveryConfigError(RuntimeError):
    pass


class ContactDiscoveryRuntimeError(RuntimeError):
    pass


class BraveSearchProvider:
    name = "brave"

    def search(self, queries: list[str]) -> list[SearchResult]:
        if not settings.brave_search_api_key:
            raise ContactDiscoveryConfigError(
                "Configurá BRAVE_SEARCH_API_KEY para habilitar la búsqueda automática."
            )

        results: list[SearchResult] = []
        count_per_query = max(1, settings.contact_discovery_max_results)
        for query in queries:
            params = urlencode(
                {
                    "q": query,
                    "count": count_per_query,
                    "country": settings.brave_search_country,
                    "search_lang": settings.brave_search_language,
                    "safesearch": "moderate",
                }
            )
            request = Request(
                f"{settings.brave_search_endpoint}?{params}",
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": settings.brave_search_api_key,
                },
            )
            try:
                with urlopen(request, timeout=settings.contact_discovery_timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                raise ContactDiscoveryRuntimeError(
                    f"Brave Search respondió con HTTP {exc.code}."
                ) from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise ContactDiscoveryRuntimeError(
                    "No se pudo completar la búsqueda automática con Brave Search."
                ) from exc

            for item in payload.get("web", {}).get("results", []):
                results.append(
                    SearchResult(
                        query=query,
                        title=item.get("title"),
                        url=item.get("url"),
                        snippet=item.get("description"),
                    )
                )
        return results


class SerperSearchProvider:
    name = "serper"

    def search(self, queries: list[str]) -> list[SearchResult]:
        if not settings.serper_api_key:
            raise ContactDiscoveryConfigError(
                "Configurá SERPER_API_KEY para habilitar la búsqueda automática con Serper."
            )

        results: list[SearchResult] = []
        count_per_query = max(1, settings.contact_discovery_max_results)
        for query in queries:
            body = json.dumps(
                {
                    "q": query,
                    "num": count_per_query,
                    "gl": settings.serper_country,
                    "hl": settings.serper_language,
                }
            ).encode("utf-8")
            request = Request(
                settings.serper_search_endpoint,
                data=body,
                method="POST",
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "X-API-KEY": settings.serper_api_key,
                },
            )
            try:
                with urlopen(request, timeout=settings.contact_discovery_timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                raise ContactDiscoveryRuntimeError(
                    f"Serper respondió con HTTP {exc.code}."
                ) from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise ContactDiscoveryRuntimeError(
                    "No se pudo completar la búsqueda automática con Serper."
                ) from exc

            for item in payload.get("organic", []):
                results.append(
                    SearchResult(
                        query=query,
                        title=item.get("title"),
                        url=item.get("link"),
                        snippet=item.get("snippet"),
                    )
                )
        return results


class SerpApiSearchProvider:
    name = "serpapi"

    def search(self, queries: list[str]) -> list[SearchResult]:
        if not settings.serpapi_api_key:
            raise ContactDiscoveryConfigError(
                "Configurá SERPAPI_API_KEY para habilitar la búsqueda automática con SerpApi."
            )

        results: list[SearchResult] = []
        count_per_query = max(1, settings.contact_discovery_max_results)
        for query in queries:
            params = urlencode(
                {
                    "engine": "google",
                    "q": query,
                    "api_key": settings.serpapi_api_key,
                    "num": count_per_query,
                    "gl": settings.serpapi_country,
                    "hl": settings.serpapi_language,
                }
            )
            request = Request(
                f"{settings.serpapi_search_endpoint}?{params}",
                headers={"Accept": "application/json"},
            )
            try:
                with urlopen(request, timeout=settings.contact_discovery_timeout_seconds) as response:
                    payload = json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                raise ContactDiscoveryRuntimeError(
                    f"SerpApi respondió con HTTP {exc.code}."
                ) from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                reason = str(exc) or exc.__class__.__name__
                raise ContactDiscoveryRuntimeError(
                    f"No se pudo completar la búsqueda automática con SerpApi: {reason}."
                ) from exc

            api_error = payload.get("error")
            if api_error:
                raise ContactDiscoveryRuntimeError(f"SerpApi respondió: {api_error}")

            results.extend(extract_serpapi_structured_results(payload, query))
            for item in payload.get("organic_results", []):
                results.append(
                    SearchResult(
                        query=query,
                        title=item.get("title"),
                        url=item.get("link"),
                        snippet=item.get("snippet"),
                    )
                )
        return results


PROVIDERS: dict[str, type[ContactDiscoveryProvider]] = {
    "brave": BraveSearchProvider,
    "serper": SerperSearchProvider,
    "serpapi": SerpApiSearchProvider,
    "serverapi": SerpApiSearchProvider,
}


def get_contact_discovery_provider() -> ContactDiscoveryProvider:
    provider_name = settings.contact_discovery_provider.lower().strip()
    provider_type = PROVIDERS.get(provider_name)
    if provider_type is None:
        available = ", ".join(sorted(PROVIDERS))
        raise ContactDiscoveryConfigError(
            f"Proveedor de búsqueda no soportado: {provider_name}. Disponibles: {available}."
        )
    return provider_type()


def build_company_queries(company: Company) -> list[str]:
    company_name = company.trade_name or company.legal_name
    values = {
        "company_name": company_name or "",
        "legal_name": company.legal_name or "",
        "trade_name": company.trade_name or "",
        "tax_id": company.tax_id or "",
        "province": company.province or "Costa Rica",
        "sector": company.sector or "",
    }
    queries: list[str] = []
    for template in settings.contact_discovery_query_templates.split("|"):
        template = template.strip()
        if not template:
            continue
        query = template.format(**values).strip()
        if query and query not in queries:
            queries.append(query)
        if len(queries) >= settings.contact_discovery_max_queries:
            break
    return queries


def infer_social_type(url: str | None) -> ContactMethodType | None:
    if not url:
        return None
    normalized_url = url.lower()
    for host, contact_type in SOCIAL_HOST_TYPES.items():
        if host in normalized_url:
            return contact_type
    return None


def clean_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    if digits.startswith("506") and len(digits) == 11:
        digits = digits[3:]
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:]}"
    return value.strip()


def normalize_json_key(value: str) -> str:
    return value.lower().replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")


def first_string_value(payload: dict, keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_serpapi_structured_results(payload: object, query: str) -> list[SearchResult]:
    """Extract contact fields from SerpApi rich JSON sections, not only organic snippets."""
    results: list[SearchResult] = []

    def walk(value: object) -> None:
        if isinstance(value, list):
            for item in value:
                walk(item)
            return
        if not isinstance(value, dict):
            return

        contact_parts: list[str] = []
        for key, field_value in value.items():
            normalized_key = normalize_json_key(str(key))
            if normalized_key in {normalize_json_key(item) for item in CONTACT_FIELD_KEYS} and field_value:
                contact_parts.append(f"{key}: {field_value}")

        if contact_parts:
            results.append(
                SearchResult(
                    query=query,
                    title=first_string_value(value, TITLE_FIELD_KEYS),
                    url=first_string_value(value, URL_FIELD_KEYS),
                    snippet=" | ".join(contact_parts),
                )
            )

        for child in value.values():
            walk(child)

    walk(payload)
    return results


def extract_candidates(provider_name: str, results: list[SearchResult]) -> list[ContactCandidate]:
    candidates: list[ContactCandidate] = []
    seen: set[tuple[str, str, str | None]] = set()

    for result in results:
        searchable_text = " ".join(part for part in [result.title, result.snippet, result.url] if part)
        source_type = infer_social_type(result.url)
        if source_type and result.url:
            candidate = ContactCandidate(
                provider=provider_name,
                query=result.query,
                source_title=result.title,
                source_url=result.url,
                snippet=result.snippet,
                candidate_name=result.title,
                contact_medium=result.url,
                contact_type=source_type,
                confidence="media",
            )
            key = (candidate.contact_type.value, candidate.contact_medium.lower(), candidate.source_url)
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)

        if result.url and not source_type:
            candidate = ContactCandidate(
                provider=provider_name,
                query=result.query,
                source_title=result.title,
                source_url=result.url,
                snippet=result.snippet,
                candidate_name=result.title,
                contact_medium=result.url,
                contact_type=ContactMethodType.website,
                confidence="baja",
            )
            key = (candidate.contact_type.value, candidate.contact_medium.lower(), candidate.source_url)
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)

        for email in EMAIL_RE.findall(searchable_text):
            candidate = ContactCandidate(
                provider=provider_name,
                query=result.query,
                source_title=result.title,
                source_url=result.url,
                snippet=result.snippet,
                candidate_name=result.title,
                contact_medium=email,
                contact_type=ContactMethodType.correo,
                confidence="alta",
            )
            key = (candidate.contact_type.value, candidate.contact_medium.lower(), candidate.source_url)
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)

        for phone in PHONE_RE.findall(searchable_text):
            clean_value = clean_phone(phone)
            candidate = ContactCandidate(
                provider=provider_name,
                query=result.query,
                source_title=result.title,
                source_url=result.url,
                snippet=result.snippet,
                candidate_name=result.title,
                contact_medium=clean_value,
                contact_type=ContactMethodType.telefono,
                confidence="media",
            )
            key = (candidate.contact_type.value, candidate.contact_medium.lower(), candidate.source_url)
            if key not in seen:
                seen.add(key)
                candidates.append(candidate)

    return candidates[: settings.contact_discovery_max_results]


def save_pending_candidates(
    session: Session,
    company_id: int,
    candidates: list[ContactCandidate],
) -> int:
    saved = 0
    for candidate in candidates:
        existing = session.query(CompanyContactDiscoveryResult).filter_by(
            company_id=company_id,
            contact_medium=candidate.contact_medium,
            source_url=candidate.source_url,
        ).first()
        if existing:
            if existing.status != DiscoveryResultStatus.pending:
                existing.status = DiscoveryResultStatus.pending
                existing.accepted_at = None
                existing.rejected_at = None
                saved += 1
            continue
        session.add(
            CompanyContactDiscoveryResult(
                company_id=company_id,
                provider=candidate.provider,
                query=candidate.query,
                source_title=candidate.source_title,
                source_url=candidate.source_url,
                snippet=candidate.snippet,
                candidate_name=candidate.candidate_name,
                contact_medium=candidate.contact_medium,
                contact_type=candidate.contact_type,
                confidence=candidate.confidence,
                status=DiscoveryResultStatus.pending,
            )
        )
        saved += 1
    session.commit()
    return saved


def discover_company_contacts(session: Session, company: Company) -> int:
    if not settings.contact_discovery_enabled:
        raise ContactDiscoveryConfigError("La búsqueda automática de contactos está deshabilitada.")
    provider = get_contact_discovery_provider()
    queries = build_company_queries(company)
    if not queries:
        raise ContactDiscoveryConfigError("La empresa no tiene suficientes datos para construir búsquedas.")
    results = provider.search(queries)
    candidates = extract_candidates(provider.name, results)
    return save_pending_candidates(session, company.id, candidates)
