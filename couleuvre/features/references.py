"""
Reference finding functionality for the Vyper Language Server.

This module provides tools to find all references to a symbol across modules,
supporting both local references (within the same file) and cross-module
references (via imports).
"""

import logging
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple

from lsprotocol import types

from couleuvre.ast import nodes
from couleuvre.ast.nodes import BaseNode
from couleuvre.features.symbol_table import ReferencePattern
from couleuvre.parser import Module
from couleuvre.utils import range_from_node

logger = logging.getLogger("couleuvre")


# -----------------------------------------------------------------------------
# Pattern Building
# -----------------------------------------------------------------------------


def _is_constant_annotation(node: nodes.AnnAssign) -> bool:
    """Check if an AnnAssign node represents a constant or immutable declaration."""
    if not isinstance(node.annotation, nodes.Call):
        return False
    func = node.annotation.func
    return isinstance(func, nodes.Name) and func.id in ("constant", "immutable")


def _get_identifier(node: BaseNode) -> Optional[str]:
    """Extract the identifier name from a node, if present."""
    # For variable declarations, the name is in target.id
    target = getattr(node, "target", None)
    if target is not None:
        return getattr(target, "id", None)
    # For other definitions (functions, structs, etc.), it's in name
    return getattr(node, "name", None)


def build_reference_patterns(node: BaseNode) -> List[ReferencePattern]:
    """
    Build patterns that match references to the given definition node.

    Different node types have different reference patterns:
    - State variables: accessed via self.name
    - Constants/immutables: accessed directly by name
    - Functions: called via self.name()
    - Flags: accessed directly, with prefix matching for members (Flag.MEMBER)
    - Events/Structs/Interfaces: accessed directly by name

    Returns:
        List of (chain, allow_prefix_match) tuples.
    """
    identifier = _get_identifier(node)
    if not identifier:
        return []

    # State variables (VariableDecl in newer Vyper)
    if isinstance(node, nodes.VariableDecl):
        if node.is_constant or node.is_immutable:
            return [([identifier], False)]
        return [(["self", identifier], False)]

    # State variables (AnnAssign in older Vyper)
    if isinstance(node, nodes.AnnAssign):
        if _is_constant_annotation(node):
            return [([identifier], False)]
        if isinstance(node.parent, nodes.Module):
            return [(["self", identifier], False)]
        return [([identifier], False)]

    # Functions are always accessed via self
    if isinstance(node, nodes.FunctionDef):
        return [(["self", identifier], False)]

    # Flags allow prefix matching for member access (e.g., Status.ACTIVE)
    if isinstance(node, nodes.FlagDef):
        return [([identifier], True)]

    # Events, Structs, and Interfaces are accessed directly by name
    if isinstance(node, (nodes.EventDef, nodes.StructDef, nodes.InterfaceDef)):
        return [([identifier], False)]

    # Fallback for other named nodes
    return [([identifier], False)]


def prefix_patterns(
    patterns: List[ReferencePattern], alias: str
) -> List[ReferencePattern]:
    """
    Create new patterns prefixed with an import alias.

    When searching for references in a module that imports another module,
    references use the import alias instead of 'self'. For example, if module A
    imports module B as 'token', then B's function 'transfer' is referenced as
    'token.transfer' rather than 'self.transfer'.

    Args:
        patterns: Original reference patterns from the definition module.
        alias: The import alias used in the importing module.

    Returns:
        New patterns with the alias prefix, with 'self' stripped if present.
    """
    prefixed: List[ReferencePattern] = []
    for chain, allow_prefix in patterns:
        # Strip leading 'self' since imports don't use self
        stripped = chain[1:] if chain and chain[0] == "self" else chain
        prefixed.append(([alias] + stripped, allow_prefix))
    return prefixed


# -----------------------------------------------------------------------------
# Chain Extraction and Matching
# -----------------------------------------------------------------------------


