# Parasite OS Progress Tracker

Last updated: 2026-05-27

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
| OpenRouter provider | Done | Optional cloud provider through env key |
| Cloud privacy gate | Done | Blocks secrets, local paths, and private runtime markers before OpenRouter calls |
| Model worker registry | Done | `/model workers` and `/model workers assess <text>` |
| Public API catalog | Done | `/apis`, search, category, inspect, recommend |
| Host repo digestion batch | Done | 14 active host repos completed the 7-stage Parasite pipeline after fast-forward pulls |
| Host integration ledger | Done | `/parasite candidates`, `/parasite inspect <repo>`, and ledger JSON ranking are implemented |
| First agency skill promotion | Done | `agency-engineering-review` is a text-only skill promoted from `agency-agents` engineering notes |
| Topology manifest | Done | Local device capability scaffold |
| Path portability layer | Done | `ARADHYA_HOME`, `parasite.toml`, and `~/.aradhya` resolution now centralize runtime paths |
| Runtime permission rules | Done | User/project allow and deny rules load through the permission engine; deny rules win |
| Hook engine foundation | Done | User/project hook configs support session and tool lifecycle events |
| Agent definitions | Done | User/project Markdown agent definitions load with frontmatter metadata |
| Session/state hardening | Done | Session management, history compression, and SQLite state primitives are in place |
| Timeout kill switch | Done | Agent loop guardrails include iteration and repeated-tool limits |
| LAN federation foundation | Started | Identity, peer registry, doctor command; transport is not complete |
| Opus coordination notes | Done | `docs/OPUS_HANDOFF.md` |
| Generated artifact cleanup | Started | `data/processed/pytest_*` artifacts are being removed from tracking and ignored |
| Full user acceptance loop | Partial | Unit and doctor checks are required before push; interactive launcher smoke still needs manual/new-terminal verification |

## Host Repo Digestion Run - 2026-05-19

Refresh result: all undigested clean host repos were pulled with `--ff-only`.
`public-apis` was skipped during pull because its verified catalog had already
been absorbed.

Archive result: `public-apis` was moved to
`Hosts\.archived\public-apis-20260519-224407` after confirming that
`data\processed\context\public_apis_catalog.json` existed and matched the
verified catalog hash.

Digestion result: these active host repos completed `7/7` stages with empty
errors, `VALIDATE.artifacts.passed = true`, `ABSORB.status = completed`, and a
generated `.parasite\DIGEST.md`:

`claude-code`, `nanoclaw`, `picoclaw`, `agency-agents`, `Scrapegraph-ai`,
`owl`, `nanobot`, `career-ops`, `gstack`, `zeroclaw`, `openhuman`,
`agent-teams-ai`, `ruflo`, `openclaw`.

Deletion state: keep the newly digested code repos in `Hosts\` for now. Their
checkpoints and digests are complete, but they need a second-pass artifact
review before archive/delete decisions because most did not copy live code
artifacts into Aradhya.

## Host Integration Ledger - 2026-05-19

Implemented commands:

- `/parasite candidates` ranks active and archived host repos for second-pass
  integration and writes
  `data\processed\context\host_integration_ledger.json`.
- `/parasite inspect <repo>` shows one repo's capabilities, expected benefits,
  absorbed artifacts, and next review gate.
- `/parasite ledger` refreshes the JSON ledger without showing the full table.

First promoted artifact:

- `core\skills\agency-engineering-review\SKILL.md`
- Source: `Hosts\agency-agents` engineering review, minimal-change,
  architecture, and technical-writing notes.
- Mode: text-only; no imported executable code.
- Purpose: improve code review, minimal diffs, architecture tradeoff analysis,
  and developer documentation quality.

## Not Done Yet

| Area | Status | Next gate |
| --- | --- | --- |
| Drive migration | Not started | Copy repo to `D:\ParasiteOS\Repos\ARADHYA`, run doctor/tests from there |
| Portable runtime profile | Partial | Validate copied-workspace behavior and remove any remaining generated absolute-path assumptions |
| LAN discovery and pairing | Not started | Signed peer handshake and trust prompt |
| Federation transport | Not started | Local-only message envelope with replay protection |
| Watcher-driven context index | Not started | Replace repeated full scans with dirty-root invalidation |
| Browser operator | Not started | Draft-before-submit workflow with confirmation |
| Screen guidance | Not started | Screenshot-guided mode, no continuous frame stream |
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

1. Finish repository hygiene:
   - keep `data/processed/pytest_*` ignored
   - keep runtime caches and local state out of Git
   - verify docs, unit tests, and doctor before push
2. Add a storage profile command:
   - show current repo path
   - detect available drives
   - recommend storage roles
   - warn when active drive free space is low
3. Add a migration dry-run command:
   - inspect tracked/untracked files
   - list ignored runtime files
   - produce a copy plan for `D:\ParasiteOS\Repos\ARADHYA`
   - do not move files automatically
4. Add federation pairing:
   - local peer discovery scaffold
   - signed identity envelope
   - explicit trust prompt
5. Add watcher-backed context invalidation:
   - dirty roots
   - miss debouncing
   - targeted refresh before full refresh

## Manual User Tasks

Current user tasks:

1. Keep the new OpenRouter keys only in environment variables.
2. Create the `D:\ParasiteOS` folder layout when ready.
3. Do not install a separate OS for Parasite OS yet.
4. Keep the Samsung T9 connected during any migration test.
5. Run migration tests only on a copied repo until all gates pass.
