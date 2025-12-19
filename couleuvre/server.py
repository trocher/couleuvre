"""
Couleuvre - Vyper Language Server.

This module provides the main entry point for the Vyper LSP server,
implementing standard LSP features like go-to-definition, references,
and document symbols.
"""

import asyncio
import logging
from typing import Dict, List, Optional

from lsprotocol import types
from pygls import uris
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from couleuvre import utils
from couleuvre.features.completion import get_completions
from couleuvre.features.definition import get_definition_location
from couleuvre.features.diagnostics import (
    compile_and_get_diagnostics,
    create_diagnostic,
    parse_error_location,
)
from couleuvre.features.references import get_all_references
from couleuvre.features.symbols import get_document_symbols
from couleuvre.logger_setup import setup_logging
from couleuvre.parser import Module, parse_module

logger = logging.getLogger("couleuvre")

# Debounce delay for AST parsing (in seconds) - short for responsive navigation
PARSE_DEBOUNCE_DELAY = 0.3

# Debounce delay for full compilation diagnostics (in seconds)
DIAGNOSTICS_DEBOUNCE_DELAY = 1.0


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
        # Debounce timers for AST parsing
        self._parse_tasks: Dict[str, asyncio.Task] = {}
        # Debounce timers for full compilation diagnostics
        self._diagnostics_tasks: Dict[str, asyncio.Task] = {}

    def publish_diagnostics(
        self, uri: str, diagnostics: List[types.Diagnostic]
    ) -> None:
        """Publish diagnostics for a document."""
        self.text_document_publish_diagnostics(
            types.PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
        )

    def clear_diagnostics(self, uri: str) -> None:
        """Clear all diagnostics for a document."""
        self.publish_diagnostics(uri, [])

    def parse(self, doc: TextDocument, workspace_path: Optional[str] = None) -> bool:
        """
        Parse a document and cache its module (AST only, fast).

        This is used for navigation features (go-to-definition, references, etc.).
        Full compilation diagnostics are run separately via schedule_diagnostics().

        Note: On parse failure, we keep the last successfully parsed module
        so that features like completion still work while typing.

        Returns:
            True if parsing succeeded, False otherwise.
        """
        try:
            self.modules[doc.uri] = parse_module(
                doc.path,
                default_version=self.default_version,
                workspace_path=workspace_path,
                source=doc.source,
            )
            if not self.default_version:
                self.default_version = self.modules[doc.uri].version
            self.logger.debug("Parsed module: %s", doc.uri)
            return True
        except ValueError as e:
            # Missing or invalid version pragma
            self.logger.warning("Parse failed for %s: %s", doc.uri, e)
            self._publish_parse_error(doc.uri, str(e), is_version_error=True)
            # Keep the last valid module for completion/navigation
            return False
        except RuntimeError as e:
            # Vyper compiler error (AST stage)
            self.logger.warning("Vyper AST parsing failed for %s: %s", doc.uri, e)
            self._publish_parse_error(doc.uri, str(e), is_version_error=False)
            # Keep the last valid module for completion/navigation
            return False
        except Exception as e:
            # Unexpected error - log and publish generic diagnostic
            self.logger.error("Unexpected error parsing %s: %s", doc.uri, e)
            self._publish_parse_error(doc.uri, f"Unexpected error: {e}")
            # Keep the last valid module for completion/navigation
            return False

    def _publish_parse_error(
        self, uri: str, message: str, is_version_error: bool = False
    ) -> None:
        """Publish a diagnostic for a parse error."""
        # For version errors, suggest adding a pragma
        if is_version_error:
            message = f"{message}. Add '#pragma version ^0.4.0' at the top of the file."

        line, col = parse_error_location(message)
        diagnostic = create_diagnostic(
            message=message,
            start_line=line,
            start_col=col,
            source="couleuvre",
        )
        self.publish_diagnostics(uri, [diagnostic])

    def schedule_diagnostics(
        self, doc: TextDocument, workspace_path: Optional[str] = None
    ) -> None:
        """
        Schedule full compilation diagnostics with debouncing.

        This runs the complete Vyper compilation pipeline (slower) to catch
        type errors, semantic errors, etc. The diagnostics are debounced
        to avoid excessive compilation on every keystroke.
        """
        uri = doc.uri

        # Cancel any pending diagnostics task for this document
        if uri in self._diagnostics_tasks:
            self._diagnostics_tasks[uri].cancel()

        # Schedule a new diagnostics task
        async def run_diagnostics_after_delay():
            try:
                await asyncio.sleep(DIAGNOSTICS_DEBOUNCE_DELAY)
                await self._run_full_diagnostics(doc, workspace_path)
            except asyncio.CancelledError:
                # Task was cancelled due to new edits, this is expected
                pass

        self._diagnostics_tasks[uri] = asyncio.create_task(
            run_diagnostics_after_delay()
        )

    def schedule_parse(
        self, doc: TextDocument, workspace_path: Optional[str] = None
    ) -> None:
        """
        Schedule AST parsing with debouncing.

        This runs AST extraction (fast) for navigation features.
        Debounced to avoid parsing on every keystroke.
        """
        uri = doc.uri

        # Cancel any pending parse task for this document
        if uri in self._parse_tasks:
            self._parse_tasks[uri].cancel()

        # Schedule a new parse task
        async def run_parse_after_delay():
            try:
                await asyncio.sleep(PARSE_DEBOUNCE_DELAY)
                # Run parsing in a thread to avoid blocking
                await asyncio.to_thread(self.parse, doc, workspace_path)
            except asyncio.CancelledError:
                # Task was cancelled due to new edits, this is expected
                pass

        self._parse_tasks[uri] = asyncio.create_task(run_parse_after_delay())

    def schedule_import_parsing(
        self, module: Module, workspace_path: Optional[str] = None
    ) -> None:
        """
        Schedule background parsing of all imports in a module.

        This pre-parses imported modules so that completion and navigation
        for imported symbols is instant.
        """
        for import_name, resolved_path in module.imports.items():
            uri = uris.from_fs_path(resolved_path)
            if not uri:
                continue

            # Skip if already parsed
            if uri in self.modules:
                continue

            # Schedule background parsing
            async def parse_import(import_uri: str, import_path: str) -> None:
                try:
                    # Small delay to not compete with main document parsing
                    await asyncio.sleep(0.1)
                    self.logger.debug("Background parsing import: %s", import_path)
                    await asyncio.to_thread(
                        self._parse_import, import_uri, import_path, workspace_path
                    )
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    self.logger.debug("Failed to parse import %s: %s", import_path, e)

            asyncio.create_task(parse_import(uri, resolved_path))

    def _parse_import(
        self, uri: str, path: str, workspace_path: Optional[str] = None
    ) -> None:
        """
        Parse an imported module and cache it.

        This is a simplified version of parse() that doesn't publish diagnostics.
        """
        if uri in self.modules:
            return

        try:
            module = parse_module(
                path,
                default_version=self.default_version,
                workspace_path=workspace_path,
            )
            self.modules[uri] = module
            self.logger.debug("Cached import module: %s", uri)

            # Recursively parse imports of this module
            self.schedule_import_parsing(module, workspace_path)
        except Exception as e:
            # Silently fail for imports - they may not be valid standalone
            self.logger.debug("Could not parse import %s: %s", path, e)

    async def _run_full_diagnostics(
        self, doc: TextDocument, workspace_path: Optional[str] = None
    ) -> None:
        """
        Run full Vyper compilation and publish diagnostics.

        This is run in the background after a debounce delay.
        """
        # Get the Vyper version from the parsed module or default
        module = self.modules.get(doc.uri)
        if module is None:
            # If AST parsing failed, we already have diagnostics
            return

        version = module.version

        self.logger.debug(
            "Running full diagnostics for %s (vyper %s)", doc.uri, version
        )

        try:
            # Run compilation in a thread to avoid blocking the event loop
            diagnostics = await asyncio.to_thread(
                compile_and_get_diagnostics,
                doc.path,
                version,
                workspace_path,
                doc.source,
            )

            # Publish the diagnostics
            self.publish_diagnostics(doc.uri, diagnostics)
            self.logger.debug(
                "Published %d diagnostics for %s", len(diagnostics), doc.uri
            )
        except Exception as e:
            self.logger.error("Full diagnostics failed for %s: %s", doc.uri, e)
            # Don't publish error - we already have AST-level diagnostics if needed

    def get_module(
        self, doc: TextDocument, workspace_path: Optional[str] = None
    ) -> Optional[Module]:
        """
        Get or parse the module for a document.

        Returns:
            The parsed Module, or None if parsing failed.
        """
        self.logger.debug("Getting module: %s", doc.uri)
        if doc.uri not in self.modules:
            success = self.parse(doc, workspace_path)
            if not success:
                return None
        return self.modules.get(doc.uri)