def _extract_chain(node: BaseNode) -> Optional[List[str]]:
    """
    Extract the identifier chain from an AST node.

    For attribute access like 'self.foo.bar', returns ['self', 'foo', 'bar'].
    For simple names like 'MAX', returns ['MAX'].

    Returns None if the node doesn't represent an identifier chain.
    """
    if isinstance(node, nodes.Attribute):
        # Build chain by traversing from leaf to root, then reverse
        chain: List[str] = [node.attr]
        value = node.value
        while isinstance(value, nodes.Attribute):
            chain.append(value.attr)
            value = value.value
        if isinstance(value, nodes.Name):
            chain.append(value.id)
            chain.reverse()
            return chain
        return None

    if isinstance(node, nodes.Name):
        return [node.id]

    return None


def _is_declaration_node(candidate: BaseNode, definition: BaseNode) -> bool:
    """Check if the candidate node is the declaration of the definition."""
    if candidate is definition:
        return True
    # For variable declarations, also check the target Name node
    if isinstance(definition, (nodes.VariableDecl, nodes.AnnAssign)):
        return candidate is getattr(definition, "target", None)
    return False


def _is_inside_declaration_context(node: BaseNode) -> bool:
    """
    Check if the node is inside a declaration context where names are definitions,
    not references (e.g., flag members, event fields, struct fields).
    """
    parent = node.parent
    while parent is not None:
        if isinstance(parent, (nodes.FlagDef, nodes.EventDef, nodes.StructDef)):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _matches_pattern(chain: Sequence[str], patterns: List[ReferencePattern]) -> bool:
    """Check if an identifier chain matches any of the reference patterns."""
    for expected, allow_prefix in patterns:
        # Exact match
        if list(chain) == expected:
            return True
        # Prefix match (for flags: Status matches Status.ACTIVE)
        if allow_prefix and len(chain) >= len(expected):
            if list(chain[: len(expected)]) == expected:
                return True
    return False


# -----------------------------------------------------------------------------
# AST Walking
# -----------------------------------------------------------------------------


def _walk_ast(node: BaseNode):
    """
    Iterate over all nodes in an AST tree (depth-first).

    Skips 'parent' fields to avoid infinite loops.
    """
    stack = [node]
    while stack:
        current = stack.pop()
        yield current
        # Iterate over dataclass fields
        for field_name in current.__dataclass_fields__:  # type: ignore[attr-defined]
            if field_name == "parent":
                continue
            value = getattr(current, field_name, None)
            if isinstance(value, BaseNode):
                stack.append(value)
            elif isinstance(value, list):
                # Reverse to maintain order when popping from stack
                for item in reversed(value):
                    if isinstance(item, BaseNode):
                        stack.append(item)


# -----------------------------------------------------------------------------
# Reference Finding
# -----------------------------------------------------------------------------


def find_references(
    module: Module,
    uri: str,
    patterns: List[ReferencePattern],
    include_declaration: bool,
    definition_node: Optional[BaseNode] = None,
) -> List[types.Location]:
    """
    Find all references matching the given patterns in a module.

    Args:
        module: The module to search in.
        uri: The URI of the module (for Location results).
        patterns: Reference patterns to match against.
        include_declaration: Whether to include the definition itself.
        definition_node: The definition node (to optionally include/exclude it).

    Returns:
        List of Location objects for each reference found.
    """
    if not patterns:
        return []

    locations: List[types.Location] = []
    # Track seen locations to avoid duplicates (e.g., Name inside Attribute)
    seen: Set[Tuple[int, int, int, int]] = set()

    def _add_location(node: BaseNode) -> None:
        """Add a location if not already seen."""
        loc = types.Location(uri=uri, range=range_from_node(node))
        key = (
            loc.range.start.line,
            loc.range.start.character,
            loc.range.end.line,
            loc.range.end.character,
        )
        if key not in seen:
            seen.add(key)
            locations.append(loc)

    # Optionally include the declaration itself
    if include_declaration and definition_node is not None:
        _add_location(definition_node)

    # Walk the AST and find matching references
    for node in _walk_ast(module.ast):
        chain = _extract_chain(node)
        if chain is None:
            continue
        # Skip the declaration node itself (we handled it above if needed)
        if definition_node and _is_declaration_node(node, definition_node):
            continue
        # Skip names inside declaration contexts (flag members, event fields, etc.)
        if _is_inside_declaration_context(node):
            continue
        if _matches_pattern(chain, patterns):
            _add_location(node)

    return locations


