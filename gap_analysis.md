# Aradhya vs OpenClaw — Deep Architecture Comparison (Post-Daemon)

> [!NOTE]
> This document was produced after committing the **Background Daemon**, **HTTP API**, and **Heartbeat-Wired Scheduler**. Aradhya is now architecturally capable of overnight autonomous work.

---

## Executive Summary

| Metric | OpenClaw | Aradhya |
|--------|---------|---------|
| **Language** | TypeScript (Node 22+) | Python 3.10+ |
| **Codebase size** | ~65 src/ subdirectories, 861+ files in `agents/` alone | 44 Python files, ~312 KB total |
| **Default model** | GPT-5.5 (cloud, `openai`) | Ollama local (any model) |
| **Cloud dependency** | Required for most features | Zero — fully offline capable |
| **Platform target** | macOS primary, Linux, Windows | Windows primary |
| **Plugin ecosystem** | npm-based, 12+ community plugins | Skills (YAML prompt injection) |
| **Daemon mechanism** | launchd / systemd / schtasks | pystray system tray + HTTP API |

---

## Subsystem-by-Subsystem Comparison

### 1. Agent Execution Loop

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Location** | `src/agents/pi-embedded-runner.ts` + `pi-embedded-subscribe.ts` (~90+ files) | `src/aradhya/agent_loop.py` (435 lines) |
| **Model integration** | Native OpenAI/Anthropic API with structured tool-calling, streaming, and response payloads | Ollama `chat()` with tool-calling OR text-completion fallback with JSON extraction |
| **Tool calling** | Native function-calling API (OpenAI `tools` param) | Native via `chat()` if model supports it; JSON-in-text fallback for simpler models |
| **Iteration control** | Session-scoped with compaction + 48-hour timeout | `max_iterations=10` with repeated-call detection |
| **Streaming** | Real-time token streaming via WebSocket | ❌ Synchronous — waits for full response |

**Verdict:** Aradhya's loop is functionally equivalent for local models. The main gap is **streaming** — the user stares at a blank screen during long loops.

---

### 2. Tool Loop Detection

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Location** | `src/agents/tool-loop-detection.ts` (770 lines) | `agent_loop.py` `_is_repeated_tool_call()` (15 lines) |
| **Detectors** | 5 detectors: `generic_repeat`, `unknown_tool_repeat`, `known_poll_no_progress`, `global_circuit_breaker`, `ping_pong` | Simple count-based: same name+args seen ≥ N times |
| **Result hashing** | SHA-256 digest of tool params + result content for no-progress detection | JSON key comparison of name + arguments |
| **Configurable** | Per-session config with warning vs critical thresholds | Single `max_repeated_tool_calls` parameter |

**Verdict:** OpenClaw's loop detection is industrial-grade with 770 lines of pattern detection. Aradhya's is effective for basic scenarios but would miss subtle ping-pong or no-progress loops. This is a **quality gap**, not a capability gap.

---

### 3. Tool Execution & Safety

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Approval system** | `node-invoke-system-run-approval.ts` — regex-based auto-approve patterns per directory, ask/deny rules, iOS push notifications for remote approval | `ToolRuntimePolicy` — path-root enforcement, mutation grants, binary live_execution flag |
| **Path policy** | `path-policy.ts` + `tool-fs-policy.ts` — workspace root guards, sandbox path mounting, tilde expansion | `_check_path_arguments()` — ensures all paths are within `allowed_roots` |
| **Sandboxing** | Docker containers with volume mounts, `Dockerfile.sandbox` | ❌ None — runs directly on host |
| **Tool catalog** | 20+ tools: `exec`, `read`, `write`, `apply_patch`, `web_search`, `web_fetch`, `image_generate`, `video_generate`, `music_generate`, `pdf`, `camera`, `browser` | 12 tools: `read_file`, `write_file`, `list_directory`, `search_files`, `run_command`, `open_path`, `open_url`, `clipboard_write`, `save_note`, `web_search`, `web_fetch`, `session_summary` |

