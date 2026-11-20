from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# 8 grey levels keeps the co-occurrence matrix tiny (8x8) so it's cheap on a pi and
# less sensitive to sensor noise than the usual 256
GLCM_LEVELS = 8

# order matters: neighbours have to go around the circle so "transitions" in a code
# mean something. (row offset, column offset), starting at the right and going counter-clockwise
LBP_NEIGHBOUR_OFFSETS = [(0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1)]

FEATURE_NAMES = (
    "periodicity",
    "fine_detail",
    "line_continuity",
    "glcm_contrast",
    "glcm_correlation",
    "lbp_irregular",
)


def _build_nri_uniform_table() -> np.ndarray:
    # equivalent of scikit-image's "nri_uniform": every uniform pattern (at most 2 bit flips
    # around the circle) keeps its own bin, so the direction of the layer lines is preserved.
    # everything else is lumped into one "irregular" bin at the end
    is_uniform = []
    for code in range(256):
        rotated = ((code >> 1) | ((code & 1) << 7)) & 0xFF
        is_uniform.append(bin(code ^ rotated).count("1") <= 2)

    irregular_bin = sum(is_uniform)
    table = np.full(256, irregular_bin, dtype=np.uint8)
    next_bin = 0
    for code in range(256):
        if is_uniform[code]:
            table[code] = next_bin
            next_bin += 1
    return table


LBP_TABLE = _build_nri_uniform_table()
LBP_BIN_COUNT = int(LBP_TABLE.max()) + 1
LBP_IRREGULAR_BIN = LBP_BIN_COUNT - 1


@dataclass
class TileFeatures:
    # one row per tile, columns follow FEATURE_NAMES
    values: np.ndarray
    # one normalised lbp histogram per tile, kept separately because the baseline turns it
    # into a single "how far from the usual histogram" number
    lbp_histograms: np.ndarray
    # top-left corner of each tile in the roi, so a caller can draw where the problem is
    origins: np.ndarray


