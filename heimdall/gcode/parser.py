"""Single-pass G-code interpreter producing compact NumPy records."""

from __future__ import annotations

from collections import Counter
import hashlib
import io
import math
from pathlib import Path
from typing import BinaryIO

import numpy as np

from .dialects import build_adapters, merge_comment_metadata
from .geometry import distance, tessellate_arc
from .models import (
    EVENT_DTYPE,
    PARSER_SCHEMA_VERSION,
    SEGMENT_DTYPE,
    EventKind,
    ParsedJob,
    ParserConfig,
    ParserWarning,
    SegmentFlag,
)
from .state import MachineState
from .tokenizer import tokenize_stream


_QUIET_COMMANDS = {
    "G4", "G28", "G29", "G80",
    "M0", "M1", "M17", "M18", "M84", "M104", "M105", "M106", "M107",
    "M109", "M115", "M117", "M140", "M190", "M201", "M203", "M204",
    "M205", "M206", "M207", "M208", "M220", "M302", "M400", "M420",
    "M486", "M900",
}


class _RecordBuffer:
    """Append structured records without retaining per-row Python objects."""

    # Function: __init__
    # Allocates a typed NumPy buffer with room to grow.
    #
    # Inputs:
    # * self: _RecordBuffer
    # * dtype: np.dtype
    # * initial_capacity: int
    #
    # Output: None.
    def __init__(self, dtype: np.dtype, initial_capacity: int = 4_096) -> None:
        self.dtype = dtype
        self.array = np.empty(initial_capacity, dtype=dtype)
        self.count = 0

    # Function: append
    # Adds one structured record, doubling the buffer when it is full.
    #
    # Inputs:
    # * self: _RecordBuffer
    # * row: tuple[object, ...]
    #
    # Output: None.
    def append(self, row: tuple[object, ...]) -> None:
        if self.count == self.array.size:
            self.array.resize((max(1, self.array.size * 2),), refcheck=False)
        self.array[self.count] = row
        self.count += 1

    # Function: finish
    # Trims unused capacity and returns the completed structured array.
    #
    # Inputs:
    # * self: _RecordBuffer
    #
    # Output: The populated NumPy record array.
    def finish(self) -> np.ndarray:
        self.array.resize((self.count,), refcheck=False)
        return self.array

