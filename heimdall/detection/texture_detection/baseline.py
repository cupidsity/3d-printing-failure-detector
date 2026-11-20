from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .features import FEATURE_NAMES, TileFeatures

# name of the extra column the baseline adds on top of FEATURE_NAMES
LBP_DRIFT_NAME = "lbp_drift"
SCORED_FEATURE_NAMES = FEATURE_NAMES + (LBP_DRIFT_NAME,)

# how far the covariance is pulled toward its diagonal. with only a few hundred baseline tiles
# the off-diagonal terms are noisy, and an unshrunk inverse blows up along those noisy directions
COVARIANCE_SHRINKAGE = 0.2


def chi_square_distance(histograms: np.ndarray, reference: np.ndarray) -> np.ndarray:
    return 0.5 * ((histograms - reference) ** 2 / (histograms + reference + 1e-10)).sum(axis=1)


@dataclass
class TileDistances:
    # mahalanobis distance divided by sqrt(feature count), so it reads like an average z-score
    # and the "3 means unusual" rule of thumb holds no matter how many features there are
    rms_z: np.ndarray
    # per tile, per feature, how many standard deviations from the baseline. only used to say
    # which kind of change caused a flag
    feature_z: np.ndarray


class TextureReference:
    # what "normal" texture looks like for one print, fitted from its own good layers

    def __init__(self, features: TileFeatures):
        self.mean_histogram = features.lbp_histograms.mean(axis=0)
        values = self._with_lbp_drift(features)

        self.center = values.mean(axis=0)
        covariance = np.cov(values, rowvar=False)
        diagonal = np.diag(np.diag(covariance))
        shrunk = (1 - COVARIANCE_SHRINKAGE) * covariance + COVARIANCE_SHRINKAGE * diagonal
        # a ridge keeps features that never varied in the baseline (e.g. a perfectly flat
        # synthetic image) from dividing by zero
        shrunk += np.eye(len(self.center)) * 1e-6 * max(float(np.trace(shrunk)), 1e-6)
        self.inverse_covariance = np.linalg.inv(shrunk)
        self.feature_std = np.sqrt(np.maximum(np.diag(shrunk), 1e-12))

    def _with_lbp_drift(self, features: TileFeatures) -> np.ndarray:
        drift = chi_square_distance(features.lbp_histograms, self.mean_histogram)
        return np.column_stack([features.values, drift])

    def distances(self, features: TileFeatures) -> TileDistances:
        values = self._with_lbp_drift(features)
        offsets = values - self.center
        squared = np.einsum("ij,jk,ik->i", offsets, self.inverse_covariance, offsets)
        return TileDistances(
            rms_z=np.sqrt(np.maximum(squared, 0.0) / len(self.center)),
            feature_z=offsets / self.feature_std,
        )


def stack_features(parts: list[TileFeatures]) -> TileFeatures:
    return TileFeatures(
        values=np.concatenate([part.values for part in parts]),
        lbp_histograms=np.concatenate([part.lbp_histograms for part in parts]),
        origins=np.concatenate([part.origins for part in parts]),
    )


class BaselinePool:
    # the tiles a reference is fitted from, grouped by layer. the first layers are always kept.
    # later layers are only added when they scored as good, and the oldest of those are dropped
    # first when the pool is full, so a slowly worsening surface can't drag "normal" along with it

    def __init__(self, max_tiles: int):
        self.max_tiles = max_tiles
        self.initial_layers: dict[int, TileFeatures] = {}
        self.recent_layers: dict[int, TileFeatures] = {}

    def add_initial(self, layer: int, features: TileFeatures):
        self.initial_layers[layer] = features

    def add_recent(self, layer: int, features: TileFeatures):
        self.recent_layers[layer] = features
        while self.tile_count() > self.max_tiles and self.recent_layers:
            oldest = min(self.recent_layers)
            del self.recent_layers[oldest]

    def layers(self) -> dict[int, TileFeatures]:
        return {**self.initial_layers, **self.recent_layers}

    def tile_count(self) -> int:
        return sum(len(part.values) for part in self.layers().values())

    def fit(self, excluded_layer: int | None = None) -> TextureReference:
        parts = [
            features for layer, features in sorted(self.layers().items()) if layer != excluded_layer
        ]
        return TextureReference(stack_features(parts))
