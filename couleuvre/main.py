"""
Couleuvre - Vyper Language Server.

This module provides the main entry point for the Vyper LSP server,
implementing standard LSP features like go-to-definition, references,
and document symbols.
"""

import logging
from typing import Dict, List, Optional

from lsprotocol import types
from pygls.cli import start_server
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from couleuvre import utils
from couleuvre.features.definition import get_definition_location
from couleuvre.features.references import get_all_references
from couleuvre.features.symbols_visitor import get_document_symbols
from couleuvre.logger_setup import setup_logging
from couleuvre.parser.parse import Module, parse_module

logger = logging.getLogger("couleuvre")


class VyperLanguageServer(LanguageServer):
    """Language server implementation for Vyper smart contracts."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modules: Dict[str, Module] = {}
        self.logger = setup_logging(self)
        self.logger.info("Vyper Language Server starting...")
        installed_version = utils.get_installed_vyper_version()
        self.default_version: Optional[str] = (
            str(installed_version) if installed_version else None
        )

    def parse(self, doc: TextDocument, workspace_path: Optional[str] = None) -> None:
        """Parse a document and cache its module."""
        self.modules[doc.uri] = parse_module(
            doc.path,
            default_version=self.default_version,
            workspace_path=workspace_path,
        )
        if not self.default_version:
            self.default_version = self.modules[doc.uri].version
        self.logger.debug("Parsed module: %s", doc.uri)

    def get_module(
        self, doc: TextDocument, workspace_path: Optional[str] = None
    ) -> Module:
        """Get or parse the module for a document."""
        self.logger.debug("Getting module: %s", doc.uri)
        if doc.uri not in self.modules:
            self.modules[doc.uri] = parse_module(
                doc.path,
                default_version=self.default_version,
                workspace_path=workspace_path,
            )
            if not self.default_version:
                self.default_version = self.modules[doc.uri].version
        return self.modules[doc.uri]


server = VyperLanguageServer("couleuvre", "v0.0.1")


# -----------------------------------------------------------------------------
# Document Lifecycle Events
# -----------------------------------------------------------------------------


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: VyperLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
    """Parse each document when it is opened."""
    ls.logger.debug("Document opened: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    ls.parse(doc, workspace_path=ls.workspace.root_path)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(
    ls: VyperLanguageServer, params: types.DidChangeTextDocumentParams
) -> None:
    """Re-parse each document when it is changed."""
    ls.logger.debug("Document changed: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    ls.parse(doc, workspace_path=ls.workspace.root_path)


# -----------------------------------------------------------------------------
# Symbol Features
# -----------------------------------------------------------------------------


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(
    ls: VyperLanguageServer, params: types.DocumentSymbolParams
) -> List[types.DocumentSymbol]:
    """Return all the symbols defined in the given document."""
    ls.logger.debug("Document symbol requested: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    module = ls.get_module(doc, workspace_path=ls.workspace.root_path)
    return get_document_symbols(module)


@server.feature(types.WORKSPACE_SYMBOL)
def workspace_symbol(
    ls: VyperLanguageServer, params: types.WorkspaceSymbolParams
) -> List[types.WorkspaceSymbol]:
    """Return symbols matching the query across the workspace."""
    # TODO: Implement workspace symbol search
    return []


# -----------------------------------------------------------------------------
# Navigation Features
# -----------------------------------------------------------------------------


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def goto_definition(
    ls: VyperLanguageServer, params: types.DefinitionParams
) -> Optional[types.Location]:
    """Jump to the definition of the symbol at the cursor."""
    ls.logger.debug("Definition requested: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    module = ls.get_module(doc, workspace_path=ls.workspace.root_path)

    def get_module_func(d: TextDocument) -> Module:
        return ls.get_module(d, workspace_path=ls.workspace.root_path)

    return get_definition_location(
        get_module_func, ls.workspace, doc, module, params.position
    )


@server.feature(types.TEXT_DOCUMENT_REFERENCES)
def goto_references(
    ls: VyperLanguageServer, params: types.ReferenceParams
) -> List[types.Location]:
    """Return all references to the symbol at the cursor."""
    ls.logger.debug("References requested: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    module = ls.get_module(doc, workspace_path=ls.workspace.root_path)

    def get_module_func(d: TextDocument) -> Module:
        return ls.get_module(d, workspace_path=ls.workspace.root_path)

    include_declaration = (
        params.context.include_declaration if params.context else False
    )

    return get_all_references(
        get_module_func,
        ls.workspace,
        doc,
        module,
        params.position,
        ls.modules,
        include_declaration,
    )


# -----------------------------------------------------------------------------
# Entry Point
# -----------------------------------------------------------------------------


def main() -> None:
    """Start the Vyper language server."""
    start_server(server)
