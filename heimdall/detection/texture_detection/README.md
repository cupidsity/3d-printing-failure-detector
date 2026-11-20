# Texture detection

Looks for rough surfaces, under-extrusion and gaps by comparing each layer's surface texture against the earlier good layers of the same print. It outputs a 0–1 failure confidence for the fusion step, plus a plain-language reason when it flags something.

## Why it compares the print to itself

In the published in-situ tests, thresholding a single texture number (GLCM contrast, entropy, line length) scored 45–64% accuracy, close to a coin flip. Comparing against a reference from the same print reached 81–87%. A per-print baseline also absorbs the filament colour, finish and lighting, which is what broke the fixed thresholds in earlier work.

## How it works

1. **Normalise.** Grayscale, then CLAHE. Glare and crushed shadows are masked out.
2. **Tile.** The crop is cut into square tiles `tile_layers` layer pitches tall (6 by default). Tiles mostly outside the part mask are skipped.
3. **Measure each tile.** Every tile is scaled to the same mean and spread first, so the features don't change when the room light does.

   | Feature | Measures | Goes wrong when |
   | --- | --- | --- |
   | `periodicity` | Share of the row-profile FFT power at the layer pitch | Lines go missing or turn noisy |
   | `fine_detail` | Laplacian variance (log) | The surface gets rough, or blobs and zits appear |
   | `line_continuity` | How well each column matches the tile's average layer profile | Lines break or have gaps |
   | `glcm_contrast`, `glcm_correlation` | 8-level co-occurrence between pixels one layer apart | Neighbouring layers stop matching |
   | `lbp_irregular` | Share of non-uniform LBP codes (orientation-preserving `nri_uniform`) | Fine irregular texture |
   | `lbp_drift` | Chi-square distance of the tile's LBP histogram from the baseline's | The texture changes character |

4. **Learn the baseline.** Layers 2–10 (`baseline_first_layer`, `baseline_layer_count`) become the reference, with odd and even layers kept separately because infill direction alternates. Learning continues past layer 10 if the part is too small to have enough tiles yet.
5. **Score each tile.** Each tile gets a Mahalanobis distance from the baseline, expressed as an average z-score. Past 3, the tile counts as unusual.
6. **Score each layer.** The share of unusual tiles is compared with how often baseline layers had unusual tiles, scored leave-one-layer-out so the baseline isn't graded against itself. That z-score goes through a logistic curve, centred at 3, into 0–1.
7. **Require persistence.** The reported `score` is the 3rd highest of the last 5 layer scores. One bad photo can't raise it, while three bad layers in a row can.
8. **Update the baseline.** Layers scoring under 0.2 are added to the baseline, and the first layers are always kept. A defect never becomes the new normal.

## Usage

```python
from heimdall.detection.texture_detection import TextureDetector, TextureConfig, TextureState

detector = TextureDetector(TextureConfig(layer_pitch_px=4.0))

# at each layer change, with a still of the part (cropped) and optionally a part mask
result = detector.analyze_layer(image, layer=current_layer, mask=part_mask)

if result.state == TextureState.SCORED:
    result.score      # 0-1, persistent; feed this to fusion
    result.reason     # e.g. "Layer lines are breaking up or missing", when a layer scores >= 0.5
elif result.state == TextureState.UNKNOWN:
    result.reason     # e.g. "Too much glare or shadow": no information, not "fine"

detector.reset()      # when a new print starts
```

`result.unusual_tiles` gives the top-left corner of each flagged tile, so the UI can outline where the problem is.

## What still needs building

- **Capturing the still.** The detector expects one sharp still per layer change with the head parked (the moonraker-timelapse `TIMELAPSE_TAKE_FRAME` pattern) and locked exposure, white balance and focus. Layer numbers come from `print_stats.info.current_layer`, which needs `SET_PRINT_STATS_INFO` in the slicer's layer-change gcode.
- **Cropping to the part.** Project Klipper's `exclude_object` polygons into the image with a one-time camera calibration, then erode a few millimetres. Until that exists, pass a hand-drawn crop and mask.
- **Camera resolution.** Layer lines need roughly 3–4 px per layer (about 0.05–0.1 mm/px). A 720p webcam watching the whole bed is about 0.19 mm/px and can't resolve them. `layer_pitch_px` has to match the real setup.
- **Running it on the Pi.** It takes about 25 ms per 512×512 crop on a desktop. It hasn't been timed on a Pi yet. Run it outside Moonraker's event loop.
- **Real test data.** The tests use synthetic striped walls. The next step is printing parts with the flow multiplier turned down on purpose (60–90%) and checking the scores against real photos.
- **Translucent, silk and glossy filament** are untested anywhere in the literature. Expect weak or unreliable scores.

## Tests

From the repository root:

```bash
python3 -m pip install -r heimdall/detection/texture_detection/requirements.txt
python3 -m unittest discover -s heimdall/detection/texture_detection/tests -t .
```