# -----------------------------------------------------------------------------
# Path Utilities
# -----------------------------------------------------------------------------


def normalize_path(path: Optional[str]) -> Optional[str]:
    """Normalize a file path to an absolute, resolved path for comparison."""
    if path is None:
        return None
    try:
        return str(Path(path).resolve())
    except Exception:
        logger.debug("Unable to normalize path %s", path)
        return path


def _module_path(module: Module, uri: str) -> Optional[str]:
    """
    Get the resolved file path for a module.

    Prefers the URI-based path over ast.resolved_path because resolved_path
    may point to a temp file when parsing unsaved buffers.
    """
    from pygls import uris as pygls_uris

    # Prefer URI path - resolved_path may be a temp file for unsaved buffers
    path = pygls_uris.to_fs_path(uri)
    if path is None:
        path = module.ast.resolved_path
    if path is None:
        return None
    try:
        return str(Path(path).resolve())
    except Exception:
        return path


def _get_search_terms(patterns: List[ReferencePattern]) -> List[str]:
    """
    Extract search terms from reference patterns for text-based pre-filtering.

    Returns the last element of each pattern chain (the symbol name itself).
    """
    terms: List[str] = []
    for chain, _ in patterns:
        if chain:
            # The symbol name is typically the last element (e.g., "func" in ["self", "func"])
            terms.append(chain[-1])
    return list(set(terms))  # deduplicate


def _find_files_with_pattern(
    workspace_root: str, search_terms: List[str], exclude_paths: Set[str]
) -> List[Path]:
    """
    Find Vyper files in workspace that contain any of the search terms.

    Uses fast text search to pre-filter files before expensive AST parsing.

    Args:
        workspace_root: Root path of the workspace.
        search_terms: Terms to search for in file contents.
        exclude_paths: Normalized paths to skip (already searched).

    Returns:
        List of file paths that contain at least one search term.
    """
    if not workspace_root or not isinstance(workspace_root, str):
        return []

    root = Path(workspace_root)
    if not root.exists():
        return []

    matching_files: List[Path] = []
    try:
        for pattern in ("**/*.vy", "**/*.vyi"):
            for file_path in root.glob(pattern):
                # Skip files we've already searched
                normalized = normalize_path(str(file_path))
                if normalized in exclude_paths:
                    continue

                # Quick text search - read file and check for terms
                try:
                    content = file_path.read_text()
                    if any(term in content for term in search_terms):
                        matching_files.append(file_path)
                except Exception:
                    continue
    except Exception as e:
        logger.debug("Error scanning workspace for Vyper files: %s", e)

    return matching_files