def to_grayscale(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return image
    # opencv's bgr2gray is the bt.601 luma conversion the fdm texture papers used
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def normalise_contrast(gray: np.ndarray, clip_limit: float, grid_size: int) -> np.ndarray:
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
    return clahe.apply(gray)


def lbp_codes(gray: np.ndarray) -> np.ndarray:
    # computed once for the whole roi and sliced per tile, which is much cheaper than per tile
    padded = cv2.copyMakeBorder(gray, 1, 1, 1, 1, cv2.BORDER_REPLICATE).astype(np.int16)
    height, width = gray.shape
    center = padded[1 : height + 1, 1 : width + 1]
    codes = np.zeros((height, width), dtype=np.uint8)
    for bit_index, (row_offset, column_offset) in enumerate(LBP_NEIGHBOUR_OFFSETS):
        neighbour = padded[
            1 + row_offset : height + 1 + row_offset,
            1 + column_offset : width + 1 + column_offset,
        ]
        codes |= (neighbour >= center).astype(np.uint8) << bit_index
    return LBP_TABLE[codes]


def periodicity_strength(tile: np.ndarray, layer_pitch_px: float) -> float:
    # layer lines run horizontally, so averaging each row leaves a 1d signal that should be a
    # clean wave at the layer pitch. the share of its power sitting at that pitch drops when lines
    # go missing (under-extrusion, gaps) or get noisy (rough surface)
    profile = tile.mean(axis=1)
    profile = profile - profile.mean()
    power = np.abs(np.fft.rfft(profile)) ** 2
    total = power[1:].sum()
    if total <= 1e-9:
        return 0.0
    expected_bin = len(profile) / layer_pitch_px
    # +-30% around the expected pitch allows for perspective and slightly wrong pitch settings
    low_bin = max(1, int(np.floor(expected_bin * 0.7)))
    high_bin = min(len(power) - 1, int(np.ceil(expected_bin * 1.3)))
    if high_bin < low_bin:
        return 0.0
    return float(power[low_bin : high_bin + 1].max() / total)


def standardise(tile: np.ndarray) -> np.ndarray:
    # zero mean, unit spread. without this, dimmer light alone lowers every contrast-like feature
    # and a good print starts looking "different" the moment someone turns a lamp off
    values = tile.astype(np.float32)
    return (values - values.mean()) / max(float(values.std()), 1e-3)


def line_continuity(standardised: np.ndarray) -> float:
    # on a good wall every column shows the same up-down layer pattern. gaps and broken or
    # missing lines make individual columns disagree with the tile's average profile
    profile = standardised.mean(axis=1)
    profile = profile - profile.mean()
    columns = standardised - standardised.mean(axis=0, keepdims=True)
    profile_norm = float(np.linalg.norm(profile))
    column_norms = np.linalg.norm(columns, axis=0)
    if profile_norm <= 1e-6:
        return 0.0
    correlations = (profile @ columns) / (profile_norm * np.maximum(column_norms, 1e-6))
    return float(correlations.mean())


def glcm_contrast_correlation(standardised: np.ndarray, offset: int) -> tuple[float, float]:
    # pixel pairs are taken vertically, one layer apart, so on a good wall each pair should match.
    # averaging over all angles, as glcm usually does, would blur away the one direction that matters.
    # levels span +-2 standard deviations so the same surface lands in the same bins at any brightness
    quantised = np.clip((standardised + 2.0) * (GLCM_LEVELS / 4.0), 0, GLCM_LEVELS - 1).astype(np.int64)
    upper = quantised[:-offset, :].ravel()
    lower = quantised[offset:, :].ravel()
    counts = np.bincount(upper * GLCM_LEVELS + lower, minlength=GLCM_LEVELS * GLCM_LEVELS)
    counts = counts.reshape(GLCM_LEVELS, GLCM_LEVELS).astype(np.float64)
    counts = counts + counts.T
    probability = counts / counts.sum()

    levels = np.arange(GLCM_LEVELS, dtype=np.float64)
    row_levels, column_levels = np.meshgrid(levels, levels, indexing="ij")
    contrast = float((probability * (row_levels - column_levels) ** 2).sum())

    # the matrix is symmetric, so row and column statistics are the same
    mean = float((probability * row_levels).sum())
    variance = float((probability * (row_levels - mean) ** 2).sum())
    if variance <= 1e-12:
        # a flat tile is perfectly "correlated" with itself, nothing to measure
        return contrast, 1.0
    correlation = float(
        (probability * (row_levels - mean) * (column_levels - mean)).sum() / variance
    )
    return contrast, correlation


def extract_tile_features(
    normalised: np.ndarray,
    usable: np.ndarray,
    layer_pitch_px: float,
    tile_layers: int,
    min_usable_fraction: float,
) -> TileFeatures:
    tile_size = max(8, int(round(layer_pitch_px * tile_layers)))
    layer_offset = max(1, int(round(layer_pitch_px)))
    height, width = normalised.shape
    codes = lbp_codes(normalised)

    rows: list[list[float]] = []
    histograms: list[np.ndarray] = []
    origins: list[tuple[int, int]] = []

    for top in range(0, height - tile_size + 1, tile_size):
        for left in range(0, width - tile_size + 1, tile_size):
            tile_usable = usable[top : top + tile_size, left : left + tile_size]
            # tiles hanging off the edge of the part would mostly be measuring the bed or the
            # background, which is exactly the leak petsiuk & pearce saw in their false positives
            if tile_usable.mean() < min_usable_fraction:
                continue

            tile = normalised[top : top + tile_size, left : left + tile_size]
            tile_codes = codes[top : top + tile_size, left : left + tile_size]
            histogram = np.bincount(tile_codes.ravel(), minlength=LBP_BIN_COUNT).astype(np.float64)
            histogram /= histogram.sum()

            standardised = standardise(tile)
            laplacian = cv2.Laplacian(standardised, cv2.CV_32F)
            contrast, correlation = glcm_contrast_correlation(standardised, offset=layer_offset)
            rows.append(
                [
                    periodicity_strength(tile, layer_pitch_px),
                    # high-frequency energy relative to the tile's own contrast, logged because it
                    # changes multiplicatively with focus and roughness
                    float(np.log(laplacian.var() + 1e-6)),
                    line_continuity(standardised),
                    contrast,
                    correlation,
                    float(histogram[LBP_IRREGULAR_BIN]),
                ]
            )
            histograms.append(histogram)
            origins.append((top, left))

    return TileFeatures(
        values=np.asarray(rows, dtype=np.float64).reshape(-1, len(FEATURE_NAMES)),
        lbp_histograms=np.asarray(histograms, dtype=np.float64).reshape(-1, LBP_BIN_COUNT),
        origins=np.asarray(origins, dtype=np.int32).reshape(-1, 2),
    )