# Function: parse_stream
# Interprets a binary G-code stream in one sequential pass.
#
# Inputs:
# * stream: BinaryIO
# * config: ParserConfig | None
# * source_path: str | None
#
# Output: A ParsedJob containing geometry, events, layers, and warnings.
def parse_stream(
    stream: BinaryIO,
    config: ParserConfig | None = None,
    *,
    source_path: str | None = None,
) -> ParsedJob:
    """Parse a binary G-code stream in one sequential pass."""

    # Initialize immutable options, hashing, machine state, and slicer adapters.
    options = config or ParserConfig()
    digest = hashlib.sha256()
    state = MachineState()
    state.filament_diameters[0] = options.filament_diameter
    adapters = build_adapters(options.slicers)

    # Allocate typed outputs and bounded metadata collections.
    segment_rows = _RecordBuffer(SEGMENT_DTYPE)
    event_rows = _RecordBuffer(EVENT_DTYPE, initial_capacity=256)
    warnings: list[ParserWarning] = []
    warning_counts: Counter[str] = Counter()
    features = ["UNKNOWN"]
    feature_ids = {"UNKNOWN": 0}
    current_feature = "UNKNOWN"
    comment_width: float | None = None
    comment_height: float | None = None
    current_layer = -1
    layer_z: float | None = None
    explicit_layers_seen = False
    pending_explicit_layer = False
    source_size = 0

    # Function: warn
    # Records a bounded source-located warning or raises in strict mode.
    #
    # Inputs:
    # * code: str
    # * message: str
    # * line_number: int
    # * byte_offset: int
    #
    # Output: None.
    def warn(code: str, message: str, line_number: int, byte_offset: int) -> None:
        warning_counts[code] += 1
        if options.strict:
            raise ValueError(f"line {line_number}: {code}: {message}")
        if len(warnings) < options.max_warnings:
            warnings.append(ParserWarning(code, message, line_number, byte_offset))

    # Function: add_event
    # Preserves a non-geometric extrusion event at the current machine position.
    #
    # Inputs:
    # * kind: EventKind
    # * delta_e: float
    # * file_end: int
    #
    # Output: None.
    def add_event(kind: EventKind, delta_e: float, file_end: int) -> None:
        event_rows.append(
            (
                int(kind), state.active_tool, state.x, state.y, state.z,
                delta_e, file_end,
            )
        )

    # Function: select_layer
    # Selects a normalized layer using comments or positive-extrusion Z changes.
    #
    # Inputs:
    # * z: float
    #
    # Output: The normalized zero-based layer index.
    def select_layer(z: float) -> int:
        nonlocal current_layer, layer_z, pending_explicit_layer
        if explicit_layers_seen:
            if current_layer < 0:
                current_layer = 0
                layer_z = z
            elif pending_explicit_layer:
                current_layer += 1
                layer_z = z
            pending_explicit_layer = False
            return current_layer
        if current_layer < 0:
            current_layer = 0
            layer_z = z
        elif layer_z is not None and z > layer_z + options.layer_z_tolerance:
            current_layer += 1
            layer_z = z
        return current_layer

    # Function: feature_id
    # Interns a feature name into the compact integer feature table.
    #
    # Inputs:
    # * name: str
    #
    # Output: The feature's integer identifier.
    def feature_id(name: str) -> int:
        normalized = name.strip() or "UNKNOWN"
        if normalized not in feature_ids:
            feature_ids[normalized] = len(features)
            features.append(normalized)
        return feature_ids[normalized]

    # Function: emit_polyline
    # Converts an extruding polyline into typed bead segment records.
    #
    # Inputs:
    # * start: tuple[float, float, float]
    # * points: list[tuple[float, float, float]]
    # * delta_e: float
    # * file_end: int
    # * arc: bool
    #
    # Output: None.
    def emit_polyline(
        start: tuple[float, float, float],
        points: list[tuple[float, float, float]],
        delta_e: float,
        file_end: int,
        *,
        arc: bool,
    ) -> None:
        if not points:
            return
        # Measure every piece so extrusion can be distributed proportionally.
        lengths: list[float] = []
        previous = start
        for point in points:
            lengths.append(distance(previous, point))
            previous = point
        total_length = sum(lengths)
        if total_length <= options.motion_epsilon:
            add_event(EventKind.PRIME, delta_e, file_end)
            return

        # Resolve bead dimensions from slicer metadata or volume-based estimates.
        height = comment_height or options.default_layer_height
        flags = SegmentFlag.ARC_LINEARIZED if arc else 0
        if comment_height is None:
            flags |= SegmentFlag.HEIGHT_ESTIMATED
        if state.active_tool in state.volumetric_tools:
            volume = delta_e
            flags |= SegmentFlag.VOLUMETRIC_EXTRUSION
        else:
            volume = delta_e * state.filament_area(options.filament_diameter)
        volume *= state.current_flow / 100.0
        if comment_width is None:
            width = volume / (total_length * height)
            if not math.isfinite(width) or width <= 0:
                width = options.default_line_width
            flags |= SegmentFlag.WIDTH_ESTIMATED
        else:
            width = comment_width

        # Emit compact records with one source byte offset for the complete command.
        layer = select_layer(points[-1][2])
        fid = feature_id(current_feature)
        previous = start
        remaining_e = delta_e
        for index, (point, length) in enumerate(zip(points, lengths, strict=True)):
            piece_e = (
                remaining_e
                if index == len(points) - 1
                else delta_e * (length / total_length)
            )
            remaining_e -= piece_e
            segment_rows.append(
                (
                    previous[0], previous[1], previous[2],
                    point[0], point[1], point[2], piece_e, width, height,
                    layer, state.active_tool, fid, int(flags), file_end,
                )
            )
            previous = point

    # Interpret each line immediately so the source is never loaded in full.
    for token in tokenize_stream(stream, digest):
        source_size = token.byte_end
        for lexical_error in token.lexical_errors:
            warn(
                "MALFORMED_TOKEN",
                f"could not parse {lexical_error!r}",
                token.line_number,
                token.byte_start,
            )
        if token.checksum_valid is False:
            warn(
                "BAD_CHECKSUM", "line checksum does not match", token.line_number,
                token.byte_start,
            )

        # Apply recognized slicer comments before interpreting the command.
        metadata = merge_comment_metadata(
            [adapter.parse(token.comment) for adapter in adapters]
        )
        if metadata.layer_change:
            explicit_layers_seen = True
            pending_explicit_layer = True
        if metadata.feature is not None:
            current_feature = metadata.feature
        if metadata.width is not None:
            if metadata.width > 0:
                comment_width = metadata.width
            else:
                warn(
                    "BAD_WIDTH", "comment width must be positive",
                    token.line_number, token.byte_start,
                )
        if metadata.height is not None:
            if metadata.height > 0:
                comment_height = metadata.height
            else:
                warn(
                    "BAD_HEIGHT", "comment height must be positive",
                    token.line_number, token.byte_start,
                )

        # Apply modal state changes and normalize supported motion commands.
        command = token.command
        parameters = token.parameters
        if command is None:
            continue
        if command == "G20":
            state.unit_scale = 25.4
        elif command == "G21":
            state.unit_scale = 1.0
        elif command == "G90":
            state.xyz_absolute = True
        elif command == "G91":
            state.xyz_absolute = False
        elif command == "M82":
            state.e_absolute_override = True
        elif command == "M83":
            state.e_absolute_override = False
        elif command == "G92":
            state.apply_g92(parameters)
        elif command in {"G17", "G18", "G19"}:
            state.plane = {"G17": "XY", "G18": "XZ", "G19": "YZ"}[command]
        elif command.startswith("T"):
            try:
                state.set_active_tool(int(command[1:]), options.filament_diameter)
            except ValueError as error:
                warn("BAD_TOOL", str(error), token.line_number, token.byte_start)
        elif command == "M200":
            diameter = parameters.get("D")
            if diameter is None:
                warn("MISSING_PARAMETER", "M200 requires D", token.line_number, token.byte_start)
            elif diameter == 0:
                state.volumetric_tools.discard(state.active_tool)
            elif diameter > 0:
                state.filament_diameters[state.active_tool] = state.scale_linear(diameter)
                state.volumetric_tools.add(state.active_tool)
            else:
                warn(
                    "BAD_FILAMENT_DIAMETER", "M200 D must be non-negative",
                    token.line_number, token.byte_start,
                )
        elif command == "M221":
            if "S" in parameters and parameters["S"] > 0:
                state.flow_percent[state.active_tool] = parameters["S"]
            else:
                warn(
                    "BAD_FLOW", "M221 requires a positive S value",
                    token.line_number, token.byte_start,
                )
        elif command in {"G10", "G11"}:
            add_event(
                EventKind.FIRMWARE_RETRACT if command == "G10" else EventKind.FIRMWARE_UNRETRACT,
                0.0,
                token.byte_end,
            )
        elif command in {"G0", "G1", "G2", "G3"}:
            start = state.xyz
            destination = state.resolve_destination(parameters)
            delta_e = state.resolve_extrusion_delta(parameters)
            spatial_distance = distance(start, destination)
            if delta_e < -options.extrusion_epsilon:
                add_event(EventKind.RETRACTION, delta_e, token.byte_end)
            elif delta_e > options.extrusion_epsilon:
                if spatial_distance <= options.motion_epsilon and command in {"G0", "G1"}:
                    add_event(EventKind.PRIME, delta_e, token.byte_end)
                elif command in {"G2", "G3"}:
                    try:
                        points = tessellate_arc(
                            start,
                            destination,
                            clockwise=command == "G2",
                            i=(state.scale_linear(parameters["I"]) if "I" in parameters else None),
                            j=(state.scale_linear(parameters["J"]) if "J" in parameters else None),
                            radius_word=(
                                state.scale_linear(parameters["R"])
                                if "R" in parameters else None
                            ),
                            chord_error=options.chord_error,
                            max_segments=options.max_arc_segments,
                            plane=state.plane,
                        )
                        emit_polyline(start, points, delta_e, token.byte_end, arc=True)
                    except ValueError as error:
                        warn("UNSUPPORTED_ARC", str(error), token.line_number, token.byte_start)
                else:
                    emit_polyline(start, [destination], delta_e, token.byte_end, arc=False)
            state.apply_move(destination, parameters)
        elif command in _QUIET_COMMANDS:
            continue
        else:
            warn("UNSUPPORTED_COMMAND", f"ignored {command}", token.line_number, token.byte_start)

    # Finalize typed buffers and build constant-time layer slice offsets.
    segments = segment_rows.finish()
    events = event_rows.finish()
    if segments.size:
        counts = np.bincount(segments["layer"].astype(np.int64))
        layer_offsets = np.concatenate(
            (np.array([0], dtype=np.uint64), np.cumsum(counts, dtype=np.uint64))
        )
    else:
        layer_offsets = np.array([0], dtype=np.uint64)

    return ParsedJob(
        segments=segments,
        events=events,
        layer_offsets=layer_offsets,
        source_hash=digest.hexdigest(),
        source_size=source_size,
        parser_schema_version=PARSER_SCHEMA_VERSION,
        config_fingerprint=options.fingerprint(),
        feature_names=tuple(features),
        warnings=tuple(warnings),
        warning_counts=dict(warning_counts),
        source_path=source_path,
    )


# Function: parse_bytes
# Parses an in-memory G-code byte string through the streaming parser.
#
# Inputs:
# * data: bytes
# * config: ParserConfig | None
#
# Output: The normalized ParsedJob.
def parse_bytes(data: bytes, config: ParserConfig | None = None) -> ParsedJob:
    """Parse an in-memory G-code byte string."""

    return parse_stream(io.BytesIO(data), config)


# Function: parse_file
# Opens and parses one G-code file without loading it all into memory.
#
# Inputs:
# * path: str | Path
# * config: ParserConfig | None
#
# Output: The normalized ParsedJob.
def parse_file(path: str | Path, config: ParserConfig | None = None) -> ParsedJob:
    """Parse a G-code file without loading the source file into memory."""

    source = Path(path).resolve()
    with source.open("rb") as stream:
        return parse_stream(stream, config, source_path=str(source))
