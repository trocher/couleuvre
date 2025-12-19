"""
Vyper module parsing.

This module handles parsing Vyper source files into AST representations.
Symbol table construction is handled by the separate visitor module.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Set

from couleuvre.ast import nodes
from couleuvre.ast.parser import get_json_ast
from couleuvre.features.symbol_table import SymbolTable

logger = logging.getLogger("couleuvre")

# Regex pattern to extract Vyper version from pragma or @version annotation
_VERSION_PATTERN = re.compile(
    r"#\s*(?:@version|pragma\s+version)\s*(?:[<>=!~^]*)\s*(\d+\.\d+\.\d+)"
)


def parse_module(
    path: str,
    default_version: Optional[str] = None,
    workspace_path: Optional[str] = None,
    source: Optional[str] = None,
) -> "Module":
    """
    Parse a Vyper source file into a Module with namespace information.

    Args:
        path: Path to the Vyper source file.
        default_version: Fallback Vyper version if not specified in file.
        workspace_path: Root path for resolving relative imports.
        source: Optional source content (for unsaved buffers). If not provided,
                reads from the file at path.

    Returns:
        A Module object with parsed AST and namespace.

    Raises:
        ValueError: If no version found and no default provided.
    """
    # Use provided source or read from disk
    content = source if source is not None else Path(path).read_text()
    match = _VERSION_PATTERN.search(content)
    if match:
        version = match.group(1)
    elif default_version is not None:
        version = default_version
    else:
        raise ValueError(f"Version not found in {path} and no default provided")

    vyper_module = get_json_ast(
        path, version, workspace_path=workspace_path, source=source
    )
    module = Module(vyper_module, version)

    # Build symbol table using the visitor
    from couleuvre.ast.visitor import VyperAstVisitor

    visitor = VyperAstVisitor(module)
    visitor.visit(vyper_module)
    return module


class Module:
    """
    Represents a parsed Vyper module with its AST and namespace.

    Attributes:
        version: The Vyper version used to parse this module.
        ast: The root AST node (Module node).
        symbol_table: The unified symbol table for this module.
        namespace: Hierarchical namespace mapping names to AST nodes (legacy, backed by symbol_table).
        flags: Set of FlagDef nodes in this module.
        functions: Set of FunctionDef nodes in this module.
        events: Set of EventDef nodes in this module.
        interfaces: Set of InterfaceDef nodes in this module.
        structs: Set of StructDef nodes in this module.
        variables: Set of VariableDecl nodes in this module.
        imports: Mapping of import aliases to resolved file paths.
    """

    def __init__(self, ast: nodes.Module, vyper_version: str):
        self.version: str = vyper_version
        self.ast: nodes.Module = ast
        self.symbol_table: SymbolTable = SymbolTable()

        self.flags: Set[nodes.BaseNode] = set()
        self.functions: Set[nodes.BaseNode] = set()
        self.events: Set[nodes.BaseNode] = set()
        self.interfaces: Set[nodes.BaseNode] = set()
        self.structs: Set[nodes.BaseNode] = set()
        self.variables: Set[nodes.BaseNode] = set()
        self.imports: Dict[str, str] = {}

    @property
    def namespace(self) -> Dict[str, Any]:
        """Legacy namespace accessor, backed by symbol_table."""
        return self.symbol_table.namespace

    def external_namespace(self) -> Dict[str, Any]:
        """
        Get the namespace visible to external modules importing this one.

        Returns a flattened namespace that includes both module-level
        names and self-prefixed names (without the self prefix).
        """
        return self.symbol_table.external_namespace()
