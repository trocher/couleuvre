"""
Shared test fixtures and utilities for Couleuvre tests.
"""

import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple
from unittest.mock import Mock

import pytest
from lsprotocol.types import (
    DefinitionParams,
    Location,
    Position,
    ReferenceContext,
    ReferenceParams,
    TextDocumentIdentifier,
)
from pygls.workspace import TextDocument

from couleuvre.ast import nodes
from couleuvre.main import VyperLanguageServer, goto_definition, goto_references
from couleuvre.parser.parse import Module, parse_module


# =============================================================================
# Basic Mocks
# =============================================================================


@pytest.fixture
def mock_language_server():
    """Create a mock VyperLanguageServer."""
    ls = Mock(spec=VyperLanguageServer)
    ls.logger = Mock()
    ls.logger.info = Mock()
    ls.logger.debug = Mock()
    ls.modules = {}
    return ls


@pytest.fixture
def mock_text_document():
    """Create a mock TextDocument."""
    return Mock(spec=TextDocument)


@pytest.fixture
def mock_workspace():
    """Create a mock workspace."""
    return Mock()


# =============================================================================
# Vyper Source Test Harness
# =============================================================================


@dataclass
class DefinitionTestCase:
    """A test case for goto-definition tests."""

    name: str
    source: str
    word_at_pos: str
    expected_line: Optional[int]  # None means no match expected
    expected_char: int = 0
    cursor_line: int = 0
    cursor_char: int = 0


@dataclass
class ReferencesTestCase:
    """A test case for goto-references tests."""

    name: str
    source: str
    word_at_pos: str
    expected_lines: List[int]  # Empty list means no matches expected
    include_declaration: bool = False
    cursor_line: int = 0
    cursor_char: int = 0


class VyperTestHarness:
    """
    Test harness for Vyper LSP features.

    Provides a clean API for testing goto-definition and goto-references
    by parsing real Vyper source code.
    """

    def __init__(
        self,
        mock_language_server: Mock,
        mock_text_document: Mock,
        mock_workspace: Mock,
    ):
        self.ls = mock_language_server
        self.doc = mock_text_document
        self.workspace = mock_workspace
        self._uri = "file:///test.vy"

    def setup(
        self,
        source: str,
        word_at_pos: Optional[str] = None,
        uri: str = "file:///test.vy",
    ) -> "VyperTestHarness":
        """
        Set up the test harness with Vyper source code.

        Args:
            source: Vyper source code to parse.
            word_at_pos: The word that would be returned by word_at_position.
            uri: The document URI.

        Returns:
            self for chaining.
        """
        self._uri = uri
        self.doc.uri = uri
        self.doc.source = source

        if word_at_pos is not None:
            self.doc.word_at_position.return_value = word_at_pos

        # Parse the module
        with tempfile.NamedTemporaryFile(suffix=".vy", mode="w", delete=False) as f:
            f.write(source)
            f.flush()
            module = parse_module(f.name)

        self.ls.get_module.return_value = module
        self.workspace.get_text_document.return_value = self.doc
        self.ls.workspace = self.workspace

        return self

    def goto_definition(
        self,
        line: int = 0,
        character: int = 0,
    ) -> Optional[Location]:
        """
        Call goto_definition and return the result.

        Args:
            line: Cursor line (0-indexed).
            character: Cursor character (0-indexed).

        Returns:
            The Location result, or None.
        """
        params = DefinitionParams(
            text_document=TextDocumentIdentifier(uri=self._uri),
            position=Position(line=line, character=character),
        )
        return goto_definition(self.ls, params)

    def goto_references(
        self,
        line: int = 0,
        character: int = 0,
        include_declaration: bool = False,
    ) -> List[Location]:
        """
        Call goto_references and return the result.

        Args:
            line: Cursor line (0-indexed).
            character: Cursor character (0-indexed).
            include_declaration: Whether to include the declaration.

        Returns:
            List of Location results.
        """
        params = ReferenceParams(
            text_document=TextDocumentIdentifier(uri=self._uri),
            position=Position(line=line, character=character),
            context=ReferenceContext(include_declaration=include_declaration),
        )
        return goto_references(self.ls, params)

    def assert_definition_at(
        self,
        expected_line: int,
        expected_char: int = 0,
        cursor_line: int = 0,
        cursor_char: int = 0,
    ) -> None:
        """Assert that goto_definition returns a location at the expected position."""
        result = self.goto_definition(cursor_line, cursor_char)
        assert result is not None, "Expected a definition location, got None"
        assert isinstance(result, Location)
        assert result.uri == self._uri
        assert result.range.start.line == expected_line, (
            f"Expected line {expected_line}, got {result.range.start.line}"
        )
        assert result.range.start.character == expected_char, (
            f"Expected char {expected_char}, got {result.range.start.character}"
        )

    def assert_no_definition(
        self,
        cursor_line: int = 0,
        cursor_char: int = 0,
    ) -> None:
        """Assert that goto_definition returns None."""
        result = self.goto_definition(cursor_line, cursor_char)
        assert result is None, f"Expected None, got {result}"

    def assert_references_at_lines(
        self,
        expected_lines: List[int],
        cursor_line: int = 0,
        cursor_char: int = 0,
        include_declaration: bool = False,
    ) -> None:
        """Assert that goto_references returns locations at the expected lines."""
        result = self.goto_references(cursor_line, cursor_char, include_declaration)
        actual_lines = {loc.range.start.line for loc in result}
        expected_set = set(expected_lines)
        assert actual_lines == expected_set, (
            f"Expected lines {expected_set}, got {actual_lines}"
        )

    def assert_no_references(
        self,
        cursor_line: int = 0,
        cursor_char: int = 0,
        include_declaration: bool = False,
    ) -> None:
        """Assert that goto_references returns an empty list."""
        result = self.goto_references(cursor_line, cursor_char, include_declaration)
        assert result == [], f"Expected empty list, got {result}"


