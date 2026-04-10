Review this repository strictly from a first-time Windows user perspective.
Assume this project is intended specifically for Windows users, not
cross-platform users.

Inspect the current repo/workspace state, including uncommitted changes if
visible in your environment. Focus especially on:

- `README.md`
- `WINDOWS_SETUP_GUIDE.md`
- `core/memory/profile.json`
- `scripts/setup.bat`
- `scripts/run_agent.bat`
- `src/aradhya/main.py`
- `src/aradhya/model_provider.py`
- `src/aradhya/model_setup.py`
- `src/aradhya/runtime_profile.py`
- `src/aradhya/assistant_indexer.py`

Answer these questions:

1. Can a brand-new Windows user simply clone this and use it directly, or are
   there hidden prerequisites?
2. Is the project portable across Windows machines and folder locations?
3. Does model onboarding work well?
   - If one Ollama model exists, does it auto-select it?
   - If multiple models exist, does it show a numbered full-name catalog?
   - If no models exist, does it suggest models clearly?
4. Are model suggestions based on actual laptop diagnostics like
   RAM/CPU/GPU/VRAM, or are they static?
5. If the Ollama model storage location changes, will this project detect it
   automatically?
6. Should model discovery use `project_tree.txt`, direct filesystem scanning,
   the Ollama API, or a combination? Explain with concrete reasoning.
7. Are the docs, setup scripts, and runtime behavior aligned for a fresh
   Windows user?

Rules:

- Be critical and concrete.
- Do not praise by default.
- Focus on first-run experience, portability, model detection, diagnostics, and
  setup clarity.
- Prefer citing exact files and behaviors over general opinions.

Output format:

- Fresh-user verdict: 1 short paragraph
- What already works: flat bullet list
- What is still missing: flat bullet list
- Incorrect assumptions or UX mismatches: flat bullet list
- Recommended next improvements in priority order: numbered list
- Important file references: exact files that support your conclusions
