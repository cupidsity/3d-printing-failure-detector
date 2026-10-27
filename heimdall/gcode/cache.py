"""Versioned, memory-mappable cache for parsed G-code jobs."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import time

import numpy as np

from .models import (
    PARSER_SCHEMA_VERSION,
    ParsedJob,
    ParserConfig,
    ParserWarning,
    normalize_source_path,
)
from .parser import parse_file


@dataclass(frozen=True, slots=True)
class CacheResult:
    """The parsed job plus observable cache behavior and timing."""

    job: ParsedJob
    cache_hit: bool
    cache_path: Path
    total_seconds: float
    parse_seconds: float

    @property
    # Function: parsing_skipped
    # Reports whether a cache hit avoided running the parser.
    #
    # Inputs:
    # * self: CacheResult
    #
    # Output: True when parsing was skipped.
    def parsing_skipped(self) -> bool:
        return self.cache_hit and self.parse_seconds == 0.0


class GCodeCache:
    """Store immutable parser artifacts keyed by source and parser configuration."""

    # Function: __init__
    # Configures the directory used for cache artifacts and their index.
    #
    # Inputs:
    # * self: GCodeCache
    # * root: str | Path
    #
    # Output: None.
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.index_path = self.root / "index.json"

    # Function: _read_index
    # Reads the cache index and treats missing or invalid data as an empty cache.
    #
    # Inputs:
    # * self: GCodeCache
    #
    # Output: Cache index entries keyed by source and configuration identity.
    def _read_index(self) -> dict[str, dict[str, object]]:
        try:
            payload = json.loads(self.index_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    # Function: _write_index
    # Writes the complete cache index through an atomic file replacement.
    #
    # Inputs:
    # * self: GCodeCache
    # * index: dict[str, dict[str, object]]
    #
    # Output: None.
    def _write_index(self, index: dict[str, dict[str, object]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = self.root / "index.json.tmp"
        temporary.write_text(
            json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary, self.index_path)

    @staticmethod
    # Function: _index_key
    # Creates the cache index identity for one source and parser configuration.
    #
    # Inputs:
    # * source_path: str
    # * config: ParserConfig
    #
    # Output: The cache index key.
    def _index_key(source_path: str, config: ParserConfig) -> str:
        return f"{source_path}\n{config.fingerprint()}\nv{PARSER_SCHEMA_VERSION}"

    @staticmethod
    # Function: _source_hash
    # Streams a source file into SHA-256 without loading it all into memory.
    #
    # Inputs:
    # * source_path: str
    #
    # Output: The source file's SHA-256 hexadecimal string.
    def _source_hash(source_path: str) -> str:
        digest = hashlib.sha256()
        with Path(source_path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    # Function: get_or_parse
    # Loads a valid memory-mapped artifact or parses and stores a new artifact.
    #
    # Inputs:
    # * self: GCodeCache
    # * source: str | Path
    # * config: ParserConfig | None
    #
    # Output: The parsed job and observable cache/timing information.
    def get_or_parse(
        self, source: str | Path, config: ParserConfig | None = None
    ) -> CacheResult:
        """Load a valid artifact or parse and atomically create one."""

        # Resolve the request and inspect any existing index entry.
        started = time.perf_counter()
        options = config or ParserConfig()
        source_path = normalize_source_path(source)
        source_stat = Path(source_path).stat()
        index = self._read_index()
        index_key = self._index_key(source_path, options)
        entry = index.get(index_key)
        # Validate file metadata and content before trusting an artifact.
        if entry is not None:
            cache_key = str(entry.get("cache_key", ""))
            artifact_path = self.root / cache_key
            if (
                entry.get("source_size") == source_stat.st_size
                and entry.get("source_mtime_ns") == source_stat.st_mtime_ns
                and entry.get("source_hash") == self._source_hash(source_path)
                and artifact_path.is_dir()
            ):
                try:
                    job = self._load(artifact_path, source_path)
                    return CacheResult(
                        job=job,
                        cache_hit=True,
                        cache_path=artifact_path,
                        total_seconds=time.perf_counter() - started,
                        parse_seconds=0.0,
                    )
                except (OSError, ValueError, KeyError, json.JSONDecodeError):
                    pass

        # Parse cache misses once, then derive a content-addressed artifact name.
        parse_started = time.perf_counter()
        job = parse_file(source_path, options)
        parse_seconds = time.perf_counter() - parse_started
        cache_key = f"v{PARSER_SCHEMA_VERSION}-{job.source_hash}-{job.config_fingerprint[:16]}"
        artifact_path = self.root / cache_key
        if not artifact_path.is_dir():
            self._store(job, artifact_path)
        # Update the index only after the artifact has been safely stored.
        latest_stat = Path(source_path).stat()
        index[index_key] = {
            "cache_key": cache_key,
            "source_hash": job.source_hash,
            "source_size": latest_stat.st_size,
            "source_mtime_ns": latest_stat.st_mtime_ns,
        }
        self._write_index(index)
        return CacheResult(
            job=job,
            cache_hit=False,
            cache_path=artifact_path,
            total_seconds=time.perf_counter() - started,
            parse_seconds=parse_seconds,
        )

    # Function: _store
    # Writes arrays and metadata into an atomically promoted artifact directory.
    #
    # Inputs:
    # * self: GCodeCache
    # * job: ParsedJob
    # * destination: Path
    #
    # Output: None.
    def _store(self, job: ParsedJob, destination: Path) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".building-", dir=self.root))
        try:
            # Save only non-pickle NumPy arrays suitable for memory mapping.
            np.save(temporary / "segments.npy", job.segments, allow_pickle=False)
            np.save(temporary / "events.npy", job.events, allow_pickle=False)
            np.save(temporary / "layer_offsets.npy", job.layer_offsets, allow_pickle=False)
            # Store JSON-safe metadata separately from typed binary records.
            metadata = {
                "source_hash": job.source_hash,
                "source_size": job.source_size,
                "parser_schema_version": job.parser_schema_version,
                "config_fingerprint": job.config_fingerprint,
                "feature_names": list(job.feature_names),
                "warnings": [asdict(item) for item in job.warnings],
                "warning_counts": job.warning_counts,
            }
            (temporary / "metadata.json").write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            # Promote the complete artifact; tolerate another writer winning the race.
            try:
                os.replace(temporary, destination)
            except FileExistsError:
                pass
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    @staticmethod
    # Function: _load
    # Opens a validated artifact with read-only memory-mapped arrays.
    #
    # Inputs:
    # * artifact_path: Path
    # * source_path: str
    #
    # Output: A ParsedJob backed by the cached NumPy files.
    def _load(artifact_path: Path, source_path: str) -> ParsedJob:
        metadata = json.loads(
            (artifact_path / "metadata.json").read_text(encoding="utf-8")
        )
        if metadata["parser_schema_version"] != PARSER_SCHEMA_VERSION:
            raise ValueError("cache schema version is stale")
        return ParsedJob(
            segments=np.load(
                artifact_path / "segments.npy", mmap_mode="r", allow_pickle=False
            ),
            events=np.load(
                artifact_path / "events.npy", mmap_mode="r", allow_pickle=False
            ),
            layer_offsets=np.load(
                artifact_path / "layer_offsets.npy", mmap_mode="r", allow_pickle=False
            ),
            source_hash=metadata["source_hash"],
            source_size=int(metadata["source_size"]),
            parser_schema_version=int(metadata["parser_schema_version"]),
            config_fingerprint=metadata["config_fingerprint"],
            feature_names=tuple(metadata["feature_names"]),
            warnings=tuple(ParserWarning(**item) for item in metadata["warnings"]),
            warning_counts={
                str(key): int(value)
                for key, value in metadata["warning_counts"].items()
            },
            source_path=source_path,
        )

    # Function: clear
    # Removes artifacts named in this cache's index.
    #
    # Inputs:
    # * self: GCodeCache
    #
    # Output: The number of artifact directories removed.
    def clear(self) -> int:
        """Remove every artifact in this cache and return the artifact count."""

        index = self._read_index()
        artifact_names = {
            str(entry.get("cache_key", "")) for entry in index.values()
        }
        removed = 0
        for name in artifact_names:
            path = self.root / name
            if name and path.is_dir():
                shutil.rmtree(path)
                removed += 1
        if self.index_path.exists():
            self.index_path.unlink()
        return removed