@pytest.fixture
def vyper_harness(mock_language_server, mock_text_document, mock_workspace):
    """Create a VyperTestHarness instance."""
    return VyperTestHarness(mock_language_server, mock_text_document, mock_workspace)


# =============================================================================
# AST Node Builders (for unit tests that need manual AST construction)
# =============================================================================


class ASTBuilder:
    """
    Builder for creating AST nodes for testing.

    Useful for tests that need to manually construct AST structures
    without parsing real Vyper source.
    """

    @staticmethod
    def module(path: str = "/tmp/test.vy", version: str = "0.3.10") -> Module:
        """Create a Module with empty AST."""
        module_ast = nodes.Module(ast_type="Module", resolved_path=path)
        return Module(module_ast, version)

    @staticmethod
    def name(
        identifier: str,
        line: int,
        col: int = 0,
        end_col: Optional[int] = None,
    ) -> nodes.Name:
        """Create a Name node."""
        if end_col is None:
            end_col = col + len(identifier)
        return nodes.Name(
            ast_type="Name",
            id=identifier,
            lineno=line,
            col_offset=col,
            end_lineno=line,
            end_col_offset=end_col,
        )

    @staticmethod
    def attribute(
        value: nodes.Name,
        attr: str,
        line: int,
        col: int = 0,
        end_col: Optional[int] = None,
    ) -> nodes.Attribute:
        """Create an Attribute node (e.g., self.foo)."""
        if end_col is None:
            end_col = col + len(f"{value.id}.{attr}")
        attr_node = nodes.Attribute(
            ast_type="Attribute",
            value=value,
            attr=attr,
            lineno=line,
            col_offset=col,
            end_lineno=line,
            end_col_offset=end_col,
        )
        value.parent = attr_node
        return attr_node

    @staticmethod
    def variable_decl(
        name: str,
        line: int,
        col: int = 0,
        is_constant: bool = False,
        is_immutable: bool = False,
    ) -> Tuple[nodes.VariableDecl, nodes.Name]:
        """Create a VariableDecl node with its target Name."""
        target = ASTBuilder.name(name, line, col)
        decl = nodes.VariableDecl(
            ast_type="VariableDecl",
            target=target,
            lineno=line,
            col_offset=col,
            end_lineno=line,
            end_col_offset=col + len(name) + 10,  # approximate
            is_constant=is_constant,
            is_immutable=is_immutable,
        )
        target.parent = decl
        return decl, target

    @staticmethod
    def function_def(
        name: str,
        line: int,
        col: int = 0,
        end_line: Optional[int] = None,
    ) -> nodes.FunctionDef:
        """Create a FunctionDef node."""
        return nodes.FunctionDef(
            ast_type="FunctionDef",
            name=name,
            lineno=line,
            col_offset=col,
            end_lineno=end_line or line + 2,
            end_col_offset=8,
        )

    @staticmethod
    def event_def(name: str, line: int, col: int = 0) -> nodes.EventDef:
        """Create an EventDef node."""
        return nodes.EventDef(
            ast_type="EventDef",
            name=name,
            lineno=line,
            col_offset=col,
            end_lineno=line + 2,
            end_col_offset=20,
        )

    @staticmethod
    def struct_def(name: str, line: int, col: int = 0) -> nodes.StructDef:
        """Create a StructDef node."""
        return nodes.StructDef(
            ast_type="StructDef",
            name=name,
            lineno=line,
            col_offset=col,
            end_lineno=line + 2,
            end_col_offset=16,
        )

    @staticmethod
    def flag_def(name: str, line: int, col: int = 0) -> nodes.FlagDef:
        """Create a FlagDef node."""
        return nodes.FlagDef(
            ast_type="FlagDef",
            name=name,
            lineno=line,
            col_offset=col,
            end_lineno=line + 2,
            end_col_offset=10,
        )

    @staticmethod
    def interface_def(name: str, line: int, col: int = 0) -> nodes.InterfaceDef:
        """Create an InterfaceDef node."""
        return nodes.InterfaceDef(
            ast_type="InterfaceDef",
            name=name,
            lineno=line,
            col_offset=col,
            end_lineno=line + 2,
            end_col_offset=20,
        )


@pytest.fixture
def ast_builder():
    """Provide an ASTBuilder instance."""
    return ASTBuilder()
