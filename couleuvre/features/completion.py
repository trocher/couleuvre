"""
Completion support for the Vyper Language Server.

This module provides autocompletion suggestions for:
- `self.` - state variables (non-constant, non-immutable) and internal functions
- `<module>.` - symbols from imported modules
"""

import logging
import re
from typing import List, Optional

from lsprotocol import types
from lsprotocol.types import CompletionItemKind
from pygls import uris
from pygls.workspace import TextDocument

from couleuvre.ast import nodes
from couleuvre.parser import Module

logger = logging.getLogger("couleuvre")

# Pattern to match trigger context: "self." or "<identifier>."
_TRIGGER_PATTERN = re.compile(r"([A-Za-z_][A-Za-z_0-9]*)\.$")


def _get_trigger_context(doc: TextDocument, position: types.Position) -> Optional[str]:
    """
    Get the identifier before the dot that triggered completion.

    Args:
        doc: The text document.
        position: The cursor position.

    Returns:
        The identifier (e.g., "self", "MyModule"), or None if no trigger.
    """
    try:
        line = doc.lines[position.line]
    except IndexError:
        return None

    # Get text up to the cursor
    text_before_cursor = line[: position.character]

    # Match pattern like "self." or "identifier."
    match = _TRIGGER_PATTERN.search(text_before_cursor)
    if match:
        return match.group(1)
    return None


def _symbol_kind_to_completion_kind(
    kind: types.SymbolKind,
) -> types.CompletionItemKind:
    """Convert LSP SymbolKind to CompletionItemKind."""
    mapping = {
        types.SymbolKind.Function: CompletionItemKind.Function,
        types.SymbolKind.Method: CompletionItemKind.Method,
        types.SymbolKind.Variable: CompletionItemKind.Variable,
        types.SymbolKind.Constant: CompletionItemKind.Constant,
        types.SymbolKind.Field: CompletionItemKind.Field,
        types.SymbolKind.Struct: CompletionItemKind.Struct,
        types.SymbolKind.Enum: CompletionItemKind.Enum,
        types.SymbolKind.EnumMember: CompletionItemKind.EnumMember,
        types.SymbolKind.Interface: CompletionItemKind.Interface,
        types.SymbolKind.Event: CompletionItemKind.Event,
    }
    return mapping.get(kind, CompletionItemKind.Text)


def _is_internal_function(func: nodes.FunctionDef) -> bool:
    """Check if a function is internal (not external/public)."""
    for decorator in func.decorator_list:
        if isinstance(decorator, nodes.Name):
            if decorator.id in ("external", "public"):
                return False
        elif isinstance(decorator, nodes.Call):
            if isinstance(decorator.func, nodes.Name):
                if decorator.func.id in ("external", "public"):
                    return False
    return True


def _get_function_signature(func: nodes.FunctionDef) -> str:
    """Get a function signature for display."""
    args_str = ""
    if func.args and func.args.args:
        arg_parts = []
        for arg in func.args.args:
            arg_name = arg.arg
            if arg.annotation:
                # Try to get a simple type name
                if isinstance(arg.annotation, nodes.Name):
                    arg_parts.append(f"{arg_name}: {arg.annotation.id}")
                else:
                    arg_parts.append(arg_name)
            else:
                arg_parts.append(arg_name)
        args_str = ", ".join(arg_parts)

    return_str = ""
    if func.returns:
        if isinstance(func.returns, nodes.Name):
            return_str = f" -> {func.returns.id}"

    return f"({args_str}){return_str}"


def _get_variable_type(var: nodes.VariableDecl) -> Optional[str]:
    """Get the type annotation for a variable."""
    if var.annotation:
        if isinstance(var.annotation, nodes.Name):
            return var.annotation.id
        elif isinstance(var.annotation, nodes.Subscript):
            # Handle types like DynArray[uint256, 10]
            if isinstance(var.annotation.value, nodes.Name):
                return var.annotation.value.id
    return None


