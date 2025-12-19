"""
Document symbol extraction for the Vyper Language Server.

This module provides functionality to extract document symbols (functions,
variables, structs, etc.) from a parsed Vyper module for IDE navigation.

Note: The actual symbol extraction is now handled by the SymbolTable built
during parsing. This module provides the interface for the LSP server.
"""

import logging
from typing import List, Optional, Tuple, Type

from lsprotocol import types
from lsprotocol.types import SymbolKind

from couleuvre.ast import nodes
from couleuvre.ast.nodes import BaseNode
from couleuvre.parser import Module
from couleuvre.utils import range_from_node

logger = logging.getLogger("couleuvre")


def get_document_symbols(module: Module) -> List[types.DocumentSymbol]:
    """
    Extract all document symbols from a parsed Vyper module.

    Args:
        module: The parsed Vyper module.

    Returns:
        List of DocumentSymbol objects representing the module's symbols.
    """
    return module.symbol_table.get_document_symbols()


# =============================================================================
# Legacy Visitor (kept for reference and potential edge cases)
# =============================================================================


class VyperNodeVisitorBase:
    """Base class for AST visitors that extract information from nodes."""

    ignored_types: Tuple[Type[BaseNode], ...] = ()
    scope_name: str = ""

    def visit(self, node: BaseNode, *args) -> List:
        """Visit a node and dispatch to the appropriate visitor method."""
        if isinstance(node, self.ignored_types):
            return []
        node_type = type(node).__name__
        visitor_fn = getattr(self, f"visit_{node_type}", None)
        if visitor_fn is None:
            return []
        return visitor_fn(node, *args)


def _make_symbol(
    node: BaseNode,
    name: str,
    kind: SymbolKind,
    children: Optional[List[types.DocumentSymbol]] = None,
) -> types.DocumentSymbol:
    """Create a DocumentSymbol from an AST node."""
    return types.DocumentSymbol(
        name=name,
        kind=kind,
        range=range_from_node(node),
        selection_range=range_from_node(node),
        children=children or [],
    )


class SymbolVisitor(VyperNodeVisitorBase):
    """
    Legacy AST visitor for symbol extraction.

    Note: This is kept for backward compatibility and edge cases.
    The primary symbol extraction is now done via SymbolTable during parsing.
    """

    def visit_Module(self, node):
        symbols = []
        for child in node.body:
            symbols += self.visit(child)
        return symbols

    def visit_VariableDecl(self, node):
        name = node.target.id
        kind = SymbolKind.Variable
        if node.is_constant or node.is_immutable:
            kind = SymbolKind.Constant
        return [_make_symbol(node, name, kind, [])]

    def visit_FlagDef(self, node):
        children = []
        for child in node.body:
            assert isinstance(child, nodes.Expr)
            children += self.visit(child.value, SymbolKind.EnumMember)
        return [_make_symbol(node, node.name, SymbolKind.Enum, children)]

    def visit_EventDef(self, node):
        return self._visit_struct_like(node, SymbolKind.Event)

    def visit_StructDef(self, node):
        return self._visit_struct_like(node, SymbolKind.Struct)

    def _visit_struct_like(self, node, symbol):
        children = []
        for child in node.body:
            children += self.visit(child, SymbolKind.Field)
        return [_make_symbol(node, node.name, symbol, children)]

    def visit_FunctionDef(self, node, kind=SymbolKind.Function):
        children = []
        children += self.visit(node.args)
        for child in node.body:
            children += self.visit(child)
        name = node.name
        return [_make_symbol(node, name, kind, children)]

    def visit_InterfaceDef(self, node):
        children = []
        for child in node.body:
            children += self.visit(child, SymbolKind.Method)
        return [_make_symbol(node, node.name, SymbolKind.Interface, children)]

    def visit_arguments(self, node):
        args = []
        for arg in node.args:
            args += self.visit(arg)
        return args

    def visit_arg(self, node):
        return [_make_symbol(node, node.arg, SymbolKind.Variable)]

    def visit_AnnAssign(self, node, kind=None):
        if not kind:
            # Old vyper version would have variable declaration as AnnAssign
            if isinstance(node.parent, nodes.Module):
                return [_make_symbol(node, node.target.id, SymbolKind.Variable)]
        # assert kind in (SymbolKind.Field,) removed because of default args most likely.
        if isinstance(node.parent, (nodes.EventDef, nodes.StructDef)):
            return [_make_symbol(node, node.target.id, SymbolKind.Field)]
        return []

    def visit_For(self, node):
        symbols = []
        for child in node.body:
            symbols += self.visit(child)
        symbols += self.visit(node.target)  # AnnAssign
        return symbols

    def visit_If(self, node):
        symbols = []
        for child in node.body:
            symbols += self.visit(child)
        for child in node.orelse:
            symbols += self.visit(child)
        return symbols

    def visit_Name(self, node, kind=SymbolKind.Variable):
        if isinstance(node.parent.parent, nodes.FlagDef):
            assert kind == SymbolKind.EnumMember
            return [_make_symbol(node, node.id, kind)]
        return []
