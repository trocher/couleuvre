"""LSP feature implementations for Vyper."""

from couleuvre.features.completion import get_completions
from couleuvre.features.definition import get_definition_location
from couleuvre.features.diagnostics import (
    compile_and_get_diagnostics,
    create_diagnostic,
    parse_error_location,
)
from couleuvre.features.references import get_all_references
from couleuvre.features.symbols import get_document_symbols

__all__ = [
    "compile_and_get_diagnostics",
    "create_diagnostic",
    "get_all_references",
    "get_completions",
    "get_definition_location",
    "get_document_symbols",
    "parse_error_location",
]
