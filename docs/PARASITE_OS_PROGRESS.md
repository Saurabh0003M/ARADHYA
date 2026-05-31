# Parasite OS Progress Tracker

Last updated: 2026-05-31

This tracker records build status, storage decisions, and acceptance gates for
the Parasite OS direction on top of Aradhya.

## Current Storage Decision

Decision: do not fully move the active repo to `D:` yet.

Use the Samsung T9 `D:` drive now for heavy storage, mirrors, backups, models,
datasets, screenshots, archives, and future VM or OS images. Keep the current
development workspace stable until path-portability checks pass from a copied
workspace.

Observed drive state from the user screenshot:

| Drive | Label | Free space | Role |
| --- | --- | ---: | --- |
| `C:` | Windows | 46.2 GB free of 325 GB | Keep OS and normal Windows apps here |
| `D:` | Samsung T9 volume 2 | 465 GB free of 465 GB | Best target for Parasite OS storage and migration staging |
| `E:` | SamsungT9 volume 1 | 314 GB free of 465 GB | Secondary portable storage |
| `F:` | New Volume | 23.0 GB free of 149 GB | Current active repo drive, becoming space constrained |

Recommended first layout on `D:`:

```text
D:\ParasiteOS\
  Artifacts\
  Backups\
  Datasets\
  Models\
  Repos\
  Runtime\
  VM\
```

Do not put API keys in this tree. Keep keys in Windows environment variables.

## OS Strategy Decision

Decision: do not install or fork an open source OS as the main path right now.

The next three months should continue as a Windows local-first Operating
Intelligence layer. Forking Linux, ReactOS, Android-x86, or another OS now
would change the project from "usable assistant" into a low-level OS project
before the intelligence layer is proven.

Better sequence:

1. Build Parasite OS as an OI layer on Windows.
2. Move heavy storage and repeatable runtime artifacts to `D:`.
3. Add LAN federation and capability routing.
4. Add a Linux/WSL/VM sandbox node later if it helps tools, agents, or safety.
5. Only after the OI loop is useful, evaluate a bootable/open-source OS base.

## Current Implemented State

| Area | Status | Notes |
| --- | --- | --- |
| Local-first CLI shell | Done | `arise.bat`, slash commands, status, help, health checks |
| Confirmation gate | Done | Dangerous tools stay behind confirmation |
| Audit logging | Done | Tool calls are logged through audit infrastructure |
| Ollama model provider | Done | Default local model path remains supported |
| OpenRouter provider | Done | Includes robust HTTP 429 failover chaining |
| Cloud privacy gate | Done | Blocks secrets, local paths, and private runtime markers |
| Model worker registry | Done | `/model workers` and `/model workers assess <text>` |
| Public API catalog | Done | `/apis`, search, category, inspect, recommend |
| Hook engine foundation | Done | PreToolUse/PostToolUse interceptors via stdin/stdout |
| Runtime permission rules | Done | Pattern matching allow/deny gates, conditional blocks |
| Agent definitions | Done | Parsed via Markdown YAML frontmatter |
| Host repo digestion batch | Done | 7-stage state machine (`ENGULF` -> `ABSORB`) with checkpoints |
| Host integration ledger | Done | `/parasite candidates`, `/parasite inspect`, deduplicator |
| First agency skill promotion | Done | `agency-engineering-review` absorbed into native skills |
| Learnings Engine | Done | Auto-promotes repeating insights (3+ hits) to `rules.md` |
| Dynamic Skill loading | Done | Git/Web skill absorption, intent-based token conservation |
| Topology manifest | Done | Local device capability scaffold |
| Path portability layer | Done | `ARADHYA_HOME`, `parasite.toml`, and `~/.aradhya` resolution |
| Session/state hardening | Done | Session management via SQLite WAL state store |
| Timeout kill switch | Done | Agent loop guardrails for iteration limits |
| LAN federation foundation | Done | SHA-256 fingerprint identity, peer registry, doctor |
| Opus coordination notes | Done | `docs/OPUS_HANDOFF.md` |
| Generated artifact cleanup | Done | `data/processed/pytest_*` artifacts removed and ignored |
| Full user acceptance loop | Partial | Unit/doctor checks pass; UI smoke testing ongoing |

## Host Repo Digestion Architecture

The Parasite OS ingestion architecture has evolved into a fully resilient, 7-stage state-machine pipeline that analyzes downloaded code repositories (`Hosts/`) and extracts safe capabilities into Aradhya:

1. **ENGULF**: Identifies target and records basic metadata.
2. **ISOLATE**: Quick trust check (README, LICENSE, GitHub stars) to assign a `trust_score`.
3. **CHEW**: Confirms target isolation in the `Hosts/` directory.
4. **SWALLOW (`analyzer.py`)**: Deep analysis of project structure, dependencies, extracting capabilities (MCP servers, API clients, agents). Runs `CloudPrivacyGate` against documentation. Produces `.parasite/DIGEST.md`.
5. **DIGEST**: Plans integration artifacts.
6. **EXTRACT**: Validates generated artifacts (Quality Gate).
7. **ABSORB**: Pushes validated artifacts into Aradhya's live tree (producing `SKILL.md` files).

This is backed by `checkpoint.py` for resumable state and `deduplicator.py` to merge overlapping skills using LLM-assisted verification.

## Not Done Yet

| Area | Status | Next gate |
| --- | --- | --- |
| Drive migration | Not started | Copy repo to `D:\ParasiteOS\Repos\ARADHYA`, run doctor/tests from there |
| Portable runtime profile | Partial | Validate copied-workspace behavior |
| Federation transport | Not started | Local-only message envelope with replay protection |
| Watcher-driven context index | Not started | Replace repeated full scans with dirty-root invalidation |
| Open-source OS base | Deferred | Revisit after OI loop and federation are useful |
| Production packaging | Not started | Installer/startup integration after local OI loop stabilizes |

## Migration Acceptance Gates

Move the active workspace to `D:` only after all gates pass from a copied repo:

1. `scripts\doctor.bat` passes from the copied path.
2. `venv\Scripts\python.exe -m pytest tests\unit --override-ini=addopts=` passes.
3. `.\arise.bat` starts from the copied path.
4. `/status`, `/model workers`, `/apis search weather`, `/topology`, and
   `/federation doctor` work from the copied path.
5. No tracked config requires `F:\ARADHYA`.
6. Runtime-generated files under `core/config/*.local.json`, topology files,
   federation state, logs, and caches remain ignored.
7. Dismounting the portable drive cannot damage the only copy of the repo.

## Next Build Slice

1. Add a storage profile command:
   - show current repo path
   - detect available drives
   - recommend storage roles
   - warn when active drive free space is low
2. Add a migration dry-run command:
   - inspect tracked/untracked files
   - list ignored runtime files
   - produce a copy plan for `D:\ParasiteOS\Repos\ARADHYA`
   - do not move files automatically
3. Complete Federation Transport:
   - implement signed identity envelopes
   - implement peer trust prompts
4. Add watcher-backed context invalidation:
   - dirty roots
   - miss debouncing
   - targeted refresh before full refresh
