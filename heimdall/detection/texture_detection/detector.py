from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from .baseline import SCORED_FEATURE_NAMES, BaselinePool, TextureReference
from .features import extract_tile_features, normalise_contrast, to_grayscale

# plain-language reason for each feature, picked by whichever one moved furthest from the
# baseline. the sign says which direction counts as "worse" for that feature
FEATURE_REASONS = {
    "periodicity": (-1, "Layer lines are breaking up or missing"),
    "fine_detail": (1, "Surface is rougher than the earlier layers"),
    "line_continuity": (-1, "Layer lines are breaking up or missing"),
    "glcm_contrast": (1, "Surface is rougher than the earlier layers"),
    "glcm_correlation": (-1, "Layer lines are breaking up or missing"),
    "lbp_irregular": (1, "Surface is rougher than the earlier layers"),
    "lbp_drift": (1, "Surface texture changed from the earlier layers"),
}


@dataclass
class TextureConfig:
    # how many pixels one layer takes up in the cropped still. everything scale-related keys off
    # this, so it has to roughly match the camera setup (0.2 mm layers at 0.05 mm/px = 4 px)
    layer_pitch_px: float = 4.0
    # tile height in layers. 4-8 is what the research recommends: enough periods for the fft,
    # small enough that a local defect fills a good part of a tile
    tile_layers: int = 6
    # tiles less than this much inside the part mask are skipped
    min_usable_fraction: float = 0.9

    clahe_clip_limit: float = 2.0
    clahe_grid_size: int = 8

    # pixels at or beyond these are glare or crushed shadow and carry no texture
    saturation_low: int = 5
    saturation_high: int = 250
    max_saturated_fraction: float = 0.25

    # below this many usable tiles there's too little part in view to say anything
    min_tiles: int = 4

    # layer 0 (first layer squish, brim) never looks like the rest of the print, so the baseline
    # starts after it and runs for baseline_layer_count layers
    baseline_first_layer: int = 2
    baseline_layer_count: int = 9
    # alternating infill directions make odd and even layers look different
    separate_parity: bool = True
    max_baseline_tiles: int = 4000

    # a tile counts as unusual past this average z-score
    tile_rms_z_threshold: float = 3.0
    # how many baseline standard deviations of "share of unusual tiles" maps to a 0.5 layer score
    score_midpoint_z: float = 3.0
    score_scale: float = 1.0
    # stops a perfectly clean baseline (std 0) from making any single odd tile look catastrophic
    unusual_fraction_std_floor: float = 0.03

    # the reported score is the persistence_count-th highest of the last persistence_window
    # layer scores, so one bad photo can never push it up alone
    persistence_window: int = 5
    persistence_count: int = 3

    # layers scoring below this are folded back into the baseline
    good_layer_score: float = 0.2


class TextureState(StrEnum):
    # nothing to compare against yet, still collecting the first layers
    LEARNING = "learning"
    SCORED = "scored"
    # couldn't judge this layer (glare, part too small). the fusion step should treat this as
    # "no information", not as "looks fine"
    UNKNOWN = "unknown"


@dataclass
class TextureResult:
    layer: int
    state: TextureState
    # persistent 0-1 failure confidence, what the fusion step should use. None until scoring starts
    score: float | None = None
    # this layer on its own, before the persistence rule
    layer_score: float | None = None
    unusual_tile_fraction: float | None = None
    tile_count: int = 0
    reason: str | None = None
    # (row, column) of each unusual tile's top-left corner in the roi, for drawing an overlay
    unusual_tiles: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class _ParityBaseline:
    pool: BaselinePool
    reference: TextureReference | None = None
    # share of unusual tiles on each baseline layer, so a layer can be compared against what
    # "normal" noise looks like for this print rather than a fixed cutoff
    unusual_fractions: list[float] = field(default_factory=list)