def get_all_references(
    get_module_func,
    workspace,
    doc,
    module: Module,
    position,
    modules_dict: dict,
    include_declaration: bool = False,
    workspace_root: Optional[str] = None,
) -> List[types.Location]:
    """
    Get all references to the symbol at the given position.

    Args:
        get_module_func: Function to get a module for a document.
        workspace: The LSP workspace.
        doc: The current document.
        module: The current module.
        position: The cursor position.
        modules_dict: Dictionary of all loaded modules (uri -> Module).
        include_declaration: Whether to include the definition itself.
        workspace_root: Root path of the workspace (for scanning additional files).

    Returns:
        List of Location objects for each reference found.
    """
    from couleuvre.utils import get_attribute_word
    from couleuvre.features.resolve import resolve_symbol_for_word

    attribute_word = get_attribute_word(doc, position)
    if not attribute_word:
        return []

    resolved = resolve_symbol_for_word(
        get_module_func, workspace, doc, module, attribute_word, position
    )
    if not resolved or resolved.node is None:
        return []

    # Check if this is a local variable (use symbol table entry if available)
    is_local = False
    enclosing_function = None
    if resolved.entry is not None and resolved.entry.is_local():
        is_local = True
        enclosing_function = resolved.entry.parent_function

    # Get patterns from symbol table entry or build from node
    if resolved.entry is not None:
        patterns = resolved.entry.access_patterns
    else:
        patterns = build_reference_patterns(resolved.node)

    if not patterns:
        return []

    # For local variables, only search within the containing function
    if is_local and enclosing_function is not None:
        return find_local_references(
            module,
            doc.uri,
            patterns,
            enclosing_function,
            include_declaration,
            resolved.node,
        )

    # For module-level symbols, search across all modules
    target_path = normalize_path(_module_path(resolved.module, resolved.uri))
    modules = dict(modules_dict)
    modules.setdefault(doc.uri, module)
    modules.setdefault(resolved.uri, resolved.module)

    locations = []
    searched_paths: Set[str] = set()

    for uri, mod in modules.items():
        module_path = normalize_path(_module_path(mod, uri))
        if not module_path:
            continue
        searched_paths.add(module_path)
        search_patterns = []
        definition_node: Optional[BaseNode] = None

        if target_path is not None and module_path == target_path:
            search_patterns = patterns
            definition_node = resolved.node
        elif target_path is not None:
            aliases = [
                alias
                for alias, path in mod.imports.items()
                if normalize_path(path) == target_path
            ]
            for alias in aliases:
                search_patterns.extend(prefix_patterns(patterns, alias))

        if not search_patterns:
            continue

        locations.extend(
            find_references(
                mod,
                uri,
                search_patterns,
                include_declaration,
                definition_node,
            )
        )

    # Scan workspace for additional files that might reference the symbol
    if workspace_root and target_path:
        from pygls import uris as pygls_uris

        # Get search terms for text-based pre-filtering
        search_terms = _get_search_terms(patterns)
        if search_terms:
            # Find files containing the symbol name (fast text search)
            candidate_files = _find_files_with_pattern(
                workspace_root, search_terms, searched_paths
            )

            for file_path in candidate_files:
                try:
                    file_uri = pygls_uris.from_fs_path(str(file_path))
                    if file_uri is None:
                        continue

                    # Parse the file
                    file_doc = workspace.get_text_document(file_uri)
                    file_module = get_module_func(
                        doc=file_doc, workspace_folder=workspace_root
                    )
                    if file_module is None:
                        continue

                    # Find import aliases that reference the target module
                    aliases = [
                        alias
                        for alias, path in file_module.imports.items()
                        if normalize_path(path) == target_path
                    ]
                    if not aliases:
                        continue

                    # Build prefixed patterns and search
                    search_patterns = []
                    for alias in aliases:
                        search_patterns.extend(prefix_patterns(patterns, alias))

                    if search_patterns:
                        locations.extend(
                            find_references(
                                file_module,
                                file_uri,
                                search_patterns,
                                include_declaration=False,
                                definition_node=None,
                            )
                        )
                except Exception as e:
                    logger.debug(
                        "Error scanning file %s for references: %s", file_path, e
                    )
                    continue

    return locations


def find_local_references(
    module: Module,
    uri: str,
    patterns: List[ReferencePattern],
    enclosing_function: nodes.FunctionDef,
    include_declaration: bool,
    definition_node: Optional[BaseNode] = None,
) -> List[types.Location]:
    """
    Find all references to a local variable within its containing function.

    Args:
        module: The module to search in.
        uri: The URI of the module.
        patterns: Reference patterns to match against.
        enclosing_function: The function containing the local variable.
        include_declaration: Whether to include the definition itself.
        definition_node: The definition node (to optionally include/exclude it).

    Returns:
        List of Location objects for each reference found.
    """
    if not patterns:
        return []

    locations: List[types.Location] = []
    seen: Set[Tuple[int, int, int, int]] = set()

    def _add_location(node: BaseNode) -> None:
        """Add a location if not already seen."""
        loc = types.Location(uri=uri, range=range_from_node(node))
        key = (
            loc.range.start.line,
            loc.range.start.character,
            loc.range.end.line,
            loc.range.end.character,
        )
        if key not in seen:
            seen.add(key)
            locations.append(loc)

    # Optionally include the declaration itself
    if include_declaration and definition_node is not None:
        _add_location(definition_node)

    # Walk the function's AST to find matching references
    for node in _walk_ast(enclosing_function):
        chain = _extract_chain(node)
        if chain is None:
            continue
        if definition_node and _is_declaration_node(node, definition_node):
            continue
        if _matches_pattern(chain, patterns):
            _add_location(node)

    return locations
