"""
Vyper module parsing and namespace extraction.

This module handles parsing Vyper source files into AST representations
and building namespace information for symbol resolution.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional, Set

from couleuvre.ast import nodes
from couleuvre.ast.parser import get_json_ast

logger = logging.getLogger("couleuvre")

# Regex pattern to extract Vyper version from pragma or @version annotation
_VERSION_PATTERN = re.compile(
    r"#\s*(?:@version|pragma\s+version)\s*(?:[<>=!~^]*)\s*(\d+\.\d+\.\d+)"
)


def parse_module(
    path: str,
    default_version: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> "Module":
    """
    Parse a Vyper source file into a Module with namespace information.

    Args:
        path: Path to the Vyper source file.
        default_version: Fallback Vyper version if not specified in file.
        workspace_path: Root path for resolving relative imports.

    Returns:
        A Module object with parsed AST and namespace.

    Raises:
        ValueError: If no version found and no default provided.
    """
    content = Path(path).read_text()
    match = _VERSION_PATTERN.search(content)
    if match:
        version = match.group(1)
    elif default_version is not None:
        version = default_version
    else:
        raise ValueError(f"Version not found in {path} and no default provided")

    vyper_module = get_json_ast(path, version, workspace_path=workspace_path)
    visitor = VyperAstVisitor(vyper_module, version)
    visitor.visit(vyper_module)
    return visitor.module


class Module:
    """
    Represents a parsed Vyper module with its AST and namespace.

    Attributes:
        version: The Vyper version used to parse this module.
        ast: The root AST node (Module node).
        namespace: Hierarchical namespace mapping names to AST nodes.
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
        self.namespace: Dict[str, Any] = {"self": {}}

        self.flags: Set[nodes.BaseNode] = set()
        self.functions: Set[nodes.BaseNode] = set()
        self.events: Set[nodes.BaseNode] = set()
        self.interfaces: Set[nodes.BaseNode] = set()
        self.structs: Set[nodes.BaseNode] = set()
        self.variables: Set[nodes.BaseNode] = set()
        self.imports: Dict[str, str] = {}

    def external_namespace(self) -> Dict[str, Any]:
        """
        Get the namespace visible to external modules importing this one.

        Returns a flattened namespace that includes both module-level
        names and self-prefixed names (without the self prefix).
        """
        return {
            k: v for k, v in self.namespace.items() if k != "self"
        } | self.namespace["self"]


class VyperAstVisitor:
    """
    Visitor that extracts namespace information from a Vyper AST.

    Walks the AST and populates a Module with:
    - Namespace mappings for symbol resolution
    - Categorized sets of definitions (functions, variables, etc.)
    - Import path mappings
    """

    def __init__(self, node: nodes.Module, vyper_version: str):
        self.module: Module = Module(node, vyper_version)

    def visit(self, node: nodes.BaseNode) -> None:
        """Visit a node by dispatching to the appropriate visit method."""
        node_type = type(node).__name__
        visitor_fn = getattr(self, f"visit_{node_type}", None)
        if visitor_fn is None:
            logger.debug(f"No visitor for node type: {node_type}")
            return
        visitor_fn(node)

    def visit_Module(self, node: nodes.Module) -> None:
        for child in node.body:
            self.visit(child)

    def visit_VariableDecl(self, node):
        self.module.variables.add(node)
        if node.is_constant or node.is_immutable:
            self.module.namespace[node.target.id] = node
        else:
            self.module.namespace["self"][node.target.id] = node

    def visit_FunctionDef(self, node):
        self.module.functions.add(node)
        self.module.namespace["self"][node.name] = node

    def visit_FlagDef(self, node):
        self.module.flags.add(node)
        self.module.namespace[node.name] = node

    def visit_EventDef(self, node):
        self.module.events.add(node)
        self.module.namespace[node.name] = node

    def visit_InterfaceDef(self, node):
        self.module.interfaces.add(node)
        self.module.namespace[node.name] = node

    def visit_StructDef(self, node):
        self.module.structs.add(node)
        self.module.namespace[node.name] = node

    def _handle_import(self, node):
        resolved_path = (
            node.import_info.get("resolved_path") if node.import_info else None
        )
        if resolved_path is None:
            return
        if node.alias:
            self.module.imports[node.alias] = resolved_path
        self.module.imports[node.name] = resolved_path

    def visit_Import(self, node):
        self._handle_import(node)

    def visit_ImportFrom(self, node):
        self._handle_import(node)

    def visit_ImplementsDecl(self, node):
        pass

    def visit_UsesDecl(self, node):
        pass

    def visit_InitializesDecl(self, node):
        pass

    def visit_ExportsDecl(self, node):
        pass

    # For backwards compatibility with older Vyper versions
    def visit_AnnAssign(self, node):
        if isinstance(node.parent, nodes.Module):
            if node.annotation is not None and isinstance(node.annotation, nodes.Call):
                if (
                    node.annotation.func.id == "constant"
                    or node.annotation.func.id == "immutable"
                ):
                    self.module.namespace[node.target.id] = node
                    return
            self.module.namespace["self"][node.target.id] = node
