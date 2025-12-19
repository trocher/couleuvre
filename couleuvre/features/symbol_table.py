"""
Unified symbol table for the Vyper Language Server.

This module provides a centralized symbol table that stores all symbols
with rich metadata, used by definition, references, and document symbols features.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from lsprotocol import types
from lsprotocol.types import SymbolKind

from couleuvre.ast import nodes
from couleuvre.ast.nodes import BaseNode
from couleuvre.utils import range_from_node


# A reference pattern is a tuple of:
# - chain: List[str] - the identifier chain to match (e.g., ["self", "foo"])
# - allow_prefix_match: bool - if True, matches chains that start with this pattern
ReferencePattern = Tuple[List[str], bool]


@dataclass
class SymbolEntry:
    """
    Represents a symbol in the symbol table.

    Attributes:
        name: The symbol's identifier name.
        node: The AST node where the symbol is defined.
        kind: The LSP SymbolKind (Variable, Function, Constant, etc.).
        scope: The scope name ("module" for module-level, or function name for locals).
        access_patterns: How the symbol is accessed (e.g., [["self", "foo"]] or [["MAX"]]).
        parent_function: The containing FunctionDef node for local variables.
        children: Child symbols (e.g., function parameters, struct fields).
    """

    name: str
    node: BaseNode
    kind: SymbolKind
    scope: str = "module"
    access_patterns: List[ReferencePattern] = field(default_factory=list)
    parent_function: Optional[nodes.FunctionDef] = None
    children: List["SymbolEntry"] = field(default_factory=list)

    def is_local(self) -> bool:
        """Check if this symbol is a local variable (not module-level)."""
        return self.scope != "module"

    def to_document_symbol(self) -> types.DocumentSymbol:
        """Convert this entry to an LSP DocumentSymbol."""
        children_symbols = [child.to_document_symbol() for child in self.children]
        return types.DocumentSymbol(
            name=self.name,
            kind=self.kind,
            range=range_from_node(self.node),
            selection_range=range_from_node(self.node),
            children=children_symbols,
        )


class SymbolTable:
    """
    Centralized symbol table for a Vyper module.

    Provides methods for:
    - Symbol resolution (for go-to-definition)
    - Reference pattern generation (for find-references)
    - Document symbol generation (for outline view)
    """

    def __init__(self):
        self.entries: List[SymbolEntry] = []
        self._by_name: Dict[str, List[SymbolEntry]] = {}
        self._by_scope: Dict[str, List[SymbolEntry]] = {}
        self._module_namespace: Dict[str, Any] = {"self": {}}

    def add(self, entry: SymbolEntry) -> None:
        """Add a symbol entry to the table."""
        self.entries.append(entry)

        # Index by name
        if entry.name not in self._by_name:
            self._by_name[entry.name] = []
        self._by_name[entry.name].append(entry)

        # Index by scope
        if entry.scope not in self._by_scope:
            self._by_scope[entry.scope] = []
        self._by_scope[entry.scope].append(entry)

        # Also populate legacy namespace for module-level symbols
        if entry.scope == "module":
            self._add_to_namespace(entry)

    def _add_to_namespace(self, entry: SymbolEntry) -> None:
        """Add a module-level symbol to the legacy namespace structure."""
        for pattern, _ in entry.access_patterns:
            if len(pattern) == 1:
                # Direct access (constants, flags, etc.)
                self._module_namespace[pattern[0]] = entry.node
            elif len(pattern) == 2 and pattern[0] == "self":
                # self.x access (state variables, functions)
                self._module_namespace["self"][pattern[1]] = entry.node

    @property
    def namespace(self) -> Dict[str, Any]:
        """Get the legacy namespace dict for backwards compatibility."""
        return self._module_namespace

    def get_by_name(self, name: str) -> List[SymbolEntry]:
        """Get all symbols with the given name."""
        return self._by_name.get(name, [])

    def get_by_scope(self, scope: str) -> List[SymbolEntry]:
        """Get all symbols in the given scope."""
        return self._by_scope.get(scope, [])

    def get_module_symbols(self) -> List[SymbolEntry]:
        """Get all module-level symbols."""
        return self.get_by_scope("module")

    def get_local_symbols(self, function_name: str) -> List[SymbolEntry]:
        """Get all local symbols for a function."""
        return self.get_by_scope(function_name)

    def resolve(
        self,
        chain: List[str],
        position: Optional[types.Position] = None,
        enclosing_function: Optional[nodes.FunctionDef] = None,
    ) -> Optional[SymbolEntry]:
        """
        Resolve an identifier chain to a symbol entry.

        Args:
            chain: The identifier chain (e.g., ['self', 'foo'] or ['x']).
            position: The cursor position (used for scope determination).
            enclosing_function: The function containing the cursor position.

        Returns:
            The resolved SymbolEntry, or None if not found.
        """
        if not chain:
            return None

        # For single-name references, check local scope first
        if len(chain) == 1 and enclosing_function is not None:
            name = chain[0]
            if enclosing_function.name:
                local_entry = self._resolve_local(name, enclosing_function.name)
                if local_entry is not None:
                    return local_entry

        # Try to resolve in module namespace
        return self._resolve_module(chain)

    def _resolve_local(self, name: str, function_name: str) -> Optional[SymbolEntry]:
        """Resolve a name in a function's local scope."""
        for entry in self.get_by_scope(function_name):
            if entry.name == name:
                return entry
        return None

    def _resolve_module(self, chain: List[str]) -> Optional[SymbolEntry]:
        """Resolve an identifier chain in module scope."""
        # Try exact match first
        for entry in self.get_module_symbols():
            for pattern, allow_prefix in entry.access_patterns:
                if list(chain) == pattern:
                    return entry

        # Try with self fallback for single names
        if len(chain) == 1:
            self_chain = ["self"] + chain
            for entry in self.get_module_symbols():
                for pattern, allow_prefix in entry.access_patterns:
                    if list(self_chain) == pattern:
                        return entry

        return None

    def get_reference_patterns(self, entry: SymbolEntry) -> List[ReferencePattern]:
        """
        Get the reference patterns for a symbol.

        Returns:
            List of (chain, allow_prefix_match) tuples.
        """
        return entry.access_patterns

    def get_document_symbols(self) -> List[types.DocumentSymbol]:
        """
        Generate LSP DocumentSymbols for the outline view.

        Returns:
            List of top-level DocumentSymbol objects.
        """
        # Only return module-level symbols as top-level items
        # (local symbols are children of their containing function)
        return [
            entry.to_document_symbol()
            for entry in self.entries
            if entry.scope == "module"
        ]

    def external_namespace(self) -> Dict[str, Any]:
        """
        Get the namespace visible to external modules importing this one.

        Returns a flattened namespace that includes both module-level
        names and self-prefixed names (without the self prefix).
        """
        return {
            k: v for k, v in self._module_namespace.items() if k != "self"
        } | self._module_namespace.get("self", {})