server = VyperLanguageServer("couleuvre", "v0.0.4")


# -----------------------------------------------------------------------------
# Document Lifecycle Events
# -----------------------------------------------------------------------------


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: VyperLanguageServer, params: types.DidOpenTextDocumentParams) -> None:
    """Parse document when opened and schedule full diagnostics."""
    ls.logger.debug("Document opened: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    # Fast AST parse for navigation
    ls.parse(doc, workspace_path=ls.workspace.root_path)
    # Schedule background parsing of imports for instant completion
    module = ls.modules.get(doc.uri)
    if module:
        ls.schedule_import_parsing(module, workspace_path=ls.workspace.root_path)
    # Schedule full compilation diagnostics (debounced)
    ls.schedule_diagnostics(doc, workspace_path=ls.workspace.root_path)


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(
    ls: VyperLanguageServer, params: types.DidChangeTextDocumentParams
) -> None:
    """Re-parse document when changed and schedule full diagnostics."""
    ls.logger.debug("Document changed: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)
    # Schedule debounced AST parse for navigation (non-blocking)
    ls.schedule_parse(doc, workspace_path=ls.workspace.root_path)
    # Schedule full compilation diagnostics (debounced, will cancel previous)
    ls.schedule_diagnostics(doc, workspace_path=ls.workspace.root_path)


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
    if module is None:
        return []
    return get_document_symbols(module)


@server.feature(types.WORKSPACE_SYMBOL)
def workspace_symbol(
    ls: VyperLanguageServer, params: types.WorkspaceSymbolParams
) -> List[types.WorkspaceSymbol]:
    """Return symbols matching the query across the workspace."""
    # TODO: Implement workspace symbol search
    return []


# -----------------------------------------------------------------------------
# Completion Features
# -----------------------------------------------------------------------------


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION, types.CompletionOptions(trigger_characters=["."])
)
def completion(
    ls: VyperLanguageServer, params: types.CompletionParams
) -> List[types.CompletionItem]:
    """Provide completion suggestions.

    Supports:
    - `self.` - state variables (non-constant, non-immutable) and internal functions
    - `<module>.` - symbols from imported modules

    Note: Uses cached module directly for instant completion (doesn't wait for parsing).
    """
    ls.logger.debug("Completion requested: %s", params.text_document.uri)
    doc = ls.workspace.get_text_document(params.text_document.uri)

    # Use cached module directly for fast completion - don't trigger a parse
    # This is important because typing "self." creates invalid syntax,
    # and we don't want to wait for parsing to fail
    module = ls.modules.get(doc.uri)
    if module is None:
        return []

    def get_module_func(d: TextDocument) -> Optional[Module]:
        # For imported modules, also prefer cached over parsing
        return ls.modules.get(d.uri)

    return get_completions(get_module_func, ls.workspace, doc, module, params.position)


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
    if module is None:
        return None

    def get_module_func(d: TextDocument) -> Optional[Module]:
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
    if module is None:
        return []

    def get_module_func(d: TextDocument) -> Optional[Module]:
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
