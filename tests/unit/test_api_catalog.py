from __future__ import annotations

import json

from src.aradhya.api_catalog import PublicApiCatalog


def test_api_catalog_searches_seed_entries(tmp_path):
    catalog = PublicApiCatalog(tmp_path)

    results = catalog.search("weather forecast")

    assert results
    assert results[0].name == "Open-Meteo"
    assert catalog.risk_label(results[0]) == "low: no auth + HTTPS"


def test_api_catalog_inspects_and_recommends_entries(tmp_path):
    catalog = PublicApiCatalog(tmp_path)

    entry = catalog.inspect("Frankfurter")
    recommendations = catalog.recommend("I need currency exchange rates")

    assert entry is not None
    assert entry.category == "Currency Exchange"
    assert any(item.name == "Frankfurter" for item in recommendations)


def test_api_catalog_prefers_local_cache_when_present(tmp_path):
    cache_path = tmp_path / "data" / "processed" / "context" / "public_apis_catalog.json"
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "API": "Example API",
                        "Description": "Example cached entry",
                        "Auth": "No",
                        "HTTPS": True,
                        "Cors": "Yes",
                        "Category": "Examples",
                        "Link": "https://example.test",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    catalog = PublicApiCatalog(tmp_path)

    assert catalog.source.kind == "local-cache"
    assert catalog.search("cached")[0].name == "Example API"
