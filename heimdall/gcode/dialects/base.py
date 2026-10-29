"""Shared contracts and composition for slicer comment adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class CommentMetadata:
    layer_change: bool = False
    layer_index: int | None = None
    z: float | None = None
    height: float | None = None
    width: float | None = None
    feature: str | None = None
    recognized: bool = False


class CommentAdapter(Protocol):
    # Function: parse
    # Interprets one slicer comment without retaining state.
    #
    # Inputs:
    # * self: CommentAdapter
    # * comment: str
    #
    # Output: Metadata recognized in the comment.
    def parse(self, comment: str) -> CommentMetadata:
        """Interpret one comment without retaining parser state."""


# Function: merge_comment_metadata
# Combines recognized values from all enabled slicer adapters.
#
# Inputs:
# * items: list[CommentMetadata]
#
# Output: One merged CommentMetadata value.
def merge_comment_metadata(items: list[CommentMetadata]) -> CommentMetadata:
    """Merge non-conflicting metadata returned by multiple adapters."""

    result = CommentMetadata()
    for item in items:
        if not item.recognized:
            continue
        result = CommentMetadata(
            layer_change=result.layer_change or item.layer_change,
            layer_index=(
                item.layer_index
                if item.layer_index is not None
                else result.layer_index
            ),
            z=item.z if item.z is not None else result.z,
            height=item.height if item.height is not None else result.height,
            width=item.width if item.width is not None else result.width,
            feature=item.feature if item.feature is not None else result.feature,
            recognized=True,
        )
    return result


# Function: build_adapters
# Constructs the configured slicer adapters in deterministic order.
#
# Inputs:
# * names: tuple[str, ...]
#
# Output: A list of comment adapters.
def build_adapters(names: tuple[str, ...]) -> list[CommentAdapter]:
    """Construct adapters in deterministic priority order."""

    from .cura import CuraCommentAdapter
    from .prusaslicer import PrusaSlicerCommentAdapter

    factories = {
        "cura": CuraCommentAdapter,
        "prusaslicer": PrusaSlicerCommentAdapter,
    }
    return [factories[name]() for name in names]