**Verdict:** Aradhya has the core tools wired and safety policies enforced. OpenClaw has a much larger tool catalog (especially media generation) and Docker sandboxing. The safety policy patterns are architecturally equivalent.

---

### 4. Background Daemon

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Location** | `src/daemon/` (62 files, ~250KB) | `src/aradhya/daemon.py` + `daemon_api.py` (2 files, ~12KB) |
| **macOS** | LaunchAgent plist registration via `launchd.ts` | N/A (Windows-only project) |
| **Linux** | systemd unit file via `systemd.ts` | N/A |
| **Windows** | `schtasks.exe` via `schtasks.ts` (32KB) | `pystray` system tray icon |
| **API** | WebSocket + HTTP gateway with auth, rate limiting, channel multiplexing | Localhost HTTP (stdlib, no auth needed for local-only) |
| **Service management** | install / uninstall / start / stop / restart / status via CLI | Start via `python -m src.aradhya.daemon`, stop via tray or `/shutdown` |
| **Auto-start** | Registered as OS service (survives reboot) | Manual shortcut to `shell:startup` (follow-up) |

**Verdict:** OpenClaw's daemon is enterprise-grade with 3-platform service registration. Aradhya's is pragmatic — a tray icon with HTTP API that **solves the real problem** (surviving terminal closure) without the complexity. Auto-restart on reboot is a future enhancement.

---

### 5. Heartbeat / Cron System

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Location** | `src/cron/` (85 files, ~400KB) | `src/aradhya/scheduler.py` (220 lines) |
| **Schedule types** | Cron expressions, `every` intervals, one-shot `at` timestamps | Fixed `interval_minutes` |
| **Timezone** | Full timezone-aware scheduling via `croner` | System local time |
| **Heartbeat agent** | Spawns isolated agent sessions with `HEARTBEAT.md` instructions | `agent_think` action calls `handle_transcript()` through the full planning pipeline |
| **Run logging** | SQLite-backed `run-log.ts` with delivery tracking, failure alerts | Heartbeat log files in `core/memory/heartbeat_log/` |
| **Session cleanup** | `session-reaper.ts` — cleans up old cron sessions | ❌ Not implemented |

**Verdict:** Both systems can now wake the agent and trigger autonomous thinking. OpenClaw's is much more sophisticated (cron expressions, SQLite logging, delivery tracking). Aradhya's is intentionally simple but functionally complete for the "check every N minutes" use case.

---

### 6. Web Search & Fetch

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Location** | `src/web-search/` + `src/web-fetch/` + plugin providers | `src/aradhya/tools/web_tools.py` (173 lines) |
| **Search providers** | Pluggable: Google, Bing, Tavily, Brave, DuckDuckGo, SearXNG, Perplexity via plugin system with API key management and auto-detection | DuckDuckGo HTML scraping (no API key needed) |
| **Fetch** | Full HTML-to-text conversion with provider routing | `requests` + regex HTML stripping |
| **Failover** | Provider cascade with structured error detection | Single provider, error returns string |

**Verdict:** Architecturally equivalent for the core use case. Aradhya's DuckDuckGo approach is actually an advantage — it works without API keys, which aligns with the "zero cloud dependency" philosophy.

---

### 7. Session & Memory

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Session management** | 19 files in `src/sessions/`, SQLite-backed, session IDs, key resolution, lifecycle events | `session_manager.py` (8KB) — JSON file-backed, named sessions, message history |
| **Compaction** | `compaction.ts` (19KB) — LLM-summarized compaction with retry and identifier preservation | `compact_session()` — keeps last N messages, discards older ones |
| **Context injection** | `context.ts` (18KB) — eager warmup, lookup, bootstrap file collection | `context_engine.py` (6KB) — index snapshot + skill instructions + user context |
| **Standing orders** | `AGENTS.md` + `HEARTBEAT.md` injected into system prompt | `rules.md` + `notes.md` read from `core/memory/user_context/` and injected |

**Verdict:** Both systems maintain conversation history and inject context. OpenClaw's is industrial-strength with SQLite persistence and LLM-driven compaction. Aradhya's is simple but functional — JSON files with basic trimming.

