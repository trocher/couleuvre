import logging
from typing import List, Tuple

from lsprotocol import types
from lsprotocol.types import SymbolKind

from couleuvre.ast_parser import vyper_ast
from couleuvre.parser.parse import Module
from couleuvre.utils import range_from_node

logger = logging.getLogger("vyper-lsp")


class VyperNodeVisitorBase:
    ignored_types: Tuple = ()
    scope_name = ""

    def visit(self, node, *args):
        if isinstance(node, self.ignored_types):
            return []
        node_type = type(node).__name__
        visitor_fn = getattr(self, f"visit_{node_type}", None)
        if visitor_fn is None:
            return []
        return visitor_fn(node, *args)


def get_document_symbols(module: Module) -> List[types.DocumentSymbol]:
    visitor = SymbolVisitor()
    return visitor.visit(module.ast)


def get_symbol(node, name, kind, children=None):
    if children is None:
        children = []
    return types.DocumentSymbol(
        name=name,
        kind=kind,
        range=range_from_node(node),
        selection_range=range_from_node(node),
        children=children,
    )


class SymbolVisitor(VyperNodeVisitorBase):
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
        return [get_symbol(node, name, kind, [])]

    def visit_FlagDef(self, node):
        children = []
        for child in node.body:
            assert isinstance(child, vyper_ast.Expr)
            children += self.visit(child.value, SymbolKind.EnumMember)
        return [get_symbol(node, node.name, SymbolKind.Enum, children)]

    def visit_EventDef(self, node):
        return self._visit_struct_like(node, SymbolKind.Event)

    def visit_StructDef(self, node):
        return self._visit_struct_like(node, SymbolKind.Struct)

    def _visit_struct_like(self, node, symbol):
        children = []
        for child in node.body:
            children += self.visit(child, SymbolKind.Field)
        return [get_symbol(node, node.name, symbol, children)]

    def visit_FunctionDef(self, node, kind=SymbolKind.Function):
        children = []
        children += self.visit(node.args)
        for child in node.body:
            children += self.visit(child)
        name = node.name
        return [get_symbol(node, name, kind, children)]

    def visit_InterfaceDef(self, node):
        children = []
        for child in node.body:
            children += self.visit(child, SymbolKind.Method)
        return [get_symbol(node, node.name, SymbolKind.Interface, children)]

    def visit_arguments(self, node):
        args = []
        for arg in node.args:
            args += self.visit(arg)
        return args

    def visit_arg(self, node):
        return [get_symbol(node, node.arg, SymbolKind.Variable)]

    def visit_AnnAssign(self, node, kind=None):
        if not kind:
            # Old vyper version would have variable declaration as AnnAssign
            if isinstance(node.parent, vyper_ast.Module):
                return [get_symbol(node, node.target.id, SymbolKind.Variable)]
        # assert kind in (SymbolKind.Field,) removed because of default args most likely.
        if isinstance(node.parent, (vyper_ast.EventDef, vyper_ast.StructDef)):
            return [get_symbol(node, node.target.id, SymbolKind.Field)]
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
        if isinstance(node.parent.parent, vyper_ast.FlagDef):
            assert kind == SymbolKind.EnumMember
            return [get_symbol(node, node.id, kind)]
        return []