# =============================================================================
# Symbol Kind Inference
# =============================================================================


def infer_symbol_kind(node: BaseNode) -> SymbolKind:
    """
    Infer the LSP SymbolKind for an AST node.

    Args:
        node: The AST node to analyze.

    Returns:
        The appropriate SymbolKind.
    """
    if isinstance(node, nodes.FunctionDef):
        return SymbolKind.Function

    if isinstance(node, nodes.VariableDecl):
        if node.is_constant or node.is_immutable:
            return SymbolKind.Constant
        return SymbolKind.Variable

    if isinstance(node, nodes.AnnAssign):
        # Check parent context
        if isinstance(node.parent, nodes.Module):
            # Module-level AnnAssign (older Vyper)
            if _is_constant_annotation(node):
                return SymbolKind.Constant
            return SymbolKind.Variable
        if isinstance(node.parent, (nodes.EventDef, nodes.StructDef)):
            return SymbolKind.Field
        # Local variable
        return SymbolKind.Variable

    if isinstance(node, nodes.arg):
        return SymbolKind.Variable

    if isinstance(node, nodes.FlagDef):
        return SymbolKind.Enum

    if isinstance(node, nodes.EventDef):
        return SymbolKind.Event

    if isinstance(node, nodes.StructDef):
        return SymbolKind.Struct

    if isinstance(node, nodes.InterfaceDef):
        return SymbolKind.Interface

    if isinstance(node, nodes.Name):
        # Flag member
        if isinstance(node.parent, nodes.Expr) and isinstance(
            node.parent.parent, nodes.FlagDef
        ):
            return SymbolKind.EnumMember

    return SymbolKind.Variable


def _is_constant_annotation(node: nodes.AnnAssign) -> bool:
    """Check if an AnnAssign node represents a constant or immutable declaration."""
    if not isinstance(node.annotation, nodes.Call):
        return False
    func = node.annotation.func
    return isinstance(func, nodes.Name) and func.id in ("constant", "immutable")


# =============================================================================
# Access Pattern Building
# =============================================================================


def build_access_patterns(
    node: BaseNode, scope: str = "module"
) -> List[ReferencePattern]:
    """
    Build access patterns for a symbol.

    Args:
        node: The AST node defining the symbol.
        scope: The scope ("module" or function name).

    Returns:
        List of (chain, allow_prefix_match) tuples.
    """
    identifier = _get_identifier(node)
    if not identifier:
        return []

    # Local variables are accessed directly by name
    if scope != "module":
        return [([identifier], False)]

    # Module-level symbols have different access patterns
    if isinstance(node, nodes.VariableDecl):
        if node.is_constant or node.is_immutable:
            return [([identifier], False)]
        return [(["self", identifier], False)]

    if isinstance(node, nodes.AnnAssign):
        if _is_constant_annotation(node):
            return [([identifier], False)]
        if isinstance(node.parent, nodes.Module):
            return [(["self", identifier], False)]
        return [([identifier], False)]

    if isinstance(node, nodes.FunctionDef):
        return [(["self", identifier], False)]

    if isinstance(node, nodes.FlagDef):
        # Flags allow prefix matching (e.g., Status.ACTIVE)
        return [([identifier], True)]

    if isinstance(node, (nodes.EventDef, nodes.StructDef, nodes.InterfaceDef)):
        return [([identifier], False)]

    # Default: direct access
    return [([identifier], False)]


def _get_identifier(node: BaseNode) -> Optional[str]:
    """Extract the identifier name from a node, if present."""
    # For variable declarations, the name is in target.id
    target = getattr(node, "target", None)
    if target is not None:
        return getattr(target, "id", None)
    # For arg nodes
    if isinstance(node, nodes.arg):
        return node.arg
    # For other definitions (functions, structs, etc.), it's in name
    return getattr(node, "name", None)