class TextureDetector:
    # compares each layer's surface texture against earlier good layers of the same print.
    # one instance per print: call reset() (or make a new one) when a new print starts

    def __init__(self, config: TextureConfig | None = None):
        self.config = config or TextureConfig()
        self.reset()

    def reset(self):
        self._baselines: dict[int, _ParityBaseline] = {}
        self._recent_layer_scores: deque[float] = deque(maxlen=self.config.persistence_window)

    def analyze_layer(
        self, image: np.ndarray, layer: int, mask: np.ndarray | None = None
    ) -> TextureResult:
        # image: a still of the part taken at this layer change, already cropped to the part
        # (bgr or grayscale). mask: optional bool array, True where the part is
        config = self.config
        gray = to_grayscale(image)
        if mask is None:
            mask = np.ones(gray.shape, dtype=bool)

        part_pixels = gray[mask]
        if part_pixels.size == 0:
            return TextureResult(layer, TextureState.UNKNOWN, reason="Part isn't in view")
        saturated = (part_pixels <= config.saturation_low) | (part_pixels >= config.saturation_high)
        if saturated.mean() > config.max_saturated_fraction:
            return TextureResult(layer, TextureState.UNKNOWN, reason="Too much glare or shadow")

        # saturated pixels are excluded before clahe would stretch them into fake texture
        usable = mask & (gray > config.saturation_low) & (gray < config.saturation_high)
        normalised = normalise_contrast(gray, config.clahe_clip_limit, config.clahe_grid_size)
        features = extract_tile_features(
            normalised, usable, config.layer_pitch_px, config.tile_layers, config.min_usable_fraction
        )
        tile_count = len(features.values)
        if tile_count < config.min_tiles:
            return TextureResult(
                layer, TextureState.UNKNOWN, tile_count=tile_count, reason="Too little of the part in view"
            )

        if layer < config.baseline_first_layer:
            return TextureResult(layer, TextureState.LEARNING, tile_count=tile_count)

        parity = layer % 2 if config.separate_parity else 0
        baseline = self._baselines.setdefault(
            parity, _ParityBaseline(pool=BaselinePool(config.max_baseline_tiles))
        )

        baseline_end = config.baseline_first_layer + config.baseline_layer_count
        if layer < baseline_end or not self._baseline_ready(baseline):
            baseline.pool.add_initial(layer, features)
            return TextureResult(layer, TextureState.LEARNING, tile_count=tile_count)

        if baseline.reference is None:
            self._fit_baseline(baseline)

        distances = baseline.reference.distances(features)
        unusual = distances.rms_z > config.tile_rms_z_threshold
        unusual_fraction = float(unusual.mean())

        fractions = np.asarray(baseline.unusual_fractions)
        spread = max(float(fractions.std()), config.unusual_fraction_std_floor)
        layer_z = (unusual_fraction - float(fractions.mean())) / spread
        layer_score = self._layer_z_to_score(layer_z)

        self._recent_layer_scores.append(layer_score)
        score = self._persistent_score()

        if layer_score < config.good_layer_score:
            baseline.pool.add_recent(layer, features)
            baseline.unusual_fractions.append(unusual_fraction)
            baseline.reference = baseline.pool.fit()

        reason = None
        if layer_score >= 0.5 and unusual.any():
            reason = self._explain(distances.feature_z[unusual])

        return TextureResult(
            layer=layer,
            state=TextureState.SCORED,
            score=score,
            layer_score=layer_score,
            unusual_tile_fraction=unusual_fraction,
            tile_count=tile_count,
            reason=reason,
            unusual_tiles=[tuple(int(value) for value in origin) for origin in features.origins[unusual]],
        )

    def _baseline_ready(self, baseline: _ParityBaseline) -> bool:
        # needs enough layers to estimate layer-to-layer noise and enough tiles for a stable
        # covariance (several per feature). if the part is tiny, learning just runs longer
        enough_layers = len(baseline.pool.layers()) >= 3
        enough_tiles = baseline.pool.tile_count() >= 5 * len(SCORED_FEATURE_NAMES)
        return enough_layers and enough_tiles

    def _fit_baseline(self, baseline: _ParityBaseline):
        # leave-one-layer-out: each baseline layer is scored against a reference built without it.
        # scoring it against itself would make normal layers look cleaner than they really are,
        # and every later layer would look worse by comparison
        config = self.config
        for layer, features in sorted(baseline.pool.layers().items()):
            held_out = baseline.pool.fit(excluded_layer=layer)
            distances = held_out.distances(features)
            baseline.unusual_fractions.append(
                float((distances.rms_z > config.tile_rms_z_threshold).mean())
            )
        baseline.reference = baseline.pool.fit()

    def _layer_z_to_score(self, layer_z: float) -> float:
        # a logistic centred on score_midpoint_z, rescaled so a layer exactly as clean as the
        # baseline scores 0 instead of the curve's ~5% tail, which the ui would show as a reading
        def logistic(value: float) -> float:
            return 1.0 / (1.0 + math.exp(-(value - self.config.score_midpoint_z) / self.config.score_scale))

        floor = logistic(0.0)
        return max(0.0, (logistic(layer_z) - floor) / (1.0 - floor))

    def _persistent_score(self) -> float:
        scores = sorted(self._recent_layer_scores, reverse=True)
        if len(scores) < self.config.persistence_count:
            return 0.0
        return scores[self.config.persistence_count - 1]

    @staticmethod
    def _explain(unusual_feature_z: np.ndarray) -> str:
        best_reason = None
        best_strength = 0.0
        for column, name in enumerate(SCORED_FEATURE_NAMES):
            direction, reason = FEATURE_REASONS[name]
            strength = float((unusual_feature_z[:, column] * direction).mean())
            if strength > best_strength:
                best_strength = strength
                best_reason = reason
        return best_reason or "Surface texture changed from the earlier layers"
