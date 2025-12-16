"""Utility functions for the Vyper Language Server."""

import logging
import re
from importlib.metadata import version
from typing import Optional

from lsprotocol.types import Location, Position, Range
from packaging.version import Version
from pygls.workspace import TextDocument

from couleuvre.ast.nodes import BaseNode

logger = logging.getLogger("couleuvre")


def get_installed_vyper_version() -> Optional[Version]:
    """Get the version of Vyper installed in the current environment."""
    try:
        return Version(version("vyper"))
    except Exception:
        return None


def range_from_node(node: BaseNode) -> Range:
    """Create an LSP Range from an AST node's position information."""
    return Range(
        start=Position(line=node.lineno - 1, character=node.col_offset),
        end=Position(line=node.end_lineno - 1, character=node.end_col_offset),
    )


def range_from_start() -> Range:
    """Create an LSP Range pointing to the start of a document."""
    return Range(
        start=Position(line=0, character=0),
        end=Position(line=0, character=0),
    )


def location_from_start(uri: str) -> Location:
    """Create an LSP Location pointing to the start of a document."""
    return Location(uri=uri, range=range_from_start())


def get_attribute_word(doc: TextDocument, position: Position) -> Optional[str]:
    """
    Extract the attribute word at the given position in a document.

    This captures dotted identifiers like 'self.foo' or 'module.Type'.

    Args:
        doc: The text document.
        position: The cursor position.

    Returns:
        The word at position (including dots), or None if not found.
    """
    try:
        attribute_word = doc.word_at_position(
            position, re.compile(r"[A-Za-z_0-9]+(?:\.[A-Za-z_0-9]+)*$")
        )
    except IndexError:
        return None
    return attribute_word
