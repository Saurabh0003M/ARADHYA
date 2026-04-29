---
name: web-search
description: Web search and URL content extraction for research and information gathering.
requires:
  python_packages:
    - requests
intents:
  - WEB_SEARCH
  - WEB_FETCH
---

You can search the web and fetch content from URLs to answer user questions.

### Capabilities

- **Web search**: Search the web using a search API and return summarized results.
- **URL fetch**: Fetch and extract text content from a given URL.
- **Summarize**: Condense long web pages into key points.
- **Compare**: Gather information from multiple sources and compare findings.

### Usage Guidelines

- Use web search when the user asks about current events, facts, or external information.
- Prefer local context and knowledge first; fall back to web search only when needed.
- Always cite the source URL when presenting web-sourced information.
- Do not blindly trust web content — flag uncertain or conflicting information.

### Safety Rules

- Web search is read-only and does not require confirmation.
- Never submit forms, create accounts, or perform transactions via web tools.
- Respect robots.txt and rate limits when fetching URLs.
