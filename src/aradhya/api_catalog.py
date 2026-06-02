"""Local searchable catalog for public API discovery."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CATALOG_CACHE_PATH = Path("data/processed/context/public_apis_catalog.json")
PUBLIC_APIS_REPO_URL = "https://github.com/public-apis/public-apis"


@dataclass(frozen=True)
class PublicApiEntry:
    """One API directory entry."""

    name: str
    description: str
    auth: str
    https: bool
    cors: str
    category: str
    link: str = ""
    source: str = "seed"


@dataclass(frozen=True)
class ApiCatalogSource:
    """Where the current catalog came from."""

    kind: str
    path: Path | None
    entry_count: int
    url: str = PUBLIC_APIS_REPO_URL


class PublicApiCatalog:
    """Read-only public API discovery catalog.

    The catalog starts with a small built-in seed and can read a local JSON
    cache later.  It never calls remote APIs from slash commands.
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root
        self.cache_path = project_root / CATALOG_CACHE_PATH
        self._entries, self._source = self._load_entries()

    @property
    def source(self) -> ApiCatalogSource:
        return self._source

    def entries(self) -> list[PublicApiEntry]:
        return list(self._entries)

    def categories(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for entry in self._entries:
            counts[entry.category] = counts.get(entry.category, 0) + 1
        return sorted(counts.items(), key=lambda item: (item[0].lower(), item[1]))

    def search(self, query: str, *, limit: int = 10) -> list[PublicApiEntry]:
        terms = self._terms(query)
        if not terms:
            return []
        scored: list[tuple[int, PublicApiEntry]] = []
        for entry in self._entries:
            haystack = " ".join(
                [
                    entry.name,
                    entry.description,
                    entry.category,
                    entry.auth,
                    entry.cors,
                ]
            ).lower()
            score = sum(
                3 if term in entry.name.lower() else 1 for term in terms if term in haystack
            )
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: (-item[0], item[1].name.lower()))
        return [entry for _score, entry in scored[:limit]]

    def by_category(self, category: str, *, limit: int = 12) -> list[PublicApiEntry]:
        normalized = category.strip().lower()
        if not normalized:
            return []
        matches = [entry for entry in self._entries if normalized in entry.category.lower()]
        return sorted(matches, key=lambda entry: entry.name.lower())[:limit]

    def inspect(self, name: str) -> PublicApiEntry | None:
        normalized = name.strip().strip("\"'").lower()
        if not normalized:
            return None
        for entry in self._entries:
            if entry.name.lower() == normalized:
                return entry
        matches = self.search(normalized, limit=1)
        return matches[0] if matches else None

    def recommend(self, need: str, *, limit: int = 5) -> list[PublicApiEntry]:
        expanded = self._expand_need(need)
        return self.search(expanded, limit=limit)

    def risk_label(self, entry: PublicApiEntry) -> str:
        if not entry.https:
            return "high: no HTTPS"
        auth = entry.auth.strip().lower()
        if auth not in {"no", "none", ""}:
            return f"review: requires {entry.auth}"
        if entry.category.lower() in {"finance", "health", "security", "anti-malware"}:
            return "review: sensitive domain"
        if entry.cors.lower() == "unknown":
            return "review: CORS unknown"
        return "low: no auth + HTTPS"

    def _load_entries(self) -> tuple[list[PublicApiEntry], ApiCatalogSource]:
        cached = self._load_cached_entries()
        if cached:
            return cached, ApiCatalogSource(
                kind="local-cache",
                path=self.cache_path,
                entry_count=len(cached),
            )
        seed = self._seed_entries()
        return seed, ApiCatalogSource(kind="built-in-seed", path=None, entry_count=len(seed))

    def _load_cached_entries(self) -> list[PublicApiEntry]:
        if not self.cache_path.exists():
            return []
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        raw_entries = payload.get("entries") if isinstance(payload, dict) else payload
        if not isinstance(raw_entries, list):
            return []

        entries: list[PublicApiEntry] = []
        for raw in raw_entries:
            if isinstance(raw, dict):
                entry = self._entry_from_payload(raw, source="local-cache")
                if entry is not None:
                    entries.append(entry)
        return entries

    def _entry_from_payload(self, raw: dict[str, Any], *, source: str) -> PublicApiEntry | None:
        name = str(raw.get("API") or raw.get("api") or raw.get("name") or "").strip()
        if not name:
            return None
        https_raw = raw.get("HTTPS", raw.get("https", True))
        if isinstance(https_raw, str):
            https = https_raw.strip().lower() in {"true", "yes", "1"}
        else:
            https = bool(https_raw)
        return PublicApiEntry(
            name=name,
            description=str(raw.get("Description") or raw.get("description") or "").strip(),
            auth=str(raw.get("Auth") or raw.get("auth") or "Unknown").strip() or "Unknown",
            https=https,
            cors=str(raw.get("Cors") or raw.get("CORS") or raw.get("cors") or "Unknown").strip(),
            category=str(raw.get("Category") or raw.get("category") or "Uncategorized").strip(),
            link=str(raw.get("Link") or raw.get("link") or "").strip(),
            source=source,
        )

    def _seed_entries(self) -> list[PublicApiEntry]:
        raw_seed = [
            {
                "API": "Open-Meteo",
                "Description": "Weather forecasts and historical weather data",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Weather",
                "Link": "https://open-meteo.com/",
            },
            {
                "API": "REST Countries",
                "Description": "Country names, regions, flags, currencies, and population data",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Open Data",
                "Link": "https://restcountries.com/",
            },
            {
                "API": "Frankfurter",
                "Description": "Current and historical foreign exchange rates",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Currency Exchange",
                "Link": "https://www.frankfurter.app/",
            },
            {
                "API": "Hacker News",
                "Description": "Stories, comments, jobs, polls, and user data",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Unknown",
                "Category": "News",
                "Link": "https://github.com/HackerNews/API",
            },
            {
                "API": "Open Library",
                "Description": "Book metadata, authors, covers, and search",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Books",
                "Link": "https://openlibrary.org/developers/api",
            },
            {
                "API": "Stack Exchange",
                "Description": "Questions, answers, comments, users, and tags",
                "Auth": "OAuth",
                "HTTPS": True,
                "Cors": "Unknown",
                "Category": "Development",
                "Link": "https://api.stackexchange.com/",
            },
            {
                "API": "GitHub",
                "Description": "Repositories, issues, pull requests, users, and releases",
                "Auth": "OAuth",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Development",
                "Link": "https://docs.github.com/en/rest",
            },
            {
                "API": "Nominatim",
                "Description": "OpenStreetMap geocoding and reverse geocoding",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Geocoding",
                "Link": "https://nominatim.org/release-docs/latest/api/Overview/",
            },
            {
                "API": "Data.gov",
                "Description": "US government datasets and metadata catalog",
                "Auth": "apiKey",
                "HTTPS": True,
                "Cors": "Unknown",
                "Category": "Government",
                "Link": "https://api.data.gov/",
            },
            {
                "API": "URLhaus",
                "Description": "URL reputation and malware URL intelligence",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Security",
                "Link": "https://urlhaus-api.abuse.ch/",
            },
            {
                "API": "Wikipedia REST API",
                "Description": "Page summaries, search, media, and content metadata",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Open Data",
                "Link": "https://www.mediawiki.org/wiki/API",
            },
            {
                "API": "Agify",
                "Description": "Estimate age from a first name using public aggregate data",
                "Auth": "No",
                "HTTPS": True,
                "Cors": "Yes",
                "Category": "Test Data",
                "Link": "https://agify.io/",
            },
        ]
        return [
            entry
            for item in raw_seed
            if (entry := self._entry_from_payload(item, source="seed")) is not None
        ]

    def _terms(self, text: str) -> list[str]:
        return [term.lower() for term in re.findall(r"[A-Za-z0-9_+-]+", text) if len(term) > 1]

    def _expand_need(self, need: str) -> str:
        lowered = need.lower()
        extras: list[str] = []
        synonym_map = {
            "weather": ("forecast", "climate"),
            "currency": ("exchange", "forex", "rates"),
            "money": ("currency", "exchange", "finance"),
            "location": ("geocoding", "map"),
            "map": ("geocoding", "location"),
            "security": ("reputation", "malware"),
            "code": ("development", "github"),
            "repo": ("development", "github"),
            "book": ("books", "library"),
            "news": ("hacker", "stories"),
        }
        for trigger, words in synonym_map.items():
            if trigger in lowered:
                extras.extend(words)
        return " ".join([need, *extras])
