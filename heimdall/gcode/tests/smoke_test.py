"""Parse the bundled Cura fixture and check its normalized output."""

from __future__ import annotations

from pathlib import Path

from heimdall.gcode import parse_file


# Function: main
# Parses the bundled Cura fixture and validates its expected geometry summary.
#
# Inputs: None.
#
# Output: A process exit status.
def main() -> int:
    fixture = Path(__file__).parents[1] / "fixtures" / "cura_square.gcode"
    job = parse_file(fixture)
    assert job.segments.size == 5, job.summary()
    assert job.layer_count == 2, job.summary()
    assert not job.warnings, job.warnings
    assert int(job.layer_offsets[-1]) == job.segments.size
    print("PASS: Cura fixture produced 5 segments across 2 layers with no warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

