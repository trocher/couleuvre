"""
Vyper AST visitor for symbol table construction.

This module provides the visitor that walks a Vyper AST and builds
the symbol table with all definitions and their access patterns.
"""

import logging
from typing import TYPE_CHECKING, Optional

from lsprotocol.types import SymbolKind

from couleuvre.ast import nodes
from couleuvre.features.symbol_table import (
    SymbolEntry,
    build_access_patterns,
)

if TYPE_CHECKING:
    from couleuvre.parser import Module

logger = logging.getLogger("couleuvre")


class VyperAstVisitor:
    """
    Visitor that extracts namespace information from a Vyper AST.

    Walks the AST and populates a Module with:
    - Symbol table with all symbols (module-level and local)
    - Categorized sets of definitions (functions, variables, etc.)
    - Import path mappings
    """

    def __init__(self, module: "Module"):
        self.module = module
        self._current_function: Optional[nodes.FunctionDef] = None

    def visit(self, node: nodes.BaseNode) -> None:
        """Visit a node by dispatching to the appropriate visit method."""
        node_type = type(node).__name__
        visitor_fn = getattr(self, f"visit_{node_type}", None)
        if visitor_fn is None:
            logger.debug(f"No visitor for node type: {node_type}")
            return
        visitor_fn(node)

    def _add_symbol(
        self,
        name: str,
        node: nodes.BaseNode,
        kind: SymbolKind,
        scope: str = "module",
        parent_function: Optional[nodes.FunctionDef] = None,
        children: Optional[list] = None,
    ) -> SymbolEntry:
        """Helper to add a symbol to the symbol table."""
        entry = SymbolEntry(
            name=name,
            node=node,
            kind=kind,
            scope=scope,
            access_patterns=build_access_patterns(node, scope),
            parent_function=parent_function,
            children=children or [],
        )
        self.module.symbol_table.add(entry)
        return entry

    def visit_Module(self, node: nodes.Module) -> None:
        for child in node.body:
            self.visit(child)

    def visit_VariableDecl(self, node: nodes.VariableDecl) -> None:
        self.module.variables.add(node)
        kind = (
            SymbolKind.Constant
            if (node.is_constant or node.is_immutable)
            else SymbolKind.Variable
        )
        self._add_symbol(node.target.id, node, kind)

    def visit_FunctionDef(self, node: nodes.FunctionDef) -> None:
        self.module.functions.add(node)

        # Guard against missing name
        if not node.name:
            return

        # Collect children (parameters and local variables)
        children: list[SymbolEntry] = []

        # Visit function arguments
        if node.args:
            for arg in node.args.args:
                arg_entry = SymbolEntry(
                    name=arg.arg,
                    node=arg,
                    kind=SymbolKind.Variable,
                    scope=node.name,
                    access_patterns=[([arg.arg], False)],
                    parent_function=node,
                )
                self.module.symbol_table.add(arg_entry)
                children.append(arg_entry)

        # Set current function context for visiting body
        self._current_function = node

        # Visit function body to collect local variables
        for child in node.body:
            local_entries = self._visit_function_body_node(child, node)
            children.extend(local_entries)

        self._current_function = None

        # Add the function itself
        self._add_symbol(node.name, node, SymbolKind.Function, children=children)

    def _visit_function_body_node(
        self, node: nodes.BaseNode, func: nodes.FunctionDef
    ) -> list[SymbolEntry]:
        """
        Visit a node in a function body and collect local variable definitions.

        Returns list of SymbolEntry for any local variables found.
        """
        entries: list[SymbolEntry] = []

        # Guard against missing function name
        if not func.name:
            return entries

        if isinstance(node, nodes.AnnAssign):
            # Local variable declaration: x: uint256 = ...
            if hasattr(node, "target") and hasattr(node.target, "id"):
                entry = SymbolEntry(
                    name=node.target.id,
                    node=node,
                    kind=SymbolKind.Variable,
                    scope=func.name,
                    access_patterns=[([node.target.id], False)],
                    parent_function=func,
                )
                self.module.symbol_table.add(entry)
                entries.append(entry)

        elif isinstance(node, nodes.For):
            # For loop iterator: for i: uint256 in range(10)
            # The target is the loop variable (can be AnnAssign or Name)
            if isinstance(node.target, nodes.AnnAssign):
                if hasattr(node.target, "target") and hasattr(node.target.target, "id"):
                    # Use the inner Name node (node.target.target) for better location info
                    target_name = node.target.target
                    entry = SymbolEntry(
                        name=target_name.id,
                        node=target_name,
                        kind=SymbolKind.Variable,
                        scope=func.name,
                        access_patterns=[([target_name.id], False)],
                        parent_function=func,
                    )
                    self.module.symbol_table.add(entry)
                    entries.append(entry)
            elif isinstance(node.target, nodes.Name):
                entry = SymbolEntry(
                    name=node.target.id,
                    node=node.target,
                    kind=SymbolKind.Variable,
                    scope=func.name,
                    access_patterns=[([node.target.id], False)],
                    parent_function=func,
                )
                self.module.symbol_table.add(entry)
                entries.append(entry)

            # Recursively visit for loop body
            for child in node.body:
                entries.extend(self._visit_function_body_node(child, func))

        elif isinstance(node, nodes.If):
            # Recursively visit if/else bodies
            for child in node.body:
                entries.extend(self._visit_function_body_node(child, func))
            for child in node.orelse:
                entries.extend(self._visit_function_body_node(child, func))

        return entries

    def visit_FlagDef(self, node: nodes.FlagDef) -> None:
        self.module.flags.add(node)

        # Guard against missing name
        if not node.name:
            return

        children: list[SymbolEntry] = []
        for child in node.body:
            if isinstance(child, nodes.Expr) and isinstance(child.value, nodes.Name):
                member_entry = SymbolEntry(
                    name=child.value.id,
                    node=child.value,
                    kind=SymbolKind.EnumMember,
                    scope="module",
                    access_patterns=[([node.name, child.value.id], False)],
                )
                # Don't add to main symbol table, just as children
                children.append(member_entry)
        self._add_symbol(node.name, node, SymbolKind.Enum, children=children)

    def visit_EventDef(self, node: nodes.EventDef) -> None:
        self.module.events.add(node)
        if not node.name:
            return
        children = self._visit_struct_like_body(node)
        self._add_symbol(node.name, node, SymbolKind.Event, children=children)

    def visit_InterfaceDef(self, node: nodes.InterfaceDef) -> None:
        self.module.interfaces.add(node)
        if not node.name:
            return
        children: list[SymbolEntry] = []
        for child in node.body:
            if isinstance(child, nodes.FunctionDef) and child.name:
                method_entry = SymbolEntry(
                    name=child.name,
                    node=child,
                    kind=SymbolKind.Method,
                    scope="module",
                    access_patterns=[],
                )
                children.append(method_entry)
        self._add_symbol(node.name, node, SymbolKind.Interface, children=children)

    def visit_StructDef(self, node: nodes.StructDef) -> None:
        self.module.structs.add(node)
        if not node.name:
            return
        children = self._visit_struct_like_body(node)
        self._add_symbol(node.name, node, SymbolKind.Struct, children=children)

    def _visit_struct_like_body(
        self, node: nodes.EventDef | nodes.StructDef
    ) -> list[SymbolEntry]:
        """Visit body of struct-like nodes (EventDef, StructDef) to collect fields."""
        children: list[SymbolEntry] = []
        for child in node.body:
            if isinstance(child, nodes.AnnAssign) and hasattr(child, "target"):
                field_entry = SymbolEntry(
                    name=child.target.id,
                    node=child,
                    kind=SymbolKind.Field,
                    scope="module",
                    access_patterns=[],
                )
                children.append(field_entry)
        return children

    def _handle_import(self, node: nodes.BaseNode) -> None:
        if not isinstance(node, (nodes.Import, nodes.ImportFrom)):
            return
        resolved_path = (
            node.import_info.get("resolved_path") if node.import_info else None
        )
        if resolved_path is None:
            return
        if node.alias:
            self.module.imports[node.alias] = resolved_path
        if node.name:
            self.module.imports[node.name] = resolved_path

    def visit_Import(self, node: nodes.Import) -> None:
        self._handle_import(node)

    def visit_ImportFrom(self, node: nodes.ImportFrom) -> None:
        self._handle_import(node)

    def visit_ImplementsDecl(self, node: nodes.ImplementsDecl) -> None:
        pass

    def visit_UsesDecl(self, node: nodes.UsesDecl) -> None:
        pass

    def visit_InitializesDecl(self, node: nodes.InitializesDecl) -> None:
        pass

    def visit_ExportsDecl(self, node: nodes.ExportsDecl) -> None:
        pass

    # For backwards compatibility with older Vyper versions
    def visit_AnnAssign(self, node: nodes.AnnAssign) -> None:
        if isinstance(node.parent, nodes.Module):
            # Module-level AnnAssign (state variable in older Vyper)
            if node.annotation is not None and isinstance(node.annotation, nodes.Call):
                if (
                    node.annotation.func.id == "constant"
                    or node.annotation.func.id == "immutable"
                ):
                    self._add_symbol(node.target.id, node, SymbolKind.Constant)
                    return
            self._add_symbol(node.target.id, node, SymbolKind.Variable)
