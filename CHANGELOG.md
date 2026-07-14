# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Cloudflare Workers AI provider with privacy gate integration
- NVDA output module for accessibility
- Demo streaming visibility improvements

### Changed
- Renamed Parasite OS internals → Symbiont (code, CLI, config, tests, and docs)
- Default to on-device `llama3.2:3b` with 600s timeout for tool turns
- Senior-audit cleanup: removed dead code, honest-docs pass

### Fixed
- Ollama tool-call arguments sent as object (not JSON string)
- History processors guarded against None message content
- 5 ruff lint errors blocking CI gate
- Daemon fails closed when API has no auth token
- Security: config hygiene, single-source tool gate, cloud-gate tool scan
- Security: daemon auth, Telegram default-deny, Windows shlex, channel gates

## [0.1.0] - 2025-12-01

### Added
- Local-first Operating Intelligence (OI) architecture with Ollama inference
- Rich terminal CLI with slash commands and `<thought>` block rendering
- Desktop floating icon overlay for quick Mic/Vision/Debate activation
- Telegram bot for secure remote access with live-streaming experience
- Multi-layered safety: Confirmation Gate, Hook Engine, Permission Engine
- SQLite WAL state store with automatic context compaction
- Voice pipeline: manual transcripts, Whisper integration, push-to-talk, wake-word
- Tool registry: file, shell, browser, vision, power, scheduler, session tools
- Symbiont OS subsystem (formerly Parasite OS): skill framework, hooks, permissions, dynamic loading
- Browser automation via Selenium with multi-tab parallel research
- Local API catalog and network topology discovery
- Audit logging via JSONL event-sourcing
- Smart router with weighted round-robin model distribution
- Subagent framework with planning workflows
- Trust-boundary workflow engine for safe multi-step operations
- Desktop control via UI Automation
- Hardware profile and reality-grounded model recommendations
- Mentor do/teach mode for guided learning
- Multimodal screen description and screen-reader skill
- User context store for form assistance
- Safe-maintenance tools on trust-boundary engine
- Cloud privacy gate for OpenRouter fallback
- Dry-run by default for all dangerous operations
- GPL v3 license and Contributor Covenant Code of Conduct

[Unreleased]: https://github.com/Saurabh0003M/ARADHYA/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Saurabh0003M/ARADHYA/releases/tag/v0.1.0
