from __future__ import annotations

from src.aradhya.tools import web_tools


class FakeResponse:
    def __init__(self, text: str, content_type: str = "text/html"):
        self.text = text
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


def test_web_fetch_returns_readable_text(monkeypatch):
    def fake_get(url, *, headers, timeout, params=None):
        return FakeResponse("<html><body><h1>Hello</h1><p>World</p></body></html>")

    monkeypatch.setattr(web_tools.requests, "get", fake_get)

    result = web_tools.web_fetch("https://example.com")

    assert "Hello" in result
    assert "World" in result
    assert "<h1>" not in result


def test_web_search_parses_duckduckgo_results(monkeypatch):
    html = """
    <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com">Example</a>
    <a class="result__snippet">An example result.</a>
    """

    def fake_get(url, *, params, headers, timeout):
        assert params == {"q": "example query"}
        return FakeResponse(html)

    monkeypatch.setattr(web_tools.requests, "get", fake_get)

    result = web_tools.web_search("example query", max_results=3)

    assert "Example" in result
    assert "https://example.com" in result
    assert "An example result." in result
