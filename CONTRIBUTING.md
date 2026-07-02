# Contributing to Aradhya

Thank you for your interest in contributing to Aradhya!

## Quick Start

```bash
# Clone and setup
git clone https://github.com/Saurabh0003M/ARADHYA.git
cd ARADHYA

# Run the interactive setup
python -m src.aradhya.setup_wizard

# Or manual setup
pip install -r requirements.txt
# Edit core/config/profile.local.json with your model settings

# Run tests
python -m pytest tests/ --override-ini="addopts=" -q

# Start Aradhya
python -m src.aradhya.main
```

## Development Guidelines

### Code Style
- Python 3.10+ with `from __future__ import annotations`
- Use `loguru` for logging, never stdlib `logging`
- Use `rich` for terminal output via `src/aradhya/ui/cli.py`, never raw `print()`
- Follow existing patterns in the codebase

### Adding a New Skill
The easiest way to contribute! No Python needed:

1. Create `core/skills/<your-skill>/SKILL.md`
2. Add YAML frontmatter: `name`, `description`, `intents`
3. Write Markdown instructions for the AI
4. It auto-loads on next startup

### Adding a New Tool
1. Add your function in `src/aradhya/tools/<category>.py`
2. Register it in `assistant_core.py` `_build_tool_registry()`
3. If dangerous, add to `dangerous_tools` in `agent_loop.py`
4. Add a unit test in `tests/unit/`

### Pull Requests
- One PR = one feature or fix
- Include tests for new functionality
- Run `pytest` before submitting
- Keep PRs focused and reviewable

### Pre-commit Hooks

We recommend installing [pre-commit](https://pre-commit.com/) to run
automated checks before every commit:

```bash
pip install pre-commit
pre-commit install
```

Once installed, hooks will run automatically on `git commit`. To run them
manually against all files:

```bash
pre-commit run --all-files
```

### Linting & Formatting

The project uses the following tools—run them before submitting a PR:

```bash
# Lint with ruff
ruff check src/ tests/

# Auto-format with black
black src/ tests/

# Sort imports with isort
isort src/ tests/
```

Configuration for `black` and `isort` lives in `pyproject.toml`.

## License

Aradhya is released under the **GNU General Public License v3.0**.
By submitting a pull request you agree that your contribution will be
licensed under the same [GPL-3.0-or-later](LICENSE) terms.

## Architecture

See [AGENTS.md](AGENTS.md) for the full architecture reference.

## Questions?

Open an issue with the `question` label.
