"""Directory index refresh logic for local data awareness."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexSnapshot,
)


class DirectoryIndexManager:
    """Writes a text snapshot of the visible directory tree."""

    def __init__(self, preferences: AssistantPreferences):
        self.preferences = preferences
        self._ignored_names = {
            name.lower() for name in preferences.directory_index_policy.ignored_names
        }

    def refresh(self, reason: str) -> DirectoryIndexSnapshot:
        generated_at = datetime.now()
        lines = [
            "# Aradhya directory index",
            f"generated_at={generated_at.isoformat()}",
            f"reason={reason}",
        ]
        node_count = 0
        truncated = False
        scanned_roots: list[str] = []

        for root in self.preferences.user_roots:
            if not root.exists():
                continue

            scanned_roots.append(str(root))
            lines.append("")
            lines.append(f"[ROOT] {root}")

            for current_root, dirnames, filenames in os.walk(
                root,
                topdown=True,
                onerror=lambda _error: None,
            ):
                dirnames[:] = [
                    dirname
                    for dirname in sorted(dirnames)
                    if not self._should_ignore_name(dirname)
                ]
                visible_files = [
                    filename
                    for filename in sorted(filenames)
                    if not self._should_ignore_name(filename)
                ]

                current_path = Path(current_root)
                depth = self._depth_from_root(current_path, root)
                label = current_path.name or str(current_path)
                lines.append(f"{'  ' * depth}[D] {label}")
                node_count += 1

                if self._hit_limit(node_count):
                    truncated = True
                    break

                file_indent = "  " * (depth + 1)
                for filename in visible_files:
                    lines.append(f"{file_indent}[F] {filename}")
                    node_count += 1

                    if self._hit_limit(node_count):
                        truncated = True
                        break

                if truncated:
                    break

            if truncated:
                break

        if truncated:
            lines.append("")
            lines.append(
                f"# Index truncated after {node_count} nodes to keep refreshes responsive."
            )

        output_path = self.preferences.directory_index_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        return DirectoryIndexSnapshot(
            path=output_path,
            generated_at=generated_at,
            reason=reason,
            scanned_roots=tuple(scanned_roots),
            node_count=node_count,
            truncated=truncated,
        )

    def _depth_from_root(self, current_path: Path, root: Path) -> int:
        try:
            relative_path = current_path.relative_to(root)
        except ValueError:
            return 0

        if relative_path == Path("."):
            return 0

        return len(relative_path.parts)

    def _hit_limit(self, node_count: int) -> bool:
        limit = self.preferences.directory_index_policy.max_nodes
        return limit is not None and node_count >= limit

    def _should_ignore_name(self, name: str) -> bool:
        return name.lower() in self._ignored_names
