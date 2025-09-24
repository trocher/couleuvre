import logging
import re
from typing import Dict
from pygls.server import LanguageServer
from lsprotocol import types
from pygls.workspace import TextDocument
from pygls import uris
from couleuvre.ast_parser.vyper_ast import BaseNode
from couleuvre.cli import start_server
from couleuvre.logger_setup import setup_logging
from couleuvre import utils
from couleuvre.parser.parse import Module, parse_module
from couleuvre.features.symbols_visitor import get_document_symbols

logger = logging.getLogger("couleuvre")


class VyperLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modules: Dict = {}
        self.logger = setup_logging(self)  # Inject logging on init
        self.logger.info("Vyper Language Server starting...")
        self.default_version = None

    def parse(self, doc: TextDocument, workspace_path=None):
        self.modules[doc.uri] = parse_module(
            doc.path,
            default_version=self.default_version,
            workspace_path=workspace_path,
        )
        if not self.default_version:
            self.default_version = self.modules[doc.uri].version
        self.logger.info("Module: %s", self.modules)

    def get_module(self, doc: TextDocument, workspace_path=None):
        self.logger.info(f"get module: {doc.uri}")
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


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: VyperLanguageServer, params: types.DidOpenTextDocumentParams):
    """Parse each document when it is opened"""
    ls.logger.info(f"Document opened: {params.text_document.uri}")
    doc = ls.workspace.get_text_document(params.text_document.uri)
    ls.parse(doc, workspace_path=ls.workspace.root_path)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: VyperLanguageServer, params: types.DidChangeTextDocumentParams):
    """Parse each document when it is changed"""
    ls.logger.info(f"Document changed: {params.text_document.uri}")
    doc = ls.workspace.get_text_document(params.text_document.uri)
    ls.parse(doc, workspace_path=ls.workspace.root_path)


@server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
def document_symbol(ls: VyperLanguageServer, params: types.DocumentSymbolParams):
    """Return all the symbols defined in the given document."""
    ls.logger.info(f"Document symbol requested: {params.text_document.uri}")
    doc = ls.workspace.get_text_document(params.text_document.uri)
    symbols = get_document_symbols(
        ls.get_module(doc, workspace_path=ls.workspace.root_path)
    )
    return symbols


@server.feature(types.WORKSPACE_SYMBOL)
def workspace_symbol(ls: VyperLanguageServer, params: types.WorkspaceSymbolParams):
    """Return all the symbols defined in the given document."""
    return


def goto_in_module(doc: TextDocument, module: Module, chain: list, external=False):
    if external:
        res = module.external_namespace()
    else:
        res = module.namespace
    while chain and res:
        res = res.get(chain.pop(0), None)
    if res is not None and isinstance(res, BaseNode):
        return types.Location(uri=doc.uri, range=utils.range_from_node(res))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def goto_definition(ls: VyperLanguageServer, params: types.DefinitionParams):
    """Jump to an object's definition."""
    ls.logger.info(f"Definition requested: {params.text_document.uri}")
    doc = ls.workspace.get_text_document(params.text_document.uri)
    module = ls.get_module(doc, workspace_path=ls.workspace.root_path)

    try:
        attribute_word = doc.word_at_position(
            params.position, re.compile(r"[A-Za-z_0-9]+(?:\.[A-Za-z_0-9]+)*$")
        )
    except IndexError:
        return
    if not attribute_word:
        return

    # Local lookup
    target = goto_in_module(doc, module, attribute_word.split("."))
    if target:
        return target

    # Imported module lookup
    parts = attribute_word.split(".")
    root_name, remainder = parts[0], parts[1:]

    if root_name in module.imports.keys():
        resolved_path = module.imports[root_name]
        resolved_uri = uris.from_fs_path(resolved_path)
        if not resolved_uri:
            return
        resolved_doc = ls.workspace.get_text_document(resolved_uri)
        resolved_module = ls.get_module(
            resolved_doc, workspace_path=ls.workspace.root_path
        )
        if not remainder:
            return utils.location_from_start(resolved_doc.uri)

        return goto_in_module(resolved_doc, resolved_module, remainder, external=True)


# TODO signature help
# TODO implementation
# TODO hover
# TODO reference
# TODO definition
# TODO declaration
# TODO completion


def main():
    # TODO: replace by pygls.cli once it is released
    start_server(server)
