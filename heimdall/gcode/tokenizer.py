"""Streaming tokenization that preserves exact G-code byte positions."""

from __future__ import annotations

from collections.abc import Iterator
import hashlib
import re
from pathlib import Path
from typing import BinaryIO

from .models import TokenRecord


_WORD_RE = re.compile(
    r"([A-Za-z])([-+]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][-+]?\d+)?)"
)


# Function: _normalize_command
# Formats a parsed command word into a stable uppercase representation.
#
# Inputs:
# * letter: str
# * value: float
#
# Output: A normalized command such as G1 or M82.
def _normalize_command(letter: str, value: float) -> str:
    if value.is_integer():
        number = str(int(value))
    else:
        number = format(value, ".12g")
    return f"{letter.upper()}{number}"


# Function: _xor_checksum
# Calculates the RepRap-style XOR checksum for a command payload.
#
# Inputs:
# * payload: bytes
#
# Output: The integer checksum.
def _xor_checksum(payload: bytes) -> int:
    value = 0
    for byte in payload:
        value ^= byte
    return value


# Function: tokenize_stream
# Reads a binary G-code stream once and yields source-located token records.
#
# Inputs:
# * stream: BinaryIO
# * digest: hashlib._Hash | None
#
# Output: An iterator of TokenRecord values.
def tokenize_stream(
    stream: BinaryIO, digest: hashlib._Hash | None = None
) -> Iterator[TokenRecord]:
    """Yield token records while reading a binary stream exactly once."""

    # Read raw bytes so hashes and file-position offsets remain exact.
    byte_start = 0
    for line_number, raw_bytes in enumerate(stream, start=1):
        if digest is not None:
            digest.update(raw_bytes)
        byte_end = byte_start + len(raw_bytes)
        source_bytes = raw_bytes.rstrip(b"\r\n")
        if line_number == 1:
            source_bytes = source_bytes.removeprefix(b"\xef\xbb\xbf")

        code_bytes, separator, comment_bytes = source_bytes.partition(b";")
        comment = (
            comment_bytes.decode("utf-8", errors="replace").strip()
            if separator
            else ""
        )

        # Separate and validate the optional line checksum.
        checksum: int | None = None
        checksum_valid: bool | None = None
        payload_bytes, star, checksum_bytes = code_bytes.partition(b"*")
        if star:
            try:
                checksum = int(checksum_bytes.strip())
                checksum_valid = _xor_checksum(payload_bytes) == checksum
            except ValueError:
                checksum_valid = False
            code_bytes = payload_bytes

        # Tokenize valid letter-number words and preserve malformed gaps.
        code = code_bytes.decode("ascii", errors="replace")
        matches = list(_WORD_RE.finditer(code))
        lexical_errors: list[str] = []
        cursor = 0
        for match in matches:
            gap = code[cursor : match.start()].strip()
            if gap and gap != "%":
                lexical_errors.append(gap)
            cursor = match.end()
        tail = code[cursor:].strip()
        if tail and tail != "%":
            lexical_errors.append(tail)

        # Classify the first command word and collect remaining parameters.
        command: str | None = None
        parameters: dict[str, float] = {}
        program_line: int | None = None
        for match in matches:
            letter = match.group(1).upper()
            try:
                value = float(match.group(2))
            except ValueError:
                lexical_errors.append(match.group(0))
                continue
            if letter == "N" and command is None and program_line is None:
                program_line = int(value)
                continue
            if command is None and letter in {"G", "M", "T"}:
                command = _normalize_command(letter, value)
                continue
            parameters[letter] = value

        yield TokenRecord(
            line_number=line_number,
            byte_start=byte_start,
            byte_end=byte_end,
            raw=source_bytes.decode("utf-8", errors="replace"),
            command=command,
            parameters=parameters,
            comment=comment,
            program_line=program_line,
            checksum=checksum,
            checksum_valid=checksum_valid,
            lexical_errors=tuple(lexical_errors),
        )
        byte_start = byte_end


# Function: tokenize_file
# Opens a G-code file and streams its token records.
#
# Inputs:
# * path: str | Path
#
# Output: An iterator of TokenRecord values.
def tokenize_file(path: str | Path) -> Iterator[TokenRecord]:
    """Yield token records from a filesystem path."""

    with Path(path).open("rb") as stream:
        yield from tokenize_stream(stream)

