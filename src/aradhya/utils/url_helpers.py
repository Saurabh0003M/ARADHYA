from urllib.parse import parse_qs, unquote, urlparse

def is_valid_http_url(url: str) -> bool:
    """Check if a URL has a valid HTTP/HTTPS scheme and a network location."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

def unwrap_duckduckgo_url(raw_url: str) -> str:
    """Unwrap a DuckDuckGo redirect URL to get the actual target URL."""
    if raw_url.startswith("//"):
        raw_url = "https:" + raw_url
    parsed = urlparse(raw_url)
    query = parse_qs(parsed.query)
    if "uddg" in query and query["uddg"]:
        return unquote(query["uddg"][0])
    return raw_url
