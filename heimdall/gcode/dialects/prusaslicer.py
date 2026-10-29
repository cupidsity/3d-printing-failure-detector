"""Comment metadata emitted by PrusaSlicer and related Slic3r variants."""

from __future__ import annotations

import re

from .base import CommentMetadata


class PrusaSlicerCommentAdapter:
    _TYPE = re.compile(r"^TYPE:\s*(.+?)\s*$", re.IGNORECASE)
    _WIDTH = re.compile(r"^WIDTH:\s*([-+\d.eE]+)\s*$", re.IGNORECASE)
    _HEIGHT = re.compile(r"^HEIGHT:\s*([-+\d.eE]+)\s*$", re.IGNORECASE)
    _Z = re.compile(r"^Z:\s*([-+\d.eE]+)\s*$", re.IGNORECASE)

    # Function: parse
    # Extracts supported layer and feature metadata from one PrusaSlicer comment.
    #
    # Inputs:
    # * self: PrusaSlicerCommentAdapter
    # * comment: str
    #
    # Output: The metadata recognized in the comment.
    def parse(self, comment: str) -> CommentMetadata:
        text = comment.strip()
        if text.upper() == "LAYER_CHANGE":
            return CommentMetadata(layer_change=True, recognized=True)
        if match := self._TYPE.match(text):
            return CommentMetadata(feature=match.group(1).strip(), recognized=True)
        if match := self._WIDTH.match(text):
            return CommentMetadata(width=float(match.group(1)), recognized=True)
        if match := self._HEIGHT.match(text):
            return CommentMetadata(height=float(match.group(1)), recognized=True)
        if match := self._Z.match(text):
            return CommentMetadata(z=float(match.group(1)), recognized=True)
        return CommentMetadata()

