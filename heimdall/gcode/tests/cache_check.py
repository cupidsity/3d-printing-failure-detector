"""Demonstrate cache creation, reuse, memory mapping, and invalidation."""

from __future__ import annotations

import gc
from pathlib import Path
import tempfile

import numpy as np

from heimdall.gcode import GCodeCache


# Function: main
# Exercises cache creation, reuse, memory mapping, and content invalidation.
#
# Inputs: None.
#
# Output: A process exit status.
def main() -> int:
    # Create disposable input and cache data inside the Phase 1 folder.
    parent = Path(__file__).parent
    with tempfile.TemporaryDirectory(dir=parent) as directory:
        workspace = Path(directory)
        source = workspace / "part.gcode"
        source.write_bytes(b"G90\nM83\nG1 X10 Z0.2 E1\n")
        cache = GCodeCache(workspace / "cache")

        # Confirm the cold request creates a new artifact.
        first = cache.get_or_parse(source)
        assert not first.cache_hit and first.cache_path.is_dir()
        print("PASS: first run was a cache miss and created an artifact.")

        # Confirm an identical request skips parsing and uses memory mapping.
        repeat = cache.get_or_parse(source)
        assert repeat.cache_hit and repeat.parsing_skipped
        assert isinstance(repeat.job.segments, np.memmap)
        print("PASS: identical repeat was a cache hit and skipped parsing.")
        print("PASS: cached arrays were loaded with memory mapping.")

        # Release Windows file mappings before changing and cleaning the fixture.
        first_hash = first.job.source_hash
        del repeat
        gc.collect()
        # Confirm changed source content cannot reuse the previous artifact.
        source.write_bytes(b"G90\nM83\nG1 X20 Z0.2 E2\nG1 X30 E1\n")
        changed = cache.get_or_parse(source)
        assert not changed.cache_hit and changed.job.source_hash != first_hash
        print("PASS: changed input invalidated the cache and produced a new hash.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

