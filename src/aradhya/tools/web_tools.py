"""Lightweight web tools for the model-driven agent loop."""

from __future__ import annotations

import re
from html import unescape

import requests

from src.aradhya.tools.tool_registry import tool_definition
from src.aradhya.utils.url_helpers import is_valid_http_url, unwrap_duckduckgo_url

# ── Gap E: network policy registry ──────────────────────────────────────────────────
# The active ToolRuntimePolicy for the current agent turn is stored here
# so web tools can query it without being passed a policy argument.
# Set by assistant_core before each agent turn; cleared to None after.
_active_policy = None


def set_active_network_policy(policy) -> None:
    """Store the current turn's ToolRuntimePolicy for network checks."""
    global _active_policy
    _active_policy = policy


def _check_network(tool_name: str) -> str | None:
    """Return a denial string if network is blocked, else None."""
    if _active_policy is not None and hasattr(_active_policy, "check_network_access"):
        decision = _active_policy.check_network_access(tool_name)
        if not decision.allowed:
            return decision.message
    return None


DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "Aradhya/0.1 local assistant"

# Pre-compiled regexes for performance
_DDG_RESULT_LINK_RE = re.compile(
    r'<a[^>]+class="[^"]*result__a[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_RE = re.compile(
    r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>',
    flags=re.IGNORECASE | re.DOTALL,
)
_HTML_STRIP_RE = re.compile(
    r"<(script|style)\b.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_HTML_BR_RE = re.compile(r"<br\s*/?>", flags=re.IGNORECASE)
_HTML_P_RE = re.compile(r"</p\s*>", flags=re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t\r\f\v]+")


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
    # ── Gap E: network policy check ──
    denial = _check_network("web_fetch")
    if denial:
        return denial

    if not is_valid_http_url(url):
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
    # ── Gap E: network policy check ──
    denial = _check_network("web_search")
    if denial:
        return denial

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
    link_matches = _DDG_RESULT_LINK_RE.finditer(html)
    snippets = [_html_to_text(match.group(1)) for match in _DDG_SNIPPET_RE.finditer(html)]

    results: list[dict[str, str]] = []
    for index, match in enumerate(link_matches):
        if len(results) >= max_results:
            break
        raw_url = unescape(match.group(1))
        title = _html_to_text(match.group(2))
        url = unwrap_duckduckgo_url(raw_url)
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


def _html_to_text(raw_html: str) -> str:
    text = _HTML_STRIP_RE.sub(" ", raw_html)
    text = _HTML_BR_RE.sub("\n", text)
    text = _HTML_P_RE.sub("\n", text)
    text = _HTML_TAG_RE.sub(" ", text)
    return _normalize_text(unescape(text))


def _normalize_text(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).replace("\n ", "\n").strip()


ALL_WEB_TOOLS = [web_fetch, web_search]
