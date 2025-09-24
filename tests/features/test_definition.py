import tempfile
import pytest
from lsprotocol.types import (
    DefinitionParams,
    Position,
    TextDocumentIdentifier,
    Location,
    Range,
)

from couleuvre.main import goto_definition
from couleuvre.parser.parse import parse_module


@pytest.fixture
def setup_mocks(mock_language_server, mock_text_document, mock_workspace):
    """Set up the basic mock structure for LSP components."""

    def _setup(source_code, uri="file:///test.vy", word_at_pos=None):
        # Configure the text document
        mock_text_document.uri = uri
        mock_text_document.source = source_code
        if word_at_pos is not None:
            mock_text_document.word_at_position.return_value = word_at_pos

        # Parse the module and set up the language server
        with tempfile.NamedTemporaryFile(suffix=".vy", mode="w") as f:
            f.write(source_code)
            f.flush()
            module = parse_module(f.name)
        mock_language_server.get_module.return_value = module

        # Set up the workspace
        mock_workspace.get_text_document.return_value = mock_text_document
        mock_language_server.workspace = mock_workspace

        return mock_language_server, mock_text_document

    return _setup


class TestGotoDefinition:
    """Test suite for the goto_definition feature."""

    def _goto_definition(self, setup_mocks, source, word_at_pos):
        # Set up mocks using the fixture
        mock_ls, mock_doc = setup_mocks(source, word_at_pos=word_at_pos)

        # Create parameters for goto definition at position where "self.a" is referenced
        params = DefinitionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.vy"),
            position=Position(line=0, character=0),
        )

        # Call goto_definition
        result = goto_definition(mock_ls, params)

        return result

    def _goto_definition_matches(
        self, setup_mocks, source, word_at_pos, line, character
    ):
        result = self._goto_definition(setup_mocks, source, word_at_pos)
        assert result is not None
        assert isinstance(result, Location)
        assert result.uri == "file:///test.vy"
        assert isinstance(result.range, Range)

        assert result.range.start.line == line
        assert result.range.start.character == character

    def _goto_definition_no_match(self, setup_mocks, source, word_at_pos):
        """Helper to test goto definition with no match."""
        result = self._goto_definition(setup_mocks, source, word_at_pos)
        assert result is None

    def test_goto_definition_variable_reference(self, setup_mocks):
        """Test goto definition for a variable reference."""
        # Vyper source code with a variable definition and reference
        source = """# pragma version 0.3.10

a: uint256

def foo():
    x: uint256 = self.a
"""
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="self.a", line=2, character=0
        )

    def test_goto_definition_function_reference(self, setup_mocks):
        """Test goto definition for a function reference."""
        source = """# pragma version 0.3.10


def bar():
    pass

@external
def foo():
    self.bar()
"""

        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="self.bar", line=3, character=0
        )

    def test_goto_definition_self_reference(self, setup_mocks):
        """Test goto definition for self.variable reference."""
        source = """# pragma version 0.3.10

my_var: uint256

def get_var() -> uint256:
    return self.my_var
"""
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="self.my_var", line=2, character=0
        )

    def test_goto_definition_not_found(self, setup_mocks):
        """Test goto definition when symbol is not found."""
        source = """# pragma version 0.3.10

def foo():
    pass
"""
        self._goto_definition_no_match(
            setup_mocks, source, word_at_pos="nonexistent_symbol"
        )
        self._goto_definition_no_match(setup_mocks, source, word_at_pos=None)
        self._goto_definition_no_match(setup_mocks, source, word_at_pos="")
        self._goto_definition_no_match(setup_mocks, source, word_at_pos="pass")

    def test_goto_definition_index_error(self, setup_mocks):
        """Test goto definition when word_at_position raises IndexError."""
        source = """# pragma version 0.3.10

def foo():
    pass
"""

        # Set up mocks using the fixture
        mock_ls, mock_doc = setup_mocks(source)

        # Mock word_at_position to raise IndexError
        mock_doc.word_at_position.side_effect = IndexError("Position out of range")

        # Create parameters
        params = DefinitionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.vy"),
            position=Position(line=100, character=100),  # Out of range position
        )

        # Call goto_definition
        result = goto_definition(mock_ls, params)

        # Should return None when IndexError is raised
        assert result is None

    def test_goto_definition_constant_variable(self, setup_mocks):
        """Test goto definition for a constant variable."""
        source = """# pragma version 0.3.10

MAX_SUPPLY: constant(uint256) = 1000000

def get_max_supply() -> uint256:
    return MAX_SUPPLY
"""
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="MAX_SUPPLY", line=2, character=0
        )

    def test_goto_definition_struct_reference(self, setup_mocks):
        """Test goto definition for a struct reference."""
        source = """# pragma version 0.3.10

struct Person:
    name: String[100]
    age: uint256

def create_person() -> Person:
    return Person({name: "Alice", age: 30})
"""
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="Person", line=2, character=0
        )

    def test_goto_definition_types_reference(self, setup_mocks):
        """Test goto definition for an event reference."""
        source = """# pragma version 0.4.0

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    amount: uint256

struct Token:
    addr: address

flag A:
    a
@external
def transfer(to: address, amount: uint256):
    log Transfer(msg.sender, to, amount)
    x: Token = Token({addr: to})
    x: flag = A.a
"""
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="Transfer", line=2, character=0
        )
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="Token", line=7, character=0
        )
        self._goto_definition_matches(
            setup_mocks, source, word_at_pos="A", line=10, character=0
        )
        # self._goto_definition_matches(setup_mocks, source, word_at_pos="A.a", line=10, character=0)
