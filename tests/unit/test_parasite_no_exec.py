"""Tripwire: the Parasite digestion pipeline must never *execute* host code.

ARADHYA "digests" third-party repositories dropped into ``Hosts/`` by analysing
them **statically** and emitting prompt-level ``SKILL.md`` capabilities. It must
never run, import, or shell out to ingested repository code — that would turn an
untrusted repo into arbitrary code execution inside the agent.

This test parses every module in ``src/aradhya/parasite`` with the ``ast`` module
and fails if any dynamic-execution primitive appears. It is a deliberate tripwire:
if a future change genuinely needs one of these (it almost certainly should not),
the author must consciously update this guard and justify why the invariant still
holds.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PARASITE_DIR = Path(__file__).resolve().parents[2] / "src" / "aradhya" / "parasite"

# Modules that must never dynamically execute or import ingested code.
FORBIDDEN_IMPORTS = {"subprocess", "runpy", "importlib", "pty", "commands"}
FORBIDDEN_CALLS = {"exec", "eval", "__import__", "compile"}
# Attribute names that are unambiguous process/exec primitives on any owner,
# e.g. os.system(...), os.popen(...), os.spawnv(...), os.execv(...).
FORBIDDEN_ATTR_ALWAYS = {"system", "popen", "Popen", "execv", "execve", "execvp", "spawnv", "spawnl", "spawnvp"}
# Generic method names (run/call/...) only count as violations when invoked on a
# process module, so innocent ``foo.run()`` methods do not trip the guard.
PROCESS_OWNERS = {"subprocess", "sp", "os", "runpy"}
FORBIDDEN_OWNER_METHODS = {"run", "call", "check_output", "check_call", "Popen", "spawn"}


def _parasite_modules() -> list[Path]:
    return sorted(p for p in PARASITE_DIR.rglob("*.py") if "__pycache__" not in p.parts)


def test_parasite_dir_exists() -> None:
    assert PARASITE_DIR.is_dir(), f"expected parasite package at {PARASITE_DIR}"
    assert _parasite_modules(), "no parasite modules found to scan"


@pytest.mark.parametrize("module_path", _parasite_modules(), ids=lambda p: p.name)
def test_no_dynamic_execution_in_parasite(module_path: Path) -> None:
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    violations: list[str] = []

    for node in ast.walk(tree):
        # import subprocess / runpy / importlib ...
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in FORBIDDEN_IMPORTS:
                    violations.append(f"line {node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in FORBIDDEN_IMPORTS:
                violations.append(f"line {node.lineno}: from {node.module} import ...")
        # exec(...) / eval(...) / __import__(...) / compile(...)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in FORBIDDEN_CALLS:
                violations.append(f"line {node.lineno}: {func.id}(...)")
            elif isinstance(func, ast.Attribute):
                owner = getattr(func.value, "id", getattr(func.value, "attr", None))
                if func.attr in FORBIDDEN_ATTR_ALWAYS:
                    # e.g. os.system(...), os.execv(...) — dangerous on any owner.
                    violations.append(f"line {node.lineno}: {owner}.{func.attr}(...)")
                elif func.attr in FORBIDDEN_OWNER_METHODS and owner in PROCESS_OWNERS:
                    # e.g. subprocess.run(...), os.popen(...) — but not foo.run().
                    violations.append(f"line {node.lineno}: {owner}.{func.attr}(...)")

    assert not violations, (
        f"Parasite digestion must not execute host code, but {module_path.name} "
        f"contains dynamic-execution primitives: {violations}. "
        "If this is intentional, update this tripwire and justify the invariant."
    )