def get_self_completions(module: Module) -> List[types.CompletionItem]:
    """
    Get completions for `self.` - state variables and internal functions.

    Args:
        module: The current module.

    Returns:
        List of CompletionItem objects.
    """
    completions: List[types.CompletionItem] = []

    # Add state variables (non-constant, non-immutable)
    for var_node in module.variables:
        if isinstance(var_node, nodes.VariableDecl):
            # Skip constants and immutables
            if var_node.is_constant or var_node.is_immutable:
                continue

            name = var_node.target.id if var_node.target else None
            if not name:
                continue

            var_type = _get_variable_type(var_node)
            detail = var_type if var_type else "state variable"

            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Variable,
                    detail=detail,
                    documentation=f"State variable: {name}",
                )
            )

    # Add internal functions
    for func_node in module.functions:
        if isinstance(func_node, nodes.FunctionDef):
            # Only include internal functions
            if not _is_internal_function(func_node):
                continue

            name = func_node.name
            if not name or name.startswith("__"):
                # Skip dunder methods like __init__
                continue

            signature = _get_function_signature(func_node)

            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Function,
                    detail=signature,
                    documentation=f"Internal function: {name}{signature}",
                    insert_text=f"{name}($0)",
                    insert_text_format=types.InsertTextFormat.Snippet,
                )
            )

    return completions


def get_module_completions(
    get_module_func,
    workspace,
    current_module: Module,
    import_name: str,
) -> List[types.CompletionItem]:
    """
    Get completions for an imported module.

    Args:
        get_module_func: Function to get a module for a document.
        workspace: The LSP workspace.
        current_module: The current module.
        import_name: The name of the import (e.g., "MyInterface").

    Returns:
        List of CompletionItem objects.
    """
    completions: List[types.CompletionItem] = []

    # Check if this is a known import
    if import_name not in current_module.imports:
        return completions

    resolved_path = current_module.imports[import_name]
    resolved_uri = uris.from_fs_path(resolved_path)
    if not resolved_uri:
        return completions

    try:
        resolved_doc = workspace.get_text_document(resolved_uri)
    except Exception:
        return completions

    resolved_module = get_module_func(resolved_doc)
    if resolved_module is None:
        return completions

    # Get the external namespace from the imported module
    external_ns = resolved_module.external_namespace()

    for name, node in external_ns.items():
        if not isinstance(node, nodes.BaseNode):
            continue

        # Determine the kind and detail based on node type
        if isinstance(node, nodes.FunctionDef):
            signature = _get_function_signature(node)
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Function,
                    detail=signature,
                    documentation=f"Function: {name}{signature}",
                    insert_text=f"{name}($0)",
                    insert_text_format=types.InsertTextFormat.Snippet,
                )
            )
        elif isinstance(node, nodes.VariableDecl):
            var_type = _get_variable_type(node)
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Variable,
                    detail=var_type or "variable",
                )
            )
        elif isinstance(node, nodes.StructDef):
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Struct,
                    detail="struct",
                )
            )
        elif isinstance(node, nodes.InterfaceDef):
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Interface,
                    detail="interface",
                )
            )
        elif isinstance(node, nodes.EventDef):
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Event,
                    detail="event",
                )
            )
        elif isinstance(node, nodes.FlagDef):
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Enum,
                    detail="flag",
                )
            )
        else:
            # Generic symbol
            completions.append(
                types.CompletionItem(
                    label=name,
                    kind=CompletionItemKind.Text,
                )
            )

    return completions


def get_completions(
    get_module_func,
    workspace,
    doc: TextDocument,
    module: Module,
    position: types.Position,
) -> List[types.CompletionItem]:
    """
    Get completion items for the given position.

    Args:
        get_module_func: Function to get a module for a document.
        workspace: The LSP workspace.
        doc: The current document.
        module: The current module.
        position: The cursor position.

    Returns:
        List of CompletionItem objects.
    """
    trigger = _get_trigger_context(doc, position)
    if not trigger:
        return []

    if trigger == "self":
        return get_self_completions(module)
    else:
        # Try to resolve as an imported module
        return get_module_completions(get_module_func, workspace, module, trigger)
