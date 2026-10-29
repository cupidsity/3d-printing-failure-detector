"""Geometry helpers for linearizing supported G-code motion."""

from __future__ import annotations

import math


Point3 = tuple[float, float, float]


# Function: distance
# Calculates the straight-line distance between two 3D points.
#
# Inputs:
# * start: Point3
# * end: Point3
#
# Output: The distance in millimeters.
def distance(start: Point3, end: Point3) -> float:
    return math.dist(start, end)


# Function: _signed_sweep
# Resolves the directed angular sweep between two angles.
#
# Inputs:
# * start_angle: float
# * end_angle: float
# * clockwise: bool
#
# Output: A signed sweep in radians.
def _signed_sweep(start_angle: float, end_angle: float, clockwise: bool) -> float:
    full_turn = 2.0 * math.pi
    if clockwise:
        magnitude = (start_angle - end_angle) % full_turn
        return -(magnitude if magnitude > 1e-12 else full_turn)
    magnitude = (end_angle - start_angle) % full_turn
    return magnitude if magnitude > 1e-12 else full_turn


# Function: _center_from_radius
# Finds the XY arc center selected by an R-form G-code command.
#
# Inputs:
# * start: Point3
# * end: Point3
# * radius_word: float
# * clockwise: bool
#
# Output: The center X/Y, starting angle, and signed sweep.
def _center_from_radius(
    start: Point3, end: Point3, radius_word: float, clockwise: bool
) -> tuple[float, float, float, float]:
    sx, sy, _ = start
    ex, ey, _ = end
    dx = ex - sx
    dy = ey - sy
    chord = math.hypot(dx, dy)
    radius = abs(radius_word)
    if chord <= 1e-12:
        raise ValueError("R-form arcs require distinct XY endpoints")
    if radius + 1e-12 < chord / 2.0:
        raise ValueError("arc radius is smaller than half the endpoint chord")

    midpoint_x = (sx + ex) / 2.0
    midpoint_y = (sy + ey) / 2.0
    height = math.sqrt(max(0.0, radius * radius - (chord / 2.0) ** 2))
    perpendicular_x = -dy / chord
    perpendicular_y = dx / chord
    candidates = [
        (
            midpoint_x + perpendicular_x * height,
            midpoint_y + perpendicular_y * height,
        ),
        (
            midpoint_x - perpendicular_x * height,
            midpoint_y - perpendicular_y * height,
        ),
    ]

    choices: list[tuple[float, float, float, float]] = []
    for center_x, center_y in candidates:
        start_angle = math.atan2(sy - center_y, sx - center_x)
        end_angle = math.atan2(ey - center_y, ex - center_x)
        sweep = _signed_sweep(start_angle, end_angle, clockwise)
        choices.append((center_x, center_y, start_angle, sweep))

    if radius_word >= 0:
        return min(choices, key=lambda choice: abs(choice[3]))
    return max(choices, key=lambda choice: abs(choice[3]))


# Function: tessellate_arc
# Converts one supported G-code arc into bounded-error line endpoints.
#
# Inputs:
# * start: Point3
# * end: Point3
# * clockwise: bool
# * i: float | None
# * j: float | None
# * radius_word: float | None
# * chord_error: float
# * max_segments: int
# * plane: str
#
# Output: A list of 3D endpoints whose final item is the exact arc endpoint.
def tessellate_arc(
    start: Point3,
    end: Point3,
    *,
    clockwise: bool,
    i: float | None,
    j: float | None,
    radius_word: float | None,
    chord_error: float,
    max_segments: int,
    plane: str = "XY",
) -> list[Point3]:
    """Return arc endpoints after the start, preserving the exact final point."""

    # Validate the arc form before selecting its center and sweep.
    if plane != "XY":
        raise ValueError(f"arc plane {plane} is not supported")
    if radius_word is not None and (i is not None or j is not None):
        raise ValueError("an arc cannot mix R with I or J")

    sx, sy, sz = start
    ex, ey, ez = end
    if radius_word is not None:
        center_x, center_y, start_angle, sweep = _center_from_radius(
            start, end, radius_word, clockwise
        )
        radius = abs(radius_word)
    else:
        if i is None and j is None:
            raise ValueError("an arc requires I/J center offsets or an R radius")
        center_x = sx + (i or 0.0)
        center_y = sy + (j or 0.0)
        radius = math.hypot(sx - center_x, sy - center_y)
        if radius <= 1e-12:
            raise ValueError("arc radius must be positive")
        start_angle = math.atan2(sy - center_y, sx - center_x)
        end_angle = math.atan2(ey - center_y, ex - center_x)
        sweep = _signed_sweep(start_angle, end_angle, clockwise)

    # Convert the allowed chord error into a safe angular step count.
    ratio = max(-1.0, min(1.0, 1.0 - chord_error / radius))
    maximum_angle = 2.0 * math.acos(ratio)
    if maximum_angle <= 1e-12:
        maximum_angle = abs(sweep)
    segment_count = max(1, math.ceil(abs(sweep) / maximum_angle))
    if segment_count > max_segments:
        raise ValueError(
            f"arc requires {segment_count} segments, exceeding limit {max_segments}"
        )

    # Generate intermediate points while preserving the exact requested endpoint.
    points: list[Point3] = []
    for index in range(1, segment_count + 1):
        fraction = index / segment_count
        if index == segment_count:
            points.append(end)
            continue
        angle = start_angle + sweep * fraction
        points.append(
            (
                center_x + radius * math.cos(angle),
                center_y + radius * math.sin(angle),
                sz + (ez - sz) * fraction,
            )
        )
    return points

