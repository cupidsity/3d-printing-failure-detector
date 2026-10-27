# Manual verification checklist

Run these commands from the repository root after completing the setup in the parent usage guide.

## 1. Parser smoke test

```powershell
python -m heimdall.gcode.manual_tests.smoke_test
```

Expected output:

```text
PASS: Cura fixture produced 5 segments across 2 layers with no warnings.
```

A nonzero exit, traceback, a different segment/layer count, or warnings means the parser fixture check failed.

## 2. Cache behavior

```powershell
python -m heimdall.gcode.manual_tests.cache_check
```

Expected output consists of four `PASS` lines confirming the first miss, repeated hit with skipped parsing, memory mapping, and changed-input invalidation.

A traceback, missing `PASS` line, a repeat reported as a miss, or changed input reported as a hit means caching failed.

## 3. CLI and JSON output

```powershell
python -m heimdall.gcode parse heimdall/gcode/fixtures/cura_square.gcode --cache-dir heimdall/gcode/manual_tests/.cli-cache --json
python -m heimdall.gcode parse heimdall/gcode/fixtures/cura_square.gcode --cache-dir heimdall/gcode/manual_tests/.cli-cache --json
```

Expected result: the first JSON document contains `"cache_hit": false`; the second contains `"cache_hit": true`, `"parsing_skipped": true`, `"segments": 5`, and `"layers": 2`.

Failure looks like invalid JSON, a traceback, incorrect counts, or a second cache miss.

Clean up this manual cache with:

```powershell
python -m heimdall.gcode clear-cache --cache-dir heimdall/gcode/manual_tests/.cli-cache
```

## 4. Layer preview

```powershell
python -m heimdall.gcode preview heimdall/gcode/fixtures/cura_square.gcode --layer 0 --output heimdall/gcode/manual_tests/layer-0.svg
```

Expected result: `Wrote ...layer-0.svg`, and the SVG opens as a four-sided cyan toolpath on a dark background.

A traceback, missing file, empty image, or a shape other than a square indicates a failure. The generated SVG is disposable.

## 5. Real-file performance check

```powershell
python -m heimdall.gcode.manual_tests.benchmark C:\path\to\your\print.gcode
```

On Raspberry Pi OS, use the same command with `python3` and a Linux path. Expected output includes input size, segment count, cold and warm times, a speed ratio, and `PASS: warm run hit the cache and skipped parsing.`

A nonzero exit, cache miss on the warm run, or memory exhaustion is a failure. Timing ratios vary by storage and file size; correctness depends on the `PASS` line, not a fixed ratio.

