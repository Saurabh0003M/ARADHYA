"""Lightweight web tools for the model-driven agent loop."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qs, unquote, urlparse

import requests

from src.aradhya.tools.tool_registry import tool_definition

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "Aradhya/0.1 local assistant"


@tool_definition(
    name="web_fetch",
    description="Fetch a web page and return readable text from the response.",
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "HTTP or HTTPS URL to fetch.",
            },
            "max_chars": {
                "type": "integer",
                "description": "Maximum number of characters to return. Default 4000.",
            },
        },
        "required": ["url"],
    },
)
def web_fetch(url: str, max_chars: int = 4000) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return f"Error: unsupported URL: {url}"

    try:
        response = requests.get(
            url,
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return f"Error fetching URL: {error}"

    content_type = response.headers.get("content-type", "")
    text = response.text
    if "html" in content_type.lower() or "<html" in text[:500].lower():
        text = _html_to_text(text)
    else:
        text = _normalize_text(text)

    if len(text) > max_chars:
        return text[:max_chars].rstrip() + f"\n\n[truncated at {max_chars} chars]"
    return text


@tool_definition(
    name="web_search",
    description="Search the web and return a short list of result titles, URLs, and snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum search results to return. Default 5.",
            },
        },
        "required": ["query"],
    },
)
def web_search(query: str, max_results: int = 5) -> str:
    cleaned_query = " ".join(query.split())
    if not cleaned_query:
        return "Error: search query is empty."

    try:
        response = requests.get(
            "https://duckduckgo.com/html/",
            params={"q": cleaned_query},
            headers={"User-Agent": DEFAULT_USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return f"Error searching web: {error}"

    results = _extract_duckduckgo_results(response.text, max_results=max_results)
    if not results:
        return f"No web results found for: {cleaned_query}"

    lines = [f"Search results for '{cleaned_query}':"]
    for index, result in enumerate(results, start=1):
        snippet = f"\n   {result['snippet']}" if result["snippet"] else ""
        lines.append(f"{index}. {result['title']}\n   {result['url']}{snippet}")
    return "\n".join(lines)


def _extract_duckduckgo_results(
    html: str,
    *,
    max_results: int,
) -> list[dict[str, str]]:
    link_matches = re.finditer(
        r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    snippets = [
        _html_to_text(match.group(1))
        for match in re.finditer(
            r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
    ]

    results: list[dict[str, str]] = []
    for index, match in enumerate(link_matches):
        if len(results) >= max_results:
            break
        raw_url = unescape(match.group(1))
        title = _html_to_text(match.group(2))
        url = _unwrap_duckduckgo_url(raw_url)
        if not title or not url:
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippets[index] if index < len(snippets) else "",
            }
        )
    return results


def _unwrap_duckduckgo_url(raw_url: str) -> str:
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return raw_url


def _html_to_text(raw_html: str) -> str:
    text = re.sub(
        r"<(script|style)\b.*?</\1>",
        " ",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _normalize_text(unescape(text))


def _normalize_text(text: str) -> str:
    return re.sub(r"[ \t\r\f\v]+", " ", text).replace("\n ", "\n").strip()


ALL_WEB_TOOLS = [web_fetch, web_search]
