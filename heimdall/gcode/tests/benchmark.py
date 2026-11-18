"""Measure cold parsing and warm cache loading for a selected G-code file."""

from __future__ import annotations

import argparse
import gc
from pathlib import Path
import shutil
import tempfile

from heimdall.gcode import GCodeCache


# Function: main
# Measures cold parsing and warm cache loading for a selected G-code file.
#
# Inputs: None. Command-line arguments are read with argparse.
#
# Output: A process exit status.
def main() -> int:
    # Validate the requested real-world G-code source.
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="G-code file to benchmark")
    arguments = parser.parse_args()
    source = arguments.source.resolve()
    if not source.is_file():
        parser.error(f"file does not exist: {source}")

    # Benchmark a disposable copy so existing caches cannot affect the cold run.
    with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
        workspace = Path(directory)
        copy = workspace / source.name
        shutil.copyfile(source, copy)
        cache = GCodeCache(workspace / "cache")
        cold = cache.get_or_parse(copy)
        warm = cache.get_or_parse(copy)
        assert not cold.cache_hit
        assert warm.cache_hit and warm.parsing_skipped
        # Report observed timings without requiring a fixed hardware-dependent ratio.
        ratio = cold.total_seconds / max(warm.total_seconds, 1e-12)
        print(f"Input bytes: {copy.stat().st_size}")
        print(f"Segments: {cold.job.segments.size}")
        print(f"Cold parse/cache: {cold.total_seconds:.6f} s")
        print(f"Warm hash/load: {warm.total_seconds:.6f} s")
        print(f"Observed speed ratio: {ratio:.2f}x")
        print("PASS: warm run hit the cache and skipped parsing.")
        del warm
        gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

