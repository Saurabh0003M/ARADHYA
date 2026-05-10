"""Validation helpers for Aradhya's directory context cache."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil
from time import perf_counter

from src.aradhya.assistant_indexer import DirectoryIndexManager
from src.aradhya.assistant_models import AssistantPreferences, DirectoryIndexSnapshot


@dataclass(frozen=True)
class CacheValidationReport:
    """Measured outcomes from a cache validation run."""

    cold_snapshot: DirectoryIndexSnapshot
    cold_refresh_seconds: float
    warm_snapshot: DirectoryIndexSnapshot
    warm_refresh_seconds: float
    manifest_path: Path
    shard_paths: tuple[Path, ...]
    exact_query: str | None
    exact_query_seconds: float
    exact_lookup_found: bool
    miss_query: str
    first_miss_query_seconds: float
    repeat_miss_query_seconds: float
    repeat_miss_negative_cached: bool
    targeted_query: str
    targeted_query_seconds: float
    targeted_lookup_found: bool
    targeted_snapshot_refreshed: bool
    targeted_probe_path: Path | None
    cleanup_performed: bool
    targeted_skip_reason: str | None = None


def run_cache_validation(preferences: AssistantPreferences) -> CacheValidationReport:
    """Exercise cold refresh, warm reuse, and targeted rescan behavior."""

    manager = DirectoryIndexManager(preferences)

    cold_start = perf_counter()
    cold_snapshot = manager.refresh("cache_validate_cold")
    cold_refresh_seconds = perf_counter() - cold_start

    manifest_path = preferences.context_cache_dir / "manifest.json"
    shard_paths = tuple(sorted(preferences.context_cache_dir.glob("drive_*.json")))

    warm_start = perf_counter()
    warm_snapshot = manager.refresh_if_stale("cache_validate_warm")
    warm_refresh_seconds = perf_counter() - warm_start

    exact_query = _pick_exact_cached_query(manager, preferences.user_roots)
    exact_query_seconds = 0.0
    exact_lookup_found = False
    if exact_query is not None:
        exact_start = perf_counter()
        exact_matches = manager.find_named_paths(exact_query, reason="cache_validate_exact")
        exact_query_seconds = perf_counter() - exact_start
        exact_lookup_found = bool(exact_matches)

    probe_parent = preferences.context_cache_dir.parent / "cache_validation"
    probe_suffix = cold_snapshot.generated_at.strftime("%Y%m%d%H%M%S%f").translate(
        str.maketrans("0123456789", "abcdefghij")
    )
    miss_query = f"zzqvmiss{probe_suffix}"
    first_miss_start = perf_counter()
    manager.find_named_paths(miss_query, reason="cache_validate_miss_first")
    first_miss_query_seconds = perf_counter() - first_miss_start
    repeat_miss_start = perf_counter()
    manager.find_named_paths(miss_query, reason="cache_validate_miss_repeat")
    repeat_miss_query_seconds = perf_counter() - repeat_miss_start
    repeat_miss_negative_cached = manager._is_negative_lookup_cached(  # noqa: SLF001 - diagnostics validate miss cache behavior
        manager._normalize_key(miss_query)
    )

    targeted_query = f"zzqvprobe{probe_suffix}"
    targeted_probe_path: Path | None = None
    targeted_query_seconds = 0.0
    targeted_lookup_found = False
    targeted_snapshot_refreshed = False
    cleanup_performed = False
    targeted_skip_reason: str | None = None

    if _is_within_user_roots(probe_parent, preferences.user_roots):
        targeted_probe_path = probe_parent / targeted_query
        targeted_probe_path.mkdir(parents=True, exist_ok=False)
        try:
            targeted_start = perf_counter()
            matches = _lookup_exact_cached_paths(manager, targeted_query)
            if targeted_probe_path not in matches:
                manager._refresh_relevant_roots(  # noqa: SLF001 - diagnostics need exact refresh control
                    "cache_validate_targeted",
                    user_roots=preferences.user_roots,
                )
                matches = _lookup_exact_cached_paths(manager, targeted_query)
            targeted_query_seconds = perf_counter() - targeted_start
            targeted_lookup_found = targeted_probe_path in matches
            targeted_snapshot_refreshed = bool(
                manager.last_snapshot and manager.last_snapshot.refreshed
            )
        finally:
            if targeted_probe_path.exists():
                shutil.rmtree(targeted_probe_path)
            cleanup_performed = not targeted_probe_path.exists()
    else:
        targeted_skip_reason = (
            "Configured user roots do not include the git-ignored cache validation area."
        )

    return CacheValidationReport(
        cold_snapshot=cold_snapshot,
        cold_refresh_seconds=cold_refresh_seconds,
        warm_snapshot=warm_snapshot,
        warm_refresh_seconds=warm_refresh_seconds,
        manifest_path=manifest_path,
        shard_paths=shard_paths,
        exact_query=exact_query,
        exact_query_seconds=exact_query_seconds,
        exact_lookup_found=exact_lookup_found,
        miss_query=miss_query,
        first_miss_query_seconds=first_miss_query_seconds,
        repeat_miss_query_seconds=repeat_miss_query_seconds,
        repeat_miss_negative_cached=repeat_miss_negative_cached,
        targeted_query=targeted_query,
        targeted_query_seconds=targeted_query_seconds,
        targeted_lookup_found=targeted_lookup_found,
        targeted_snapshot_refreshed=targeted_snapshot_refreshed,
        targeted_probe_path=targeted_probe_path,
        cleanup_performed=cleanup_performed,
        targeted_skip_reason=targeted_skip_reason,
    )


def format_cache_validation_report(report: CacheValidationReport) -> tuple[str, ...]:
    """Render a human-readable cache validation summary."""

    lines = [
        f"Cache > Summary artifact: {report.cold_snapshot.path}",
        f"Cache > Context manifest: {report.manifest_path}",
        f"Cache > Drive shards: {len(report.shard_paths)}",
        (
            "Cache > Cold refresh: "
            f"{report.cold_refresh_seconds:.3f}s "
            f"({report.cold_snapshot.node_count} summary nodes, refreshed=yes)"
        ),
        (
            "Cache > Warm reuse: "
            f"{report.warm_refresh_seconds:.3f}s "
            f"(refreshed={'yes' if report.warm_snapshot.refreshed else 'no'})"
        ),
        (
            "Cache > Exact lookup: "
            + (
                f"{report.exact_query} ({report.exact_query_seconds:.3f}s, "
                f"found={'yes' if report.exact_lookup_found else 'no'})"
                if report.exact_query is not None
                else "no cached query available"
            )
        ),
        (
            "Cache > Miss lookup: "
            f"{report.miss_query} "
            f"(first={report.first_miss_query_seconds:.3f}s, "
            f"repeat={report.repeat_miss_query_seconds:.3f}s, "
            f"negative_cache={'yes' if report.repeat_miss_negative_cached else 'no'})"
        ),
    ]

    if report.targeted_skip_reason is not None:
        lines.append(f"Cache > Targeted rescan skipped: {report.targeted_skip_reason}")
        return tuple(lines)

    lines.extend(
        [
            (
                "Cache > Targeted query: "
                f"{report.targeted_query} "
                f"({report.targeted_query_seconds:.3f}s)"
            ),
            (
                "Cache > Targeted rescan refreshed: "
                f"{'yes' if report.targeted_snapshot_refreshed else 'no'}"
            ),
            (
                "Cache > Targeted lookup found probe: "
                f"{'yes' if report.targeted_lookup_found else 'no'}"
            ),
            f"Cache > Probe cleanup: {'yes' if report.cleanup_performed else 'no'}",
        ]
    )
    return tuple(lines)


def _is_within_user_roots(path: Path, user_roots: tuple[Path, ...]) -> bool:
    for user_root in user_roots:
        try:
            path.relative_to(user_root)
            return True
        except ValueError:
            continue
    return False


def _lookup_exact_cached_paths(
    manager: DirectoryIndexManager,
    query: str,
) -> tuple[Path, ...]:
    normalized_query = manager._normalize_key(query)  # noqa: SLF001 - diagnostics inspect exact cache keys
    if not normalized_query:
        return tuple()

    _manifest, shards = manager._load_cache()  # noqa: SLF001 - diagnostics inspect cache contents
    return tuple(
        Path(candidate.path)
        for candidate in manager._gather_name_candidates(  # noqa: SLF001 - exact cache lookup only
            shards,
            normalized_query,
        )
    )


def _pick_exact_cached_query(
    manager: DirectoryIndexManager,
    user_roots: tuple[Path, ...],
) -> str | None:
    _manifest, shards = manager._load_cache()  # noqa: SLF001 - diagnostics inspect cache contents
    for shard in shards.values():
        for candidates in shard.name_candidates.values():
            for candidate in candidates:
                candidate_path = Path(candidate.path)
                if _is_within_user_roots(candidate_path, user_roots) and candidate_path.name:
                    return candidate_path.name
    return None
