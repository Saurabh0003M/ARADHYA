"""Directory summary and compact context-cache logic for local data awareness."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterator

from loguru import logger

from src.aradhya.assistant_models import (
    AssistantPreferences,
    DirectoryIndexSnapshot,
)

SCHEMA_VERSION = 1
SUMMARY_DEPTH = 2
MISC_DRIVE_KEY = "misc"


@dataclass(frozen=True)
class CachedPathCandidate:
    """Compact lookup record for a file-system path candidate."""

    path: str
    is_dir: bool
    depth: int
    mtime: float

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "is_dir": self.is_dir,
            "depth": self.depth,
            "mtime": self.mtime,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CachedPathCandidate":
        return cls(
            path=str(payload.get("path", "")),
            is_dir=bool(payload.get("is_dir", False)),
            depth=int(payload.get("depth", 0)),
            mtime=float(payload.get("mtime", 0.0)),
        )


@dataclass(frozen=True)
class CachedTxtFolder:
    """Precomputed directory text-density statistics."""

    path: str
    txt_count: int
    visible_file_count: int
    density: float
    depth: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "txt_count": self.txt_count,
            "visible_file_count": self.visible_file_count,
            "density": self.density,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CachedTxtFolder":
        return cls(
            path=str(payload.get("path", "")),
            txt_count=int(payload.get("txt_count", 0)),
            visible_file_count=int(payload.get("visible_file_count", 0)),
            density=float(payload.get("density", 0.0)),
            depth=int(payload.get("depth", 0)),
        )


@dataclass(frozen=True)
class CachedTimedCandidate:
    """Cached candidate that is ranked by activity time."""

    path: str
    latest_activity: float
    depth: int

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "latest_activity": self.latest_activity,
            "depth": self.depth,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "CachedTimedCandidate":
        return cls(
            path=str(payload.get("path", "")),
            latest_activity=float(payload.get("latest_activity", 0.0)),
            depth=int(payload.get("depth", 0)),
        )


@dataclass(frozen=True)
class ContextCacheManifest:
    """Top-level metadata for the per-drive context cache."""

    schema_version: int
    generated_at: datetime
    refresh_interval_seconds: int
    indexed_roots: tuple[str, ...]
    game_roots: tuple[str, ...]
    shards: dict[str, str]
    total_indexed_nodes: int
    summary_node_count: int
    summary_truncated: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "generated_at": self.generated_at.isoformat(),
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "indexed_roots": list(self.indexed_roots),
            "game_roots": list(self.game_roots),
            "shards": self.shards,
            "total_indexed_nodes": self.total_indexed_nodes,
            "summary_node_count": self.summary_node_count,
            "summary_truncated": self.summary_truncated,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ContextCacheManifest":
        generated_at = datetime.fromisoformat(str(payload.get("generated_at", "")))
        raw_shards = payload.get("shards", {})
        shards = (
            {str(key): str(value) for key, value in raw_shards.items()}
            if isinstance(raw_shards, dict)
            else {}
        )
        return cls(
            schema_version=int(payload.get("schema_version", 0)),
            generated_at=generated_at,
            refresh_interval_seconds=int(payload.get("refresh_interval_seconds", 0)),
            indexed_roots=tuple(str(item) for item in payload.get("indexed_roots", [])),
            game_roots=tuple(str(item) for item in payload.get("game_roots", [])),
            shards=shards,
            total_indexed_nodes=int(payload.get("total_indexed_nodes", 0)),
            summary_node_count=int(payload.get("summary_node_count", 0)),
            summary_truncated=bool(payload.get("summary_truncated", False)),
        )

@dataclass(frozen=True)
class DriveCacheShard:
    """Compact per-drive shard used for runtime local lookups."""

    drive_key: str
    user_roots: tuple[str, ...]
    game_roots: tuple[str, ...]
    name_candidates: dict[str, tuple[CachedPathCandidate, ...]]
    txt_folders: tuple[CachedTxtFolder, ...]
    projects: tuple[CachedTimedCandidate, ...]
    games: tuple[CachedTimedCandidate, ...]
    shallow_outline: dict[str, tuple[str, ...]]
    directory_count: int
    file_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "drive_key": self.drive_key,
            "user_roots": list(self.user_roots),
            "game_roots": list(self.game_roots),
            "name_candidates": {
                key: [candidate.to_dict() for candidate in candidates]
                for key, candidates in self.name_candidates.items()
            },
            "txt_folders": [folder.to_dict() for folder in self.txt_folders],
            "projects": [candidate.to_dict() for candidate in self.projects],
            "games": [candidate.to_dict() for candidate in self.games],
            "shallow_outline": {
                key: list(lines) for key, lines in self.shallow_outline.items()
            },
            "directory_count": self.directory_count,
            "file_count": self.file_count,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "DriveCacheShard":
        raw_name_candidates = payload.get("name_candidates", {})
        raw_outline = payload.get("shallow_outline", {})
        return cls(
            drive_key=str(payload.get("drive_key", MISC_DRIVE_KEY)),
            user_roots=tuple(str(item) for item in payload.get("user_roots", [])),
            game_roots=tuple(str(item) for item in payload.get("game_roots", [])),
            name_candidates={
                str(key): tuple(
                    CachedPathCandidate.from_dict(candidate)
                    for candidate in candidates
                    if isinstance(candidate, dict)
                )
                for key, candidates in raw_name_candidates.items()
                if isinstance(candidates, list)
            }
            if isinstance(raw_name_candidates, dict)
            else {},
            txt_folders=tuple(
                CachedTxtFolder.from_dict(item)
                for item in payload.get("txt_folders", [])
                if isinstance(item, dict)
            ),
            projects=tuple(
                CachedTimedCandidate.from_dict(item)
                for item in payload.get("projects", [])
                if isinstance(item, dict)
            ),
            games=tuple(
                CachedTimedCandidate.from_dict(item)
                for item in payload.get("games", [])
                if isinstance(item, dict)
            ),
            shallow_outline={
                str(key): tuple(str(line) for line in lines)
                for key, lines in raw_outline.items()
                if isinstance(lines, list)
            }
            if isinstance(raw_outline, dict)
            else {},
            directory_count=int(payload.get("directory_count", 0)),
            file_count=int(payload.get("file_count", 0)),
        )


@dataclass
class _DriveAccumulator:
    """Mutable accumulator used while scanning configured roots."""

    drive_key: str
    user_roots: set[str] = field(default_factory=set)
    game_roots: set[str] = field(default_factory=set)
    name_candidates: dict[str, list[CachedPathCandidate]] = field(
        default_factory=lambda: defaultdict(list)
    )
    txt_folders: list[CachedTxtFolder] = field(default_factory=list)
    project_paths: set[str] = field(default_factory=set)
    games: list[CachedTimedCandidate] = field(default_factory=list)
    shallow_outline: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    directory_count: int = 0
    file_count: int = 0


class DirectoryIndexManager:
    """Maintains a compact context cache plus a summary tree artifact."""

    def __init__(
        self,
        preferences: AssistantPreferences,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.preferences = preferences
        self.now_provider = now_provider or datetime.now
        self._ignored_names = {
            name.lower() for name in preferences.directory_index_policy.ignored_names
        }
        self._manifest_path = self.preferences.context_cache_dir / "manifest.json"
        self._last_snapshot: DirectoryIndexSnapshot | None = None

    @property
    def last_snapshot(self) -> DirectoryIndexSnapshot | None:
        """Return the latest refresh or cache-reuse snapshot."""

        return self._last_snapshot

    def refresh(self, reason: str) -> DirectoryIndexSnapshot:
        """Force a full rebuild of all configured context caches."""

        return self._rebuild_cache(
            reason,
            user_roots=self.preferences.user_roots,
            game_roots=self.preferences.game_library_roots,
        )

    def refresh_if_stale(self, reason: str) -> DirectoryIndexSnapshot:
        """Reuse a fresh cache or rebuild it if missing, invalid, or stale."""

        try:
            manifest, _shards = self._load_cache()
        except ValueError:
            return self.refresh(reason)

        if not self.preferences.directory_index_path.exists():
            return self.refresh(reason)

        if self._is_manifest_stale(manifest):
            return self.refresh(reason)

        snapshot = DirectoryIndexSnapshot(
            path=self.preferences.directory_index_path,
            generated_at=manifest.generated_at,
            reason=reason,
            scanned_roots=manifest.indexed_roots,
            node_count=manifest.summary_node_count,
            truncated=manifest.summary_truncated,
            refreshed=False,
        )
        self._last_snapshot = snapshot
        return snapshot

    def find_named_paths(self, query: str, limit: int = 10, reason: str = "local_query") -> list[Path]:
        """Return cached path candidates for an open-path style query."""

        snapshot = self.refresh_if_stale(reason)
        _manifest, shards = self._load_cache()
        matches = self._lookup_named_paths(shards, query, limit)
        if matches or snapshot.refreshed:
            return matches

        self._refresh_relevant_roots(reason, user_roots=self.preferences.user_roots)
        _manifest, shards = self._load_cache()
        return self._lookup_named_paths(shards, query, limit)

    def find_txt_dense_folder(
        self,
        reason: str = "local_query",
    ) -> tuple[Path, int, float] | None:
        """Return the strongest cached text-density folder."""

        snapshot = self.refresh_if_stale(reason)
        _manifest, shards = self._load_cache()
        candidate = self._lookup_txt_dense_folder(shards)
        if candidate is not None or snapshot.refreshed:
            return candidate

        self._refresh_relevant_roots(reason, user_roots=self.preferences.user_roots)
        _manifest, shards = self._load_cache()
        return self._lookup_txt_dense_folder(shards)

    def find_yesterdays_project(
        self,
        now: datetime,
        reason: str = "local_query",
    ) -> tuple[Path, datetime] | None:
        """Return the strongest cached project candidate from yesterday."""

        snapshot = self.refresh_if_stale(reason)
        _manifest, shards = self._load_cache()
        candidate = self._lookup_yesterdays_project(shards, now)
        if candidate is not None or snapshot.refreshed:
            return candidate

        self._refresh_relevant_roots(reason, user_roots=self.preferences.user_roots)
        _manifest, shards = self._load_cache()
        return self._lookup_yesterdays_project(shards, now)

    def find_recent_game(
        self,
        reason: str = "local_query",
    ) -> tuple[Path, datetime] | None:
        """Return the most recently updated cached game candidate."""

        snapshot = self.refresh_if_stale(reason)
        _manifest, shards = self._load_cache()
        candidate = self._lookup_recent_game(shards)
        if candidate is not None or snapshot.refreshed:
            return candidate

        self._refresh_relevant_roots(reason, game_roots=self.preferences.game_library_roots)
        _manifest, shards = self._load_cache()
        return self._lookup_recent_game(shards)

    def _refresh_relevant_roots(
        self,
        reason: str,
        *,
        user_roots: tuple[Path, ...] = (),
        game_roots: tuple[Path, ...] = (),
    ) -> DirectoryIndexSnapshot:
        try:
            manifest, existing_shards = self._load_cache()
        except ValueError:
            return self.refresh(reason)

        affected_drive_keys = {
            self._drive_key_for_path(path)
            for path in (*user_roots, *game_roots)
            if path.exists()
        }
        if not affected_drive_keys:
            self._last_snapshot = DirectoryIndexSnapshot(
                path=self.preferences.directory_index_path,
                generated_at=manifest.generated_at,
                reason=reason,
                scanned_roots=manifest.indexed_roots,
                node_count=manifest.summary_node_count,
                truncated=manifest.summary_truncated,
                refreshed=False,
            )
            return self._last_snapshot

        selected_user_roots = tuple(
            root
            for root in self.preferences.user_roots
            if root.exists() and self._drive_key_for_path(root) in affected_drive_keys
        )
        selected_game_roots = tuple(
            root
            for root in self.preferences.game_library_roots
            if root.exists() and self._drive_key_for_path(root) in affected_drive_keys
        )
        return self._rebuild_cache(
            reason,
            user_roots=selected_user_roots,
            game_roots=selected_game_roots,
            base_manifest=manifest,
            base_shards=existing_shards,
        )

    def _rebuild_cache(
        self,
        reason: str,
        *,
        user_roots: tuple[Path, ...],
        game_roots: tuple[Path, ...],
        base_manifest: ContextCacheManifest | None = None,
        base_shards: dict[str, DriveCacheShard] | None = None,
    ) -> DirectoryIndexSnapshot:
        generated_at = self.now_provider()
        accumulators = self._scan_roots(user_roots, game_roots)
        updated_shards = {
            key: self._finalize_drive_shard(accumulator) for key, accumulator in accumulators.items()
        }

        if base_shards is not None:
            final_shards = {
                key: shard
                for key, shard in base_shards.items()
                if key not in updated_shards
            }
            final_shards.update(updated_shards)
        else:
            final_shards = updated_shards

        summary_node_count, summary_truncated = self._write_summary_artifact(
            final_shards,
            generated_at=generated_at,
            reason=reason,
            refreshed=True,
        )
        self.preferences.context_cache_dir.mkdir(parents=True, exist_ok=True)

        manifest = ContextCacheManifest(
            schema_version=SCHEMA_VERSION,
            generated_at=generated_at,
            refresh_interval_seconds=self.preferences.directory_index_policy.refresh_interval_seconds,
            indexed_roots=tuple(str(root) for root in self.preferences.user_roots if root.exists()),
            game_roots=tuple(str(root) for root in self.preferences.game_library_roots if root.exists()),
            shards={
                drive_key: self._shard_filename(drive_key)
                for drive_key in sorted(final_shards)
            },
            total_indexed_nodes=sum(
                shard.directory_count + shard.file_count for shard in final_shards.values()
            ),
            summary_node_count=summary_node_count,
            summary_truncated=summary_truncated,
        )
        self._write_manifest(manifest)
        self._write_shards(final_shards)

        snapshot = DirectoryIndexSnapshot(
            path=self.preferences.directory_index_path,
            generated_at=generated_at,
            reason=reason,
            scanned_roots=manifest.indexed_roots,
            node_count=summary_node_count,
            truncated=summary_truncated,
            refreshed=True,
        )
        self._last_snapshot = snapshot
        return snapshot

    def _scan_roots(
        self,
        user_roots: tuple[Path, ...],
        game_roots: tuple[Path, ...],
    ) -> dict[str, _DriveAccumulator]:
        accumulators: dict[str, _DriveAccumulator] = {}

        for root in user_roots:
            if root.exists():
                drive_key = self._drive_key_for_path(root)
                accumulator = accumulators.setdefault(drive_key, _DriveAccumulator(drive_key))
                self._scan_user_root(root, accumulator)

        for root in game_roots:
            if root.exists():
                drive_key = self._drive_key_for_path(root)
                accumulator = accumulators.setdefault(drive_key, _DriveAccumulator(drive_key))
                self._scan_game_root(root, accumulator)

        return accumulators

    def _walk_tree(self, root: Path) -> Iterator[tuple[str, list[str], list[str]]]:
        """Walk a tree while surfacing inaccessible paths in the logs."""

        def handle_error(error: OSError) -> None:
            location = error.filename or str(root)
            logger.warning(
                "Skipping inaccessible path during directory scan at {}: {}",
                location,
                error,
            )

        yield from os.walk(root, topdown=True, onerror=handle_error)

    def _scan_user_root(self, root: Path, accumulator: _DriveAccumulator) -> None:
        root_label = str(root)
        accumulator.user_roots.add(root_label)
        marker_names = {marker.lower() for marker in self.preferences.project_markers}

        for current_root, dirnames, filenames in self._walk_tree(root):
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
            accumulator.directory_count += 1
            self._store_name_candidate(
                accumulator.name_candidates,
                self._normalize_key(current_path.name or current_path.drive or current_path.anchor),
                CachedPathCandidate(
                    path=str(current_path),
                    is_dir=True,
                    depth=depth,
                    mtime=self._safe_timestamp(current_path) or 0.0,
                ),
            )
            self._record_outline(accumulator, root_label, current_path, root)

            if visible_files:
                accumulator.file_count += len(visible_files)

            txt_count = sum(
                1
                for filename in visible_files
                if Path(filename).suffix.lower() == ".txt"
            )
            if txt_count > 0 and visible_files:
                accumulator.txt_folders.append(
                    CachedTxtFolder(
                        path=str(current_path),
                        txt_count=txt_count,
                        visible_file_count=len(visible_files),
                        density=txt_count / len(visible_files),
                        depth=depth,
                    )
                )

            if any(filename.lower() in marker_names for filename in visible_files):
                accumulator.project_paths.add(str(current_path))

            for filename in visible_files:
                file_path = current_path / filename
                self._store_name_candidate(
                    accumulator.name_candidates,
                    self._normalize_key(file_path.name),
                    CachedPathCandidate(
                        path=str(file_path),
                        is_dir=False,
                        depth=depth + 1,
                        mtime=self._safe_timestamp(file_path) or 0.0,
                    ),
                )

    def _scan_game_root(self, root: Path, accumulator: _DriveAccumulator) -> None:
        accumulator.game_roots.add(str(root))
        blocked_tokens = ("crash", "unins", "setup", "redistributable")
        for current_root, dirnames, filenames in self._walk_tree(root):
            dirnames[:] = [
                dirname
                for dirname in sorted(dirnames)
                if not self._should_ignore_name(dirname)
            ]
            current_path = Path(current_root)
            depth = self._depth_from_root(current_path, root)

            for filename in sorted(filenames):
                lowered_name = filename.lower()
                if self._should_ignore_name(filename):
                    continue
                if not lowered_name.endswith((".exe", ".lnk")):
                    continue
                if any(token in lowered_name for token in blocked_tokens):
                    continue

                candidate_path = current_path / filename
                timestamp = self._safe_timestamp(candidate_path)
                if timestamp is None:
                    continue

                accumulator.games.append(
                    CachedTimedCandidate(
                        path=str(candidate_path),
                        latest_activity=timestamp,
                        depth=depth + 1,
                    )
                )

    def _finalize_drive_shard(self, accumulator: _DriveAccumulator) -> DriveCacheShard:
        projects = [
            CachedTimedCandidate(
                path=project_path,
                latest_activity=self._estimate_project_activity(Path(project_path)),
                depth=self._safe_relative_depth(Path(project_path), accumulator.user_roots),
            )
            for project_path in sorted(accumulator.project_paths)
        ]
        projects = [candidate for candidate in projects if candidate.latest_activity > 0]

        deduped_games = self._dedupe_timed_candidates(accumulator.games)
        sorted_txt_folders = sorted(
            self._dedupe_txt_folders(accumulator.txt_folders),
            key=lambda folder: (folder.txt_count, folder.density, -folder.depth),
            reverse=True,
        )
        return DriveCacheShard(
            drive_key=accumulator.drive_key,
            user_roots=tuple(sorted(accumulator.user_roots)),
            game_roots=tuple(sorted(accumulator.game_roots)),
            name_candidates={
                key: tuple(candidates)
                for key, candidates in sorted(accumulator.name_candidates.items())
            },
            txt_folders=tuple(sorted_txt_folders),
            projects=tuple(
                sorted(
                    self._dedupe_timed_candidates(projects),
                    key=lambda candidate: candidate.latest_activity,
                    reverse=True,
                )
            ),
            games=tuple(
                sorted(deduped_games, key=lambda candidate: candidate.latest_activity, reverse=True)
            ),
            shallow_outline={
                root: tuple(lines)
                for root, lines in sorted(accumulator.shallow_outline.items())
            },
            directory_count=accumulator.directory_count,
            file_count=accumulator.file_count,
        )

    def _load_cache(self) -> tuple[ContextCacheManifest, dict[str, DriveCacheShard]]:
        manifest = self._read_manifest()
        shards = {
            drive_key: self._read_shard(filename)
            for drive_key, filename in manifest.shards.items()
        }
        return manifest, shards

    def _read_manifest(self) -> ContextCacheManifest:
        if not self._manifest_path.exists():
            raise ValueError("Context cache manifest does not exist.")

        try:
            payload = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            manifest = ContextCacheManifest.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError("Context cache manifest is invalid.") from error

        if manifest.schema_version != SCHEMA_VERSION:
            raise ValueError("Context cache schema version is outdated.")
        if not self._is_manifest_compatible(manifest):
            raise ValueError("Context cache configuration no longer matches preferences.")
        return manifest

    def _read_shard(self, filename: str) -> DriveCacheShard:
        shard_path = self.preferences.context_cache_dir / filename
        if not shard_path.exists():
            raise ValueError(f"Context cache shard {filename} does not exist.")

        try:
            payload = json.loads(shard_path.read_text(encoding="utf-8"))
            return DriveCacheShard.from_dict(payload)
        except (OSError, json.JSONDecodeError, ValueError) as error:
            raise ValueError(f"Context cache shard {filename} is invalid.") from error

    def _write_manifest(self, manifest: ContextCacheManifest) -> None:
        self._manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2) + "\n",
            encoding="utf-8",
        )

    def _write_shards(self, shards: dict[str, DriveCacheShard]) -> None:
        for drive_key, shard in shards.items():
            shard_path = self.preferences.context_cache_dir / self._shard_filename(drive_key)
            shard_path.write_text(
                json.dumps(shard.to_dict(), indent=2) + "\n",
                encoding="utf-8",
            )

    def _write_summary_artifact(
        self,
        shards: dict[str, DriveCacheShard],
        *,
        generated_at: datetime,
        reason: str,
        refreshed: bool,
    ) -> tuple[int, bool]:
        lines = [
            "# Aradhya directory index summary",
            f"generated_at={generated_at.isoformat()}",
            f"reason={reason}",
            f"refreshed={'true' if refreshed else 'false'}",
            f"context_cache_manifest={self._manifest_path}",
        ]

        node_count = 0
        truncated = False
        limit = self.preferences.directory_index_policy.max_nodes

        for drive_key, shard in sorted(shards.items()):
            lines.append("")
            lines.append(f"[DRIVE] {drive_key}")
            lines.append(
                "  "
                + f"user_roots={len(shard.user_roots)} indexed_names={len(shard.name_candidates)} "
                + f"projects={len(shard.projects)} games={len(shard.games)} "
                + f"txt_dense_dirs={len(shard.txt_folders)}"
            )
            node_count += 2

            for root in shard.user_roots:
                lines.append(f"  [ROOT] {root}")
                node_count += 1
                for outline_line in shard.shallow_outline.get(root, ()):
                    if limit is not None and node_count >= limit:
                        truncated = True
                        break
                    lines.append(outline_line)
                    node_count += 1
                if truncated:
                    break
            if truncated:
                break

        if truncated:
            lines.append("")
            lines.append(
                f"# Summary truncated after {node_count} nodes to keep refreshes responsive."
            )

        output_path = self.preferences.directory_index_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return node_count, truncated

    def _lookup_named_paths(
        self,
        shards: dict[str, DriveCacheShard],
        query: str,
        limit: int,
    ) -> list[Path]:
        normalized_query = self._normalize_key(query)
        if not normalized_query:
            return []

        candidates: list[CachedPathCandidate] = []
        seen_paths: set[str] = set()

        exact_candidates = self._gather_name_candidates(shards, normalized_query)
        for candidate in exact_candidates:
            if candidate.path not in seen_paths:
                seen_paths.add(candidate.path)
                candidates.append(candidate)

        if not candidates:
            for key, shard_candidates in self._iter_name_candidates(shards):
                if normalized_query not in key and key not in normalized_query:
                    continue
                for candidate in shard_candidates:
                    if candidate.path in seen_paths:
                        continue
                    seen_paths.add(candidate.path)
                    candidates.append(candidate)
                    if len(candidates) >= limit:
                        break
                if len(candidates) >= limit:
                    break

        return [Path(candidate.path) for candidate in candidates[:limit]]

    def _lookup_txt_dense_folder(
        self,
        shards: dict[str, DriveCacheShard],
    ) -> tuple[Path, int, float] | None:
        best_candidate: CachedTxtFolder | None = None
        best_score: tuple[int, float, int] | None = None

        for shard in shards.values():
            for candidate in shard.txt_folders:
                score = (candidate.txt_count, candidate.density, -candidate.depth)
                if best_score is None or score > best_score:
                    best_score = score
                    best_candidate = candidate

        if best_candidate is None:
            return None
        return (
            Path(best_candidate.path),
            best_candidate.txt_count,
            best_candidate.density,
        )

    def _lookup_yesterdays_project(
        self,
        shards: dict[str, DriveCacheShard],
        now: datetime,
    ) -> tuple[Path, datetime] | None:
        target_day = (now - timedelta(days=1)).date()
        best_candidate: CachedTimedCandidate | None = None

        for shard in shards.values():
            for candidate in shard.projects:
                activity_time = datetime.fromtimestamp(candidate.latest_activity)
                if activity_time.date() != target_day:
                    continue
                if best_candidate is None or candidate.latest_activity > best_candidate.latest_activity:
                    best_candidate = candidate

        if best_candidate is None:
            return None
        return (
            Path(best_candidate.path),
            datetime.fromtimestamp(best_candidate.latest_activity),
        )

    def _lookup_recent_game(
        self,
        shards: dict[str, DriveCacheShard],
    ) -> tuple[Path, datetime] | None:
        best_candidate: CachedTimedCandidate | None = None

        for shard in shards.values():
            for candidate in shard.games:
                if best_candidate is None or candidate.latest_activity > best_candidate.latest_activity:
                    best_candidate = candidate

        if best_candidate is None:
            return None
        return (
            Path(best_candidate.path),
            datetime.fromtimestamp(best_candidate.latest_activity),
        )

    def _gather_name_candidates(
        self,
        shards: dict[str, DriveCacheShard],
        key: str,
    ) -> tuple[CachedPathCandidate, ...]:
        collected: list[CachedPathCandidate] = []
        seen_paths: set[str] = set()
        for shard in shards.values():
            for candidate in shard.name_candidates.get(key, ()):
                if candidate.path in seen_paths:
                    continue
                seen_paths.add(candidate.path)
                collected.append(candidate)
        return tuple(collected)

    def _iter_name_candidates(
        self,
        shards: dict[str, DriveCacheShard],
    ) -> tuple[tuple[str, tuple[CachedPathCandidate, ...]], ...]:
        items: list[tuple[str, tuple[CachedPathCandidate, ...]]] = []
        for shard in shards.values():
            items.extend(shard.name_candidates.items())
        return tuple(items)

    def _store_name_candidate(
        self,
        mapping: dict[str, list[CachedPathCandidate]],
        key: str,
        candidate: CachedPathCandidate,
    ) -> None:
        if not key:
            return

        candidates = mapping[key]
        if any(existing.path == candidate.path for existing in candidates):
            return

        candidates.append(candidate)
        candidates.sort(key=self._candidate_priority, reverse=True)
        del candidates[self.preferences.directory_index_policy.max_name_candidates_per_key :]

    def _candidate_priority(self, candidate: CachedPathCandidate) -> tuple[int, int, float]:
        return (
            1 if candidate.is_dir else 0,
            -candidate.depth,
            candidate.mtime,
        )

    def _record_outline(
        self,
        accumulator: _DriveAccumulator,
        root_label: str,
        current_path: Path,
        root: Path,
    ) -> None:
        depth = self._depth_from_root(current_path, root)
        if depth == 0 or depth > SUMMARY_DEPTH:
            return

        relative_path = current_path.relative_to(root)
        outline_line = f"{'  ' * (depth + 1)}[D] {relative_path.as_posix()}"
        if outline_line not in accumulator.shallow_outline[root_label]:
            accumulator.shallow_outline[root_label].append(outline_line)

    def _estimate_project_activity(self, project_path: Path) -> float:
        latest_timestamp = self._safe_timestamp(project_path)
        files_seen = 0
        max_files = 500
        max_depth = 3

        for current_root, dirnames, filenames in self._walk_tree(project_path):
            current_path = Path(current_root)
            try:
                depth = len(current_path.relative_to(project_path).parts)
            except ValueError:
                depth = 0
            if depth >= max_depth:
                dirnames[:] = []
            else:
                dirnames[:] = [
                    dirname
                    for dirname in dirnames
                    if not self._should_ignore_name(dirname)
                ]

            for filename in filenames:
                if self._should_ignore_name(filename):
                    continue

                candidate_timestamp = self._safe_timestamp(current_path / filename)
                if candidate_timestamp is not None:
                    latest_timestamp = max(
                        latest_timestamp or candidate_timestamp,
                        candidate_timestamp,
                    )

                files_seen += 1
                if files_seen >= max_files:
                    break

            if files_seen >= max_files:
                break

        return latest_timestamp or 0.0

    def _dedupe_timed_candidates(
        self,
        candidates: list[CachedTimedCandidate],
    ) -> list[CachedTimedCandidate]:
        deduped: dict[str, CachedTimedCandidate] = {}
        for candidate in candidates:
            existing = deduped.get(candidate.path)
            if existing is None or candidate.latest_activity > existing.latest_activity:
                deduped[candidate.path] = candidate
        return list(deduped.values())

    def _dedupe_txt_folders(
        self,
        folders: list[CachedTxtFolder],
    ) -> list[CachedTxtFolder]:
        deduped: dict[str, CachedTxtFolder] = {}
        for folder in folders:
            existing = deduped.get(folder.path)
            if existing is None or (
                folder.txt_count,
                folder.density,
                -folder.depth,
            ) > (
                existing.txt_count,
                existing.density,
                -existing.depth,
            ):
                deduped[folder.path] = folder
        return list(deduped.values())

    def _is_manifest_stale(self, manifest: ContextCacheManifest) -> bool:
        refresh_interval = timedelta(seconds=manifest.refresh_interval_seconds)
        return self.now_provider() - manifest.generated_at > refresh_interval

    def _is_manifest_compatible(self, manifest: ContextCacheManifest) -> bool:
        expected_user_roots = tuple(
            str(root) for root in self.preferences.user_roots if root.exists()
        )
        expected_game_roots = tuple(
            str(root) for root in self.preferences.game_library_roots if root.exists()
        )
        return (
            manifest.refresh_interval_seconds
            == self.preferences.directory_index_policy.refresh_interval_seconds
            and manifest.indexed_roots == expected_user_roots
            and manifest.game_roots == expected_game_roots
        )

    def _safe_relative_depth(self, path: Path, roots: set[str]) -> int:
        best_depth: int | None = None
        for root_str in roots:
            root = Path(root_str)
            try:
                depth = len(path.relative_to(root).parts)
            except ValueError:
                continue
            best_depth = depth if best_depth is None else min(best_depth, depth)
        return best_depth or 0

    def _normalize_key(self, value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    def _depth_from_root(self, current_path: Path, root: Path) -> int:
        try:
            relative_path = current_path.relative_to(root)
        except ValueError:
            return 0

        if relative_path == Path("."):
            return 0
        return len(relative_path.parts)

    def _drive_key_for_path(self, path: Path) -> str:
        drive = path.drive.rstrip(":").upper()
        if drive:
            return drive
        anchor = path.anchor.rstrip("\\/").rstrip(":").upper()
        if anchor:
            return anchor
        return MISC_DRIVE_KEY

    def _shard_filename(self, drive_key: str) -> str:
        safe_drive = re.sub(r"[^A-Za-z0-9_-]+", "_", drive_key)
        return f"drive_{safe_drive}.json"

    def _safe_timestamp(self, path: Path) -> float | None:
        try:
            return path.stat().st_mtime
        except OSError:
            return None

    def _should_ignore_name(self, name: str) -> bool:
        return name.lower() in self._ignored_names
