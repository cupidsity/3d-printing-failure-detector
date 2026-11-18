"""Data contracts shared by the Phase 1 G-code parser modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import IntEnum
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


PARSER_SCHEMA_VERSION = 1


class SegmentFlag(IntEnum):
    """Bit flags describing how an emitted segment was derived."""

    WIDTH_ESTIMATED = 1
    HEIGHT_ESTIMATED = 2
    ARC_LINEARIZED = 4
    VOLUMETRIC_EXTRUSION = 8


class EventKind(IntEnum):
    """Non-geometric extrusion events preserved by the parser."""

    RETRACTION = 1
    PRIME = 2
    FIRMWARE_RETRACT = 3
    FIRMWARE_UNRETRACT = 4


SEGMENT_DTYPE = np.dtype(
    [
        ("x0", "<f4"),
        ("y0", "<f4"),
        ("z0", "<f4"),
        ("x1", "<f4"),
        ("y1", "<f4"),
        ("z1", "<f4"),
        ("delta_e", "<f4"),
        ("width", "<f4"),
        ("height", "<f4"),
        ("layer", "<u4"),
        ("tool", "<u2"),
        ("feature", "<u2"),
        ("flags", "<u2"),
        ("file_end", "<u8"),
    ],
    align=False,
)


EVENT_DTYPE = np.dtype(
    [
        ("kind", "u1"),
        ("tool", "<u2"),
        ("x", "<f4"),
        ("y", "<f4"),
        ("z", "<f4"),
        ("delta_e", "<f4"),
        ("file_end", "<u8"),
    ],
    align=False,
)


@dataclass(frozen=True, slots=True)
class ParserConfig:
    """Options that affect parser output and therefore cache identity."""

    slicers: tuple[str, ...] = ("cura", "prusaslicer")
    filament_diameter: float = 1.75
    default_line_width: float = 0.4
    default_layer_height: float = 0.2
    chord_error: float = 0.05
    motion_epsilon: float = 1e-6
    extrusion_epsilon: float = 1e-7
    layer_z_tolerance: float = 1e-4
    max_arc_segments: int = 10_000
    max_warnings: int = 1_000
    strict: bool = False

    # Function: __post_init__
    # Validates parser options after the immutable configuration is created.
    #
    # Inputs:
    # * self: ParserConfig
    #
    # Output: None.
    def __post_init__(self) -> None:
        supported = {"cura", "prusaslicer"}
        unknown = set(self.slicers) - supported
        if unknown:
            raise ValueError(f"unsupported slicer adapter(s): {sorted(unknown)}")
        if self.filament_diameter <= 0:
            raise ValueError("filament_diameter must be positive")
        if self.default_line_width <= 0 or self.default_layer_height <= 0:
            raise ValueError("default bead dimensions must be positive")
        if self.chord_error <= 0:
            raise ValueError("chord_error must be positive")
        if self.max_arc_segments < 1:
            raise ValueError("max_arc_segments must be at least one")

    # Function: fingerprint
    # Creates a deterministic identity for every option that affects output.
    #
    # Inputs:
    # * self: ParserConfig
    #
    # Output: A SHA-256 hexadecimal string.
    def fingerprint(self) -> str:
        """Return a stable hash of every option that changes parser output."""

        payload = json.dumps(
            asdict(self), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class ParserWarning:
    """A bounded, source-located parser warning."""

    code: str
    message: str
    line_number: int
    byte_offset: int


@dataclass(frozen=True, slots=True)
class TokenRecord:
    """One tokenized G-code source line."""

    line_number: int
    byte_start: int
    byte_end: int
    raw: str
    command: str | None
    parameters: dict[str, float]
    comment: str
    program_line: int | None
    checksum: int | None
    checksum_valid: bool | None
    lexical_errors: tuple[str, ...] = ()


@dataclass(slots=True)
class ParsedJob:
    """Normalized geometry and metadata produced for one G-code file."""

    segments: np.ndarray
    events: np.ndarray
    layer_offsets: np.ndarray
    source_hash: str
    source_size: int
    parser_schema_version: int
    config_fingerprint: str
    feature_names: tuple[str, ...]
    warnings: tuple[ParserWarning, ...] = ()
    warning_counts: dict[str, int] = field(default_factory=dict)
    source_path: str | None = None

    @property
    # Function: layer_count
    # Calculates the number of layers containing emitted geometry.
    #
    # Inputs:
    # * self: ParsedJob
    #
    # Output: The number of populated layers.
    def layer_count(self) -> int:
        """Return the number of layers that contain emitted geometry."""

        return max(0, int(self.layer_offsets.size) - 1)

    # Function: layer_segments
    # Returns a zero-copy view of the segments assigned to one layer.
    #
    # Inputs:
    # * self: ParsedJob
    # * layer: int
    #
    # Output: A NumPy array view containing the requested layer.
    def layer_segments(self, layer: int) -> np.ndarray:
        """Return a zero-copy slice for one normalized layer index."""

        if layer < 0 or layer >= self.layer_count:
            raise IndexError(f"layer {layer} is outside 0..{self.layer_count - 1}")
        start = int(self.layer_offsets[layer])
        end = int(self.layer_offsets[layer + 1])
        return self.segments[start:end]

    # Function: segment_index_at_file_position
    # Finds the last virtual segment completed by a G-code byte position.
    #
    # Inputs:
    # * self: ParsedJob
    # * file_position: int
    #
    # Output: The segment index, or None when no segment is complete.
    def segment_index_at_file_position(self, file_position: int) -> int | None:
        """Return the last segment whose source command ends by a byte position."""

        if file_position < 0:
            raise ValueError("file_position cannot be negative")
        if self.segments.size == 0:
            return None
        index = int(
            np.searchsorted(self.segments["file_end"], file_position, side="right") - 1
        )
        return index if index >= 0 else None

    # Function: summary
    # Builds a JSON-safe summary for diagnostics and command-line output.
    #
    # Inputs:
    # * self: ParsedJob
    #
    # Output: A dictionary containing parser and geometry statistics.
    def summary(self) -> dict[str, Any]:
        """Return JSON-safe diagnostic counts for CLI and manual tests."""

        return {
            "source_path": self.source_path,
            "source_hash": self.source_hash,
            "source_size": self.source_size,
            "segments": int(self.segments.size),
            "events": int(self.events.size),
            "layers": self.layer_count,
            "warnings": len(self.warnings),
            "warning_counts": dict(sorted(self.warning_counts.items())),
            "segment_record_bytes": int(SEGMENT_DTYPE.itemsize),
        }


# Function: normalize_source_path
# Resolves a source path so cache identity does not depend on the current directory.
#
# Inputs:
# * path: str | Path
#
# Output: The normalized absolute path as a string.
def normalize_source_path(path: str | Path) -> str:
    """Normalize a source path for cache index identity."""

    return str(Path(path).resolve())