---

### 8. Model Provider

| Aspect | OpenClaw | Aradhya |
|--------|---------|---------|
| **Providers** | 15+ providers: OpenAI, Anthropic, Google, Ollama, Groq, Together, OpenRouter, Copilot, Bedrock, Azure, Chutes, MiniMax, Moonshot, StepFun, xAI | 1 provider: Ollama |
| **Failover** | `model-fallback.ts` (36KB) — automatic provider rotation with cooldown, auth profiles | ❌ Single provider, no fallback |
| **Auth** | `model-auth.ts` (25KB) — API key rotation, OAuth, auth profiles, rate limiting | Ollama (no auth needed for local) |
| **Model catalog** | Dynamic model discovery with catalog lookup and runtime aliases | Static model name from config |
| **Streaming** | SSE / WebSocket streaming with chunk splitting | ❌ Synchronous only |

**Verdict:** This is the largest remaining gap. OpenClaw's multi-provider failover is a major advantage. However, Aradhya's single-provider approach is a *deliberate design choice* (offline-first, zero cloud dependency). Adding a cloud provider as a fallback would be straightforward.

---

## What Aradhya Has That OpenClaw Doesn't

| Feature | Aradhya | OpenClaw |
|---------|---------|---------|
| **Zero cloud dependency** | Fully functional offline with Ollama | Requires API keys for most features |
| **Windows-native** | Built for Windows, Win32 APIs, pystray tray | Primarily macOS/Linux; Windows is secondary |
| **Push-to-talk + wake word** | Native microphone capture + wake word detection | Voice via plugins only |
| **Floating desktop icon** | tkinter wake icon with IPC | No desktop presence on Windows |
| **Rule-based fast path** | Deterministic intent matching before LLM | Everything goes through the model |
| **Simple codebase** | 44 Python files, easy to read and extend | 861+ agent files, massive TypeScript monorepo |

---

## Final Gap Summary

| Category | Status | Notes |
|----------|--------|-------|
| Agent Loop | ✅ Complete | Wired, iterating, tool-calling |
| Tool Registry | ✅ Complete | 12 tools registered and executing |
| Runtime Policy | ✅ Complete | Path enforcement + mutation grants |
| Web Tools | ✅ Complete | Search + Fetch, no API key needed |
| Session Memory | ✅ Complete | History passed to agent loop |
| Standing Orders | ✅ Complete | rules.md injected into prompts |
| Background Daemon | ✅ Complete | pystray tray + HTTP API |
| Heartbeat Scheduler | ✅ Complete | agent_think → full AgentLoop |
| Context Engine | ✅ Complete | Snapshot + skills + user context |
| **Streaming** | 🟡 Not built | UX improvement, not blocking |
| **Multi-Model** | 🟡 Not built | Deliberate (offline-first) |
| **Docker Sandbox** | 🟡 Not built | Security improvement |
| **Sub-Agents** | 🟡 Not built | Advanced feature |
| **Plugin System** | 🟡 Not built | Skills serve similar purpose |
| **MCP** | 🟡 Not built | Standardization |

---

## Can Aradhya Work Overnight Now?

### ✅ YES — with caveats

The architecture is now complete:

```
1. User launches daemon:  python -m src.aradhya.daemon
2. Tray icon appears, assistant is auto-waked
3. User configures a heartbeat task in schedules.json:
   {
     "id": "overnight_review",
     "action": "agent_think",
     "payload": "Check the project status, run tests, summarize results.",
     "interval_minutes": 30,
     "enabled": true
   }
4. Every 30 minutes, the scheduler fires → assistant thinks → tools execute → results logged
5. User closes terminal — daemon keeps running via system tray
6. In the morning, user checks heartbeat_log/ for overnight activity
```

**Caveats:**
- The model must support tool calling (e.g., `llama3.1`, `qwen2.5` via Ollama)
- No Docker sandboxing — be careful with `allow_live_execution: true`
- No streaming — long agent loops show no progress indicator
- Process survives terminal close but not a reboot (add to `shell:startup` manually)
