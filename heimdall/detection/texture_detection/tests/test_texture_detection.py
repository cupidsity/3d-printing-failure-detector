from __future__ import annotations

import unittest

import numpy as np

from heimdall.detection.texture_detection import TextureConfig, TextureDetector, TextureState
from heimdall.detection.texture_detection.features import (
    LBP_BIN_COUNT,
    LBP_TABLE,
    extract_tile_features,
    periodicity_strength,
)

IMAGE_HEIGHT = 192
IMAGE_WIDTH = 240
LAYER_PITCH_PX = 4.0


def layered_wall(seed: int, brightness: float = 1.0) -> np.ndarray:
    # stand-in for a side-on still of a good wall: horizontal layer lines at a fixed pitch,
    # a little sensor noise and a soft lighting gradient, like a real print under one lamp
    generator = np.random.default_rng(seed)
    rows = np.arange(IMAGE_HEIGHT, dtype=np.float64)[:, None]
    columns = np.arange(IMAGE_WIDTH, dtype=np.float64)[None, :]
    # each layer bulges slightly differently, so lines aren't perfectly straight
    wobble = 0.3 * np.sin(columns / 23.0 + seed)
    stripes = 45.0 * np.sin(2 * np.pi * (rows + wobble) / LAYER_PITCH_PX)
    lighting = 20.0 * columns / IMAGE_WIDTH
    image = 120.0 + stripes + lighting + generator.normal(0.0, 6.0, (IMAGE_HEIGHT, IMAGE_WIDTH))
    return np.clip(image * brightness, 0, 255).astype(np.uint8)


def under_extruded_wall(seed: int) -> np.ndarray:
    # missing and broken lines with rough patches across the lower half of the part, which is
    # what a clog or low flow looks like from the side
    image = layered_wall(seed).astype(np.float64)
    generator = np.random.default_rng(seed + 1000)
    lower_half = slice(IMAGE_HEIGHT // 2, IMAGE_HEIGHT)
    image[lower_half] = 0.5 * image[lower_half] + 0.5 * generator.normal(
        120.0, 40.0, image[lower_half].shape
    )
    return np.clip(image, 0, 255).astype(np.uint8)


def run_print(images_by_layer) -> list:
    detector = TextureDetector(TextureConfig(layer_pitch_px=LAYER_PITCH_PX))
    return [detector.analyze_layer(image, layer) for layer, image in images_by_layer]


class FeatureTests(unittest.TestCase):
    def test_lbp_table_keeps_every_uniform_pattern(self):
        # 58 uniform 8-neighbour patterns plus one bin for everything else
        self.assertEqual(LBP_BIN_COUNT, 59)
        self.assertEqual(LBP_TABLE[0], 0)

    def test_periodicity_is_high_for_layer_lines_and_low_for_noise(self):
        tile_size = int(LAYER_PITCH_PX * 6)
        wall_tile = layered_wall(seed=1)[:tile_size, :tile_size]
        noise_tile = np.random.default_rng(2).integers(0, 256, (tile_size, tile_size)).astype(np.uint8)
        self.assertGreater(periodicity_strength(wall_tile, LAYER_PITCH_PX), 0.8)
        self.assertLess(periodicity_strength(noise_tile, LAYER_PITCH_PX), 0.5)

    def test_tiles_outside_the_mask_are_skipped(self):
        image = layered_wall(seed=3)
        usable = np.zeros(image.shape, dtype=bool)
        usable[:, : IMAGE_WIDTH // 2] = True
        everything = extract_tile_features(image, np.ones(image.shape, dtype=bool), LAYER_PITCH_PX, 6, 0.9)
        left_half = extract_tile_features(image, usable, LAYER_PITCH_PX, 6, 0.9)
        self.assertEqual(len(left_half.values), len(everything.values) // 2)


class DetectorTests(unittest.TestCase):
    def test_good_print_stays_low(self):
        results = run_print((layer, layered_wall(seed=layer)) for layer in range(40))
        scored = [result for result in results if result.state == TextureState.SCORED]
        self.assertTrue(scored, "the baseline never finished learning")
        self.assertLess(max(result.score for result in scored), 0.3)

    def test_learning_comes_before_scoring(self):
        results = run_print((layer, layered_wall(seed=layer)) for layer in range(15))
        self.assertTrue(all(result.state == TextureState.LEARNING for result in results[:11]))
        self.assertTrue(all(result.score is None for result in results[:11]))

    def test_persistent_defect_raises_the_score_and_says_why(self):
        layers = [(layer, layered_wall(seed=layer)) for layer in range(20)]
        layers += [(layer, under_extruded_wall(seed=layer)) for layer in range(20, 30)]
        results = run_print(layers)
        self.assertLess(results[19].score, 0.3)
        self.assertGreater(results[24].score, 0.7)
        self.assertIsNotNone(results[24].reason)
        self.assertTrue(results[24].unusual_tiles)

    def test_one_bad_layer_is_ignored(self):
        layers = [
            (layer, under_extruded_wall(seed=layer) if layer == 20 else layered_wall(seed=layer))
            for layer in range(30)
        ]
        results = run_print(layers)
        self.assertGreater(results[20].layer_score, 0.5)
        self.assertLess(max(result.score for result in results[12:]), 0.3)

    def test_defect_doesnt_become_the_new_normal(self):
        layers = [(layer, layered_wall(seed=layer)) for layer in range(20)]
        layers += [(layer, under_extruded_wall(seed=layer)) for layer in range(20, 60)]
        results = run_print(layers)
        self.assertGreater(min(result.score for result in results[25:]), 0.7)

    def test_dimmer_lighting_alone_is_not_a_failure(self):
        # someone turns a room light off halfway through: clahe and the self-referenced baseline
        # should absorb it
        layers = [
            (layer, layered_wall(seed=layer, brightness=1.0 if layer < 20 else 0.6))
            for layer in range(35)
        ]
        results = run_print(layers)
        self.assertLess(max(result.score for result in results[12:]), 0.3)

    def test_glare_reports_unknown_instead_of_a_score(self):
        image = layered_wall(seed=5)
        image[:, : IMAGE_WIDTH // 2] = 255
        result = TextureDetector().analyze_layer(image, 15)
        self.assertEqual(result.state, TextureState.UNKNOWN)
        self.assertIsNone(result.score)

    def test_tiny_part_reports_unknown(self):
        mask = np.zeros((IMAGE_HEIGHT, IMAGE_WIDTH), dtype=bool)
        mask[:30, :30] = True
        result = TextureDetector().analyze_layer(layered_wall(seed=6), 15, mask)
        self.assertEqual(result.state, TextureState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
