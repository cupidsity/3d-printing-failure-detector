# G-code

Converts a sliced G-code file into compact, layer-addressable NumPy records for the expected printed toolpath. Later detection work can render these records in 3D or project them through a calibrated virtual camera without parsing the file again.

This is Phase 1 of the virtual-camera pipeline. Camera calibration, rendering, and image comparison are not included yet.

## Supported G-code

- One sequential parser pass for G-code cache misses.
- `G20`/`G21`, `G90`/`G91`, `M82`/`M83`, `G92`, feed rate, tools, per-tool extrusion state, `M200`, and `M221`.
- Extruding `G0`/`G1` moves and XY-plane `G2`/`G3` arcs with configurable chord error.
- Cura and PrusaSlicer layer, feature, width, height, and Z comments.
- Layer inference from positive-extrusion Z values when comments are absent; travel-only Z hops are ignored.
- Retraction, prime, firmware retract, and firmware unretract events without false printed geometry.
- Source byte-end offsets for synchronizing virtual progress with printer file position.
- SHA-256 source validation, parser/config fingerprints, NumPy files with `allow_pickle=False`, and read-only memory mapping on cache hits.
- A dependency-free SVG layer preview for diagnostics.

Unsupported commands are skipped with bounded warnings. Non-XY arcs are currently warned and omitted from geometry. Bézier moves, firmware-specific macros, and mesh/render generation are intentionally outside Phase 1.

## Structure

| Path | Responsibility |
| --- | --- |
| `tokenizer.py` | Streaming lexical analysis, comments, checksums, and byte offsets |
| `state.py` | Modal coordinate, extrusion, tool, unit, and flow state |
| `dialects/` | Cura and PrusaSlicer comment adapters |
| `geometry.py` | Distances and bounded-error arc tessellation |
| `parser.py` | State transitions and compact segment/event emission |
| `models.py` | Typed schemas, configuration, warnings, and result API |
| `cache.py` | Versioned artifacts, validation, atomic writes, and memory mapping |
| `diagnostics.py` | Lightweight top-down SVG layer preview |
| `cli.py` | Parse, preview, and cache-clear commands |
| `tests/` | Automated unit, integration, invariant, and cache tests |
| `manual_tests/` | User-runnable checks and benchmark |
| `fixtures/` | Small Cura, PrusaSlicer, and malformed-input samples |

Each segment is a 54-byte structured record containing start/end XYZ, extrusion delta, bead width/height, normalized layer, tool, feature ID, derivation flags, and the source command's ending byte offset. Retractions and primes use a separate compact event array.

## Setup

Python 3.11 or newer is recommended. On Raspberry Pi OS:

```bash
cd /path/to/3d-printing-failure-detector
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r heimdall/gcode/requirements.txt
```

On Windows PowerShell:

```powershell
cd C:\path\to\3d-printing-failure-detector
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r heimdall/gcode/requirements.txt
```

## Usage

Parse and cache a file:

```bash
python3 -m heimdall.gcode parse /path/to/print.gcode --cache-dir /path/to/cache
```

Run the same command again to validate the SHA-256 digest, skip parsing, and memory-map the cached arrays. Add `--json` for machine-readable diagnostics.

Create a layer preview:

```bash
python3 -m heimdall.gcode preview /path/to/print.gcode --layer 12 --output layer-12.svg --cache-dir /path/to/cache
```

## Worked Python example

```python
from heimdall.gcode import GCodeCache, ParserConfig

config = ParserConfig(chord_error=0.05)
result = GCodeCache("/var/cache/heimdall/gcode").get_or_parse(
    "/home/pi/gcodes/part.gcode",
    config,
)

print("cache hit:", result.cache_hit)
print("layers:", result.job.layer_count)
layer_10 = result.job.layer_segments(10)  # zero-copy NumPy slice
print("layer 10 segments:", layer_10.size)

# Find virtual geometry completed at Moonraker's file_position byte count.
last_segment = result.job.segment_index_at_file_position(file_position=250_000)
```

The next phase can consume `layer_segments()` directly for bead geometry or use the XYZ endpoints with calibrated camera matrices for 2D projection.

## How caching behaves

The index identity includes the absolute source path, parser schema version, and every parser option. A possible cache hit is then verified against file size, nanosecond modification time, and a fresh SHA-256 digest. This extra sequential read is intentionally cheaper than reparsing while still detecting content changes even if file size and timestamp are preserved.

On a miss, parsing and hashing occur together in one source pass. Artifacts are written to a temporary directory and atomically promoted. On a hit, parsing is skipped and the `.npy` arrays are loaded with `mmap_mode="r"`, allowing the operating system to page in only accessed regions.

Clear a cache explicitly:

```bash
python3 -m heimdall.gcode clear-cache --cache-dir /path/to/cache
```

Do not manually edit cache metadata. It is safe to clear generated cache data; the next parse recreates it from the original G-code.

## Automated tests

From the repository root:

```bash
python3 -m unittest discover -s heimdall/gcode/tests -v
```

The suite verifies positioning equivalence, extrusion modes and resets, travel/retraction suppression, Z-hop handling, Cura/Prusa metadata, arc endpoint and chord error, byte lookup, malformed input warnings, SVG output, cache creation, memory-mapped reuse, configuration invalidation, content invalidation, and cache clearing.

See [`manual_tests/README.md`](manual_tests/README.md) for checks that can be run on a development computer or Raspberry Pi.

## Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `ModuleNotFoundError: numpy` | Dependencies are not installed in the active environment | Activate the virtual environment and install `requirements.txt` |
| `No module named heimdall` | Command was run outside the repository root | Change to the repository root or add it to `PYTHONPATH` |
| Zero segments | File contains only travel, uses unsupported motion, or extrusion mode is unexpected | Run with `--json` and inspect warning counts; test the file in the diagnostic preview |
| Too many inferred layers | Extrusion occurs during a Z lift, or layer comments are missing/nonstandard | Add a slicer adapter or increase `layer_z_tolerance` in `ParserConfig` |
| `UNSUPPORTED_ARC` | Arc is malformed, exceeds the segment guard, or uses XZ/YZ plane | Linearize arcs in the slicer or extend `geometry.py` in a later phase |
| Cache never hits | Source content, parser config, or schema changes between runs | Compare the reported source hash/config fingerprint and use a stable cache directory |
| Cache clear fails on Windows | Another process still holds a memory-mapped array | Release the `ParsedJob`, stop the consuming process, then retry |
| Large cold-parse memory use | Extremely high segment count or very small arc chord error | Increase `chord_error`; the parser already uses typed growable buffers, and warm runs are memory-mapped |

## Phase boundary and assumptions

- G-code is treated as the expected toolpath, not a guarantee of actual machine motion.
- Width estimation uses extrusion volume divided by segment length and layer height; slicer-provided width/height wins when present.
- Layer numbers are normalized to contiguous zero-based indices in encounter order.
- The first camera-aware render or projection remains Phase 2 and should consume this stable array contract rather than reparsing G-code.
