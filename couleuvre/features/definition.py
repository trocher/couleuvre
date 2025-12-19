"""
Definition finding functionality for the Vyper Language Server.

This module provides the go-to-definition feature, resolving symbols
to their definition locations across modules.
"""

import logging
from typing import Optional

from lsprotocol import types
from pygls.workspace import TextDocument

from couleuvre.parser import Module
from couleuvre import utils
from couleuvre.features.resolve import resolve_symbol_for_word

logger = logging.getLogger("couleuvre")


def get_definition_location(
    get_module_func,
    workspace,
    doc: TextDocument,
    module: Module,
    position: types.Position,
) -> Optional[types.Location]:
    """
    Get the definition location for the symbol at the given position.

    Args:
        get_module_func: Function to get a module for a document.
        workspace: The LSP workspace.
        doc: The current document.
        module: The current module.
        position: The cursor position.

    Returns:
        Location of the definition, or None if not found.
    """
    attribute_word = utils.get_attribute_word(doc, position)
    if not attribute_word:
        return None

    resolved = resolve_symbol_for_word(
        get_module_func, workspace, doc, module, attribute_word, position
    )
    if not resolved:
        return None

    if resolved.node is None:
        # Pointing to an import itself, go to start of imported file
        return utils.location_from_start(resolved.uri)

    return types.Location(uri=resolved.uri, range=utils.range_from_node(resolved.node))
