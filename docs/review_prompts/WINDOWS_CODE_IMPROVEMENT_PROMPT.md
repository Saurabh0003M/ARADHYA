You are reviewing and improving a Windows-only local AI assistant project. Do
not limit yourself to commentary: if you find meaningful gaps, you may
implement improvements directly in code.

Project intent:

- Windows-first user experience
- Local Ollama-backed model usage
- Good first-run onboarding
- Clear diagnostics and error messages
- Practical portability across Windows machines and folder locations

Focus especially on these gaps:

- Better first-run setup for Windows users
- Better prerequisite detection for Python, Git, Ollama, and optional voice
  dependencies
- Hardware-aware model recommendation based on laptop specs such as
  RAM/CPU/GPU/VRAM
- Detection/explanation of Ollama model storage location changes
- Better model onboarding:
  - auto-use the only installed model
  - numbered installed-model selection when multiple models exist
  - numbered recommended catalog when no models exist
- Better remediation messages when errors occur
- Alignment between docs, setup scripts, and runtime behavior
- Correct reasoning about why model discovery should use the Ollama API rather
  than `project_tree.txt` as the main source of truth

Inspect the current repo/workspace state, including uncommitted changes if
visible in your environment. Prioritize these files:

- `README.md`
- `WINDOWS_SETUP_GUIDE.md`
- `scripts/setup.bat`
- `scripts/run_agent.bat`
- `core/memory/profile.json`
- `src/aradhya/main.py`
- `src/aradhya/model_provider.py`
- `src/aradhya/model_setup.py`
- `src/aradhya/runtime_profile.py`
- `src/aradhya/assistant_indexer.py`

Instructions:

- If your environment allows editing, make the improvements directly.
- If direct editing is not possible, provide unified diffs or full replacement
  file contents.
- Do not make random stylistic refactors.
- Make only practical changes that improve the Windows first-run experience,
  diagnostics, onboarding, or portability.
- Preserve existing behavior unless there is a strong reason to change it.
- If you recommend a behavior change, explain why it is better for a first-time
  Windows user.

Output format:

- Summary of the most important problems found
- Concrete improvements made or proposed
- Exact files changed or that should change
- Patch / diff / replacement code
- Remaining limitations after your changes
- Any assumptions you had to make
