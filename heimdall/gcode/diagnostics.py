"""Low-cost diagnostic output for checking normalized parser geometry."""

from __future__ import annotations

from html import escape
from pathlib import Path

import numpy as np

from .models import ParsedJob


# Function: write_layer_svg
# Writes a lightweight top-down diagnostic image for one normalized layer.
#
# Inputs:
# * job: ParsedJob
# * layer: int
# * destination: str | Path
# * image_size: int
# * padding: int
#
# Output: The absolute path of the written SVG file.
def write_layer_svg(
    job: ParsedJob,
    layer: int,
    destination: str | Path,
    *,
    image_size: int = 800,
    padding: int = 24,
) -> Path:
    """Write a dependency-free top-down SVG preview for one layer."""

    # Load the requested zero-copy layer slice and calculate its XY bounds.
    segments = job.layer_segments(layer)
    if segments.size == 0:
        raise ValueError(f"layer {layer} has no segments")
    x_values = np.concatenate((segments["x0"], segments["x1"]))
    y_values = np.concatenate((segments["y0"], segments["y1"]))
    min_x, max_x = float(x_values.min()), float(x_values.max())
    min_y, max_y = float(y_values.min()), float(y_values.max())
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = (image_size - 2 * padding) / max(span_x, span_y)

    # Function: project
    # Maps one machine-space XY point into SVG pixel coordinates.
    #
    # Inputs:
    # * x: float
    # * y: float
    #
    # Output: The projected SVG X and Y coordinates.
    def project(x: float, y: float) -> tuple[float, float]:
        px = padding + (x - min_x) * scale
        py = image_size - padding - (y - min_y) * scale
        return px, py

    # Convert each segment into an SVG line with feature metadata.
    lines: list[str] = []
    for segment in segments:
        x0, y0 = project(float(segment["x0"]), float(segment["y0"]))
        x1, y1 = project(float(segment["x1"]), float(segment["y1"]))
        feature_index = int(segment["feature"])
        feature = (
            job.feature_names[feature_index]
            if feature_index < len(job.feature_names)
            else "UNKNOWN"
        )
        lines.append(
            f'<line x1="{x0:.3f}" y1="{y0:.3f}" x2="{x1:.3f}" '
            f'y2="{y1:.3f}"><title>{escape(feature)}</title></line>'
        )

    # Write a self-contained SVG that needs no rendering dependency.
    output = Path(destination)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "\n".join(
            [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<svg xmlns="http://www.w3.org/2000/svg" '
                f'viewBox="0 0 {image_size} {image_size}">',
                '<rect width="100%" height="100%" fill="#10151c"/>',
                '<g fill="none" stroke="#61dafb" stroke-width="2" stroke-linecap="round">',
                *lines,
                "</g>",
                '<text x="12" y="20" fill="#e6edf3" font-family="monospace" '
                f'font-size="14">Layer {layer}</text>',
                "</svg>",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return output.resolve()

