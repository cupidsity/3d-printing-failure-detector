"""Command-line entry point for parsing, caching, and diagnostics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .cache import GCodeCache
from .diagnostics import write_layer_svg


# Function: _cache_for
# Selects an explicit cache directory or a stable directory beside the source.
#
# Inputs:
# * source: Path
# * cache_dir: str | None
#
# Output: A configured GCodeCache.
def _cache_for(source: Path, cache_dir: str | None) -> GCodeCache:
    root = Path(cache_dir) if cache_dir else source.parent / ".heimdall-gcode-cache"
    return GCodeCache(root)


# Function: _parse_command
# Parses or loads a G-code file and prints its geometry/cache summary.
#
# Inputs:
# * arguments: argparse.Namespace
#
# Output: A process exit status.
def _parse_command(arguments: argparse.Namespace) -> int:
    source = Path(arguments.source).resolve()
    result = _cache_for(source, arguments.cache_dir).get_or_parse(source)
    # Combine parser statistics with observable cache information.
    payload = result.job.summary()
    payload.update(
        {
            "cache_hit": result.cache_hit,
            "parsing_skipped": result.parsing_skipped,
            "cache_path": str(result.cache_path),
            "total_seconds": result.total_seconds,
            "parse_seconds": result.parse_seconds,
        }
    )
    # Print either integration-friendly JSON or compact human-readable output.
    if arguments.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        status = "HIT (parsing skipped)" if result.cache_hit else "MISS (cache created)"
        print(f"Cache: {status}")
        print(f"Layers: {payload['layers']}")
        print(f"Segments: {payload['segments']}")
        print(f"Events: {payload['events']}")
        print(f"Warnings: {payload['warnings']}")
        print(f"Artifact: {result.cache_path}")
    return 0


# Function: _preview_command
# Loads a G-code job and writes the requested diagnostic layer preview.
#
# Inputs:
# * arguments: argparse.Namespace
#
# Output: A process exit status.
def _preview_command(arguments: argparse.Namespace) -> int:
    source = Path(arguments.source).resolve()
    result = _cache_for(source, arguments.cache_dir).get_or_parse(source)
    output = write_layer_svg(result.job, arguments.layer, arguments.output)
    print(f"Wrote {output}")
    return 0


# Function: _clear_command
# Removes generated artifacts from one explicitly selected cache directory.
#
# Inputs:
# * arguments: argparse.Namespace
#
# Output: A process exit status.
def _clear_command(arguments: argparse.Namespace) -> int:
    removed = GCodeCache(arguments.cache_dir).clear()
    print(f"Removed {removed} cached artifact(s).")
    return 0


# Function: build_parser
# Defines the command-line interface and its parse, preview, and clear commands.
#
# Inputs: None.
#
# Output: The configured argument parser.
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Parse G-code into memory-efficient expected-print geometry."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    parse = commands.add_parser("parse", help="parse a file or load its cache")
    parse.add_argument("source", help="path to a G-code file")
    parse.add_argument("--cache-dir", help="cache directory")
    parse.add_argument("--json", action="store_true", help="emit JSON")
    parse.set_defaults(handler=_parse_command)

    preview = commands.add_parser("preview", help="write a top-down layer SVG")
    preview.add_argument("source", help="path to a G-code file")
    preview.add_argument("--layer", type=int, default=0)
    preview.add_argument("--output", required=True, help="destination SVG")
    preview.add_argument("--cache-dir", help="cache directory")
    preview.set_defaults(handler=_preview_command)

    clear = commands.add_parser("clear-cache", help="remove generated cache data")
    clear.add_argument("--cache-dir", required=True, help="cache directory")
    clear.set_defaults(handler=_clear_command)
    return parser


# Function: main
# Parses command-line arguments and runs the selected command handler.
#
# Inputs:
# * argv: list[str] | None
#
# Output: A process exit status.
def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    return int(arguments.handler(arguments))


if __name__ == "__main__":
    raise SystemExit(main())

