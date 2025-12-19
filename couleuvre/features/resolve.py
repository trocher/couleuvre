"""
Symbol resolution utilities for the Vyper Language Server.

This module provides shared functionality for resolving symbols
across modules, used by both definition and references features.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

from lsprotocol import types
from pygls import uris
from pygls.workspace import TextDocument

from couleuvre.ast.nodes import BaseNode
from couleuvre.ast import nodes
from couleuvre.features.symbol_table import SymbolEntry
from couleuvre.parser import Module

logger = logging.getLogger("couleuvre")


@dataclass
class ResolvedSymbol:
    """Result of resolving a symbol to its definition."""

    node: Optional[BaseNode]
    module: Module
    uri: str
    entry: Optional[SymbolEntry] = None  # The symbol table entry, if available


def _find_enclosing_function(
    module: Module, position: types.Position
) -> Optional[nodes.FunctionDef]:
    """
    Find the function that contains the given position.

    Args:
        module: The module to search in.
        position: The cursor position (0-based line).

    Returns:
        The FunctionDef node containing the position, or None if at module level.
    """
    line = position.line + 1  # AST uses 1-based line numbers
    for node in module.ast.body:
        if isinstance(node, nodes.FunctionDef):
            if node.lineno <= line <= node.end_lineno:
                return node
    return None


def _is_inside_declaration_context(module: Module, position: types.Position) -> bool:
    """
    Check if the given position is inside a declaration context where names are
    definitions, not references (e.g., flag members, event fields, struct fields).

    Args:
        module: The module to search in.
        position: The cursor position (0-based line).

    Returns:
        True if position is inside a FlagDef, EventDef, or StructDef body.
    """
    line = position.line + 1  # AST uses 1-based line numbers
    for node in module.ast.body:
        if isinstance(node, (nodes.FlagDef, nodes.EventDef, nodes.StructDef)):
            # Check if we're inside this definition but NOT on the declaration line
            if node.lineno < line <= node.end_lineno:
                return True
    return False


def _is_at_module_level(module: Module, position: types.Position) -> bool:
    """
    Check if the given position is at module level (direct child of Module).

    Args:
        module: The module to search in.
        position: The cursor position (0-based line).

    Returns:
        True if position is at module level, False if nested inside something.
    """
    line = position.line + 1  # AST uses 1-based line numbers
    for node in module.ast.body:
        if node.lineno <= line <= node.end_lineno:
            # Position is within this top-level node
            # It's module level only if it's on the node's declaration line itself
            # (not inside a function body, etc.)
            return line == node.lineno
    # Not inside any top-level node - must be module level (e.g., blank lines)
    return True


def _resolve_in_namespace(
    module: Module,
    chain: List[str],
    external: bool = False,
    allow_self_fallback: bool = True,
) -> Optional[BaseNode]:
    """
    Resolve an identifier chain within a module's namespace.

    Args:
        module: The module to search in.
        chain: The identifier chain (e.g., ['self', 'foo', 'bar']).
        external: If True, search the external namespace (for imports).
        allow_self_fallback: If True, try self.X when X is not found directly.

    Returns:
        The resolved BaseNode, or None if not found.
    """
    namespace = module.external_namespace() if external else module.namespace
    first_iteration = True
    for part in chain:
        if not isinstance(namespace, dict):
            return None
        inner_namespace = namespace.get(part)
        if inner_namespace is None:
            if first_iteration and not external and allow_self_fallback:
                inner_namespace = namespace.get("self", {}).get(part)
                if inner_namespace is None:
                    return None
            else:
                return None
        namespace = inner_namespace
        first_iteration = False
    if isinstance(namespace, BaseNode):
        return namespace
    return None


def resolve_symbol_for_word(
    get_module_func,
    workspace,
    doc: TextDocument,
    module: Module,
    attribute_word: str,
    position: Optional[types.Position] = None,
) -> Optional[ResolvedSymbol]:
    """
    Resolve a symbol from an attribute word (e.g., 'self.foo', 'imported.Bar').

    Args:
        get_module_func: Function to get a module for a document.
        workspace: The LSP workspace.
        doc: The current document.
        module: The current module.
        attribute_word: The word to resolve (e.g., 'self.foo').
        position: The cursor position (used to determine scope).

    Returns:
        ResolvedSymbol with the node, module, and URI, or None if not found.
    """
    parts = attribute_word.split(".")

    # Don't resolve names inside declaration contexts (flag/event/struct members)
    if position is not None and _is_inside_declaration_context(module, position):
        return None

    # Find enclosing function for local variable resolution
    enclosing_function = None
    if position is not None:
        enclosing_function = _find_enclosing_function(module, position)

    # Try to resolve using the symbol table (supports local variables)
    if len(parts) == 1 and enclosing_function is not None:
        # Single name inside a function - check local scope first
        entry = module.symbol_table.resolve(parts, position, enclosing_function)
        if entry is not None:
            return ResolvedSymbol(entry.node, module, doc.uri, entry)

    # Try module-level resolution via symbol table
    entry = module.symbol_table.resolve(parts, position, enclosing_function)
    if entry is not None:
        return ResolvedSymbol(entry.node, module, doc.uri, entry)

    # Fall back to legacy namespace resolution for backward compatibility
    allow_self_fallback = True
    if position is not None and not _is_at_module_level(module, position):
        allow_self_fallback = False

    resolved_node = _resolve_in_namespace(
        module, parts, allow_self_fallback=allow_self_fallback
    )
    if resolved_node:
        return ResolvedSymbol(resolved_node, module, doc.uri)

    # Try to resolve as an import
    root_name, remainder = parts[0], parts[1:]
    if root_name not in module.imports:
        return None

    resolved_path = module.imports[root_name]
    resolved_uri = uris.from_fs_path(resolved_path)
    if not resolved_uri:
        return None

    try:
        resolved_doc = workspace.get_text_document(resolved_uri)
    except Exception:
        return None
    resolved_module = get_module_func(resolved_doc)

    # If no remainder, we're pointing to the import itself
    if not remainder:
        return ResolvedSymbol(None, resolved_module, resolved_doc.uri)

    resolved_node = _resolve_in_namespace(resolved_module, remainder, external=True)
    if not resolved_node:
        return None
    return ResolvedSymbol(resolved_node, resolved_module, resolved_doc.uri)
