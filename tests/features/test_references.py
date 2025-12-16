"""
Tests for the goto-references feature.

Uses the VyperTestHarness for clean, declarative tests.
Line numbers are 0-indexed (LSP convention).
"""

from unittest.mock import Mock
from lsprotocol.types import (
    Position,
    ReferenceContext,
    ReferenceParams,
    TextDocumentIdentifier,
)

from couleuvre.ast import nodes
from couleuvre.main import goto_references
from couleuvre.parser.parse import Module


class TestGotoReferences:
    """Test suite for goto_references feature."""

    # =========================================================================
    # State Variables
    # =========================================================================

    def test_state_variable_references(self, vyper_harness):
        """Test finding references to a state variable."""
        # Line 0: # pragma version 0.3.10
        # Line 1: (empty)
        # Line 2: counter: uint256
        # Line 3: (empty)
        # Line 4: @external
        # Line 5: def increment():
        # Line 6:     self.counter += 1  <- reference
        # Line 7: (empty)
        # Line 8: @external
        # Line 9: def get_counter() -> uint256:
        # Line 10:    return self.counter  <- reference
        source = """# pragma version 0.3.10

counter: uint256

@external
def increment():
    self.counter += 1

@external
def get_counter() -> uint256:
    return self.counter
"""
        vyper_harness.setup(source, word_at_pos="self.counter")
        vyper_harness.assert_references_at_lines([6, 10])

    def test_state_variable_with_declaration(self, vyper_harness):
        """Test finding references including declaration."""
        # Line 2: balance: uint256  <- declaration
        # Line 6: self.balance += msg.value  <- reference
        source = """# pragma version 0.3.10

balance: uint256

@external
def deposit():
    self.balance += msg.value
"""
        vyper_harness.setup(source, word_at_pos="self.balance")
        vyper_harness.assert_references_at_lines([2, 6], include_declaration=True)

    def test_multiple_state_variable_references(self, vyper_harness):
        """Test finding multiple references to the same state variable."""
        source = """# pragma version 0.3.10

counter: uint256

@external
def increment():
    self.counter += 1

@external
def decrement():
    self.counter -= 1

@external
def reset():
    self.counter = 0

@external
def get() -> uint256:
    return self.counter
"""
        vyper_harness.setup(source, word_at_pos="self.counter")
        # References at: line 6, 10, 14, 18
        vyper_harness.assert_references_at_lines([6, 10, 14, 18])

    # =========================================================================
    # Constants and Immutables
    # =========================================================================

    def test_constant_references(self, vyper_harness):
        """Test finding references to a constant."""
        source = """# pragma version 0.3.10

MAX_SUPPLY: constant(uint256) = 1000000

@external
def check() -> bool:
    return MAX_SUPPLY > 0

@external
def get_max() -> uint256:
    return MAX_SUPPLY
"""
        vyper_harness.setup(source, word_at_pos="MAX_SUPPLY")
        # References at: line 6, 10
        vyper_harness.assert_references_at_lines([6, 10])

    def test_constant_with_declaration(self, vyper_harness):
        """Test finding constant references including declaration."""
        source = """# pragma version 0.3.10

MAX_VALUE: constant(uint256) = 100

@external
def get_max() -> uint256:
    return MAX_VALUE
"""
        vyper_harness.setup(source, word_at_pos="MAX_VALUE")
        # Declaration at line 2, reference at line 6
        vyper_harness.assert_references_at_lines([2, 6], include_declaration=True)

    def test_immutable_references(self, vyper_harness):
        """Test finding references to an immutable variable."""
        source = """# pragma version 0.3.10

OWNER: immutable(address)

@deploy
def __init__():
    OWNER = msg.sender

@external
def get_owner() -> address:
    return OWNER
"""
        vyper_harness.setup(source, word_at_pos="OWNER")
        # References at: line 6 (assignment), line 10 (usage)
        vyper_harness.assert_references_at_lines([6, 10])

    # =========================================================================
    # Functions
    # =========================================================================

    def test_function_references(self, vyper_harness):
        """Test finding references to a function."""
        source = """# pragma version 0.3.10

@internal
def helper() -> uint256:
    return 42

@external
def foo() -> uint256:
    return self.helper()

@external
def bar() -> uint256:
    return self.helper() + 1
"""
        vyper_harness.setup(source, word_at_pos="self.helper")
        # References at: line 8, 12
        vyper_harness.assert_references_at_lines([8, 12])

    def test_function_with_declaration(self, vyper_harness):
        """Test finding function references including declaration."""
        source = """# pragma version 0.3.10

@internal
def compute() -> uint256:
    return 100

@external
def get_value() -> uint256:
    return self.compute()
"""
        vyper_harness.setup(source, word_at_pos="self.compute")
        # Declaration at line 3, reference at line 8
        vyper_harness.assert_references_at_lines([3, 8], include_declaration=True)

    # =========================================================================
    # Events
    # =========================================================================

    def test_event_references(self, vyper_harness):
        """Test finding references to an event."""
        source = """# pragma version 0.4.0

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    amount: uint256

@external
def transfer(to: address, amount: uint256):
    log Transfer(msg.sender, to, amount)

@external
def batch_transfer(to: address, amount: uint256):
    log Transfer(msg.sender, to, amount)
"""
        vyper_harness.setup(source, word_at_pos="Transfer")
        # References at: line 9, 13
        vyper_harness.assert_references_at_lines([9, 13])

    def test_event_with_declaration(self, vyper_harness):
        """Test finding event references including declaration."""
        source = """# pragma version 0.4.0

event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256

@external
def approve(spender: address, amount: uint256):
    log Approval(msg.sender, spender, amount)
"""
        vyper_harness.setup(source, word_at_pos="Approval")
        # Declaration at line 2, reference at line 9
        vyper_harness.assert_references_at_lines([2, 9], include_declaration=True)

    # =========================================================================
    # Structs
    # =========================================================================

    def test_struct_references(self, vyper_harness):
        """Test finding references to a struct."""
        source = """# pragma version 0.4.0

struct Person:
    name: String[100]
    age: uint256

@external
def create_person() -> Person:
    return Person({name: "Alice", age: 30})

@external
def empty_person() -> Person:
    return Person({name: "", age: 0})
"""
        vyper_harness.setup(source, word_at_pos="Person")
        # References at: line 7 (return type), 8 (constructor), 11 (return type), 12 (constructor)
        vyper_harness.assert_references_at_lines([7, 8, 11, 12])

    # =========================================================================
    # Flags
    # =========================================================================

    def test_flag_references(self, vyper_harness):
        """Test finding references to a flag."""
        source = """# pragma version 0.4.0

flag Status:
    ACTIVE
    INACTIVE

@external
def get_status() -> Status:
    return Status.ACTIVE

@external
def is_active(s: Status) -> bool:
    return s == Status.ACTIVE
"""
        vyper_harness.setup(source, word_at_pos="Status")
        # References at: line 7 (return type), 8 (member access), 11 (param type), 12 (member access)
        vyper_harness.assert_references_at_lines([7, 8, 11, 12])

    # =========================================================================
    # Interfaces
    # =========================================================================

    def test_interface_references(self, vyper_harness):
        """Test finding references to an interface."""
        source = """# pragma version 0.4.0

interface IERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable
    def balanceOf(owner: address) -> uint256: view

@external
def check_balance(token: IERC20, owner: address) -> uint256:
    return token.balanceOf(owner)

@external
def do_transfer(token: IERC20, to: address, amount: uint256):
    token.transfer(to, amount)
"""
        vyper_harness.setup(source, word_at_pos="IERC20")
        # References at: line 7 (param type), 11 (param type)
        vyper_harness.assert_references_at_lines([7, 11])

    def test_interface_with_declaration(self, vyper_harness):
        """Test finding interface references including declaration."""
        source = """# pragma version 0.4.0

interface IVault:
    def deposit(amount: uint256): nonpayable

@external
def deposit_to(vault: IVault, amount: uint256):
    vault.deposit(amount)
"""
        vyper_harness.setup(source, word_at_pos="IVault")
        # Declaration at line 2, reference at line 6 (param type)
        vyper_harness.assert_references_at_lines([2, 6], include_declaration=True)

    # =========================================================================
    # Negative Cases / Edge Cases
    # =========================================================================

    def test_no_references_when_symbol_not_found(self, vyper_harness):
        """Test that empty list is returned when symbol is not found."""
        source = """# pragma version 0.3.10

@external
def foo():
    pass
"""
        vyper_harness.setup(source, word_at_pos="nonexistent")
        vyper_harness.assert_no_references()

    def test_empty_word_returns_no_references(self, vyper_harness):
        """Test that empty list is returned when word is empty."""
        source = """# pragma version 0.3.10

@external
def foo():
    pass
"""
        vyper_harness.setup(source, word_at_pos="")
        vyper_harness.assert_no_references()

    def test_index_error(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test that empty list is returned when IndexError is raised."""
        mock_text_document.uri = "file:///test.vy"
        mock_text_document.word_at_position.side_effect = IndexError("out of range")
        mock_workspace.get_text_document.return_value = mock_text_document
        mock_language_server.workspace = mock_workspace

        params = ReferenceParams(
            text_document=TextDocumentIdentifier(uri="file:///test.vy"),
            position=Position(line=100, character=100),
            context=ReferenceContext(include_declaration=False),
        )
        result = goto_references(mock_language_server, params)
        assert result == []


# =============================================================================
# AST-Based Tests (for edge cases requiring manual AST construction)
# =============================================================================


def _make_module(path: str = "/tmp/test.vy") -> Module:
    """Create a Module with empty AST."""
    module_ast = nodes.Module(ast_type="Module", resolved_path=path)
    return Module(module_ast, "0.3.10")


def _make_name(identifier: str, line: int, col: int = 0) -> nodes.Name:
    """Create a Name node."""
    return nodes.Name(
        ast_type="Name",
        id=identifier,
        lineno=line,
        col_offset=col,
        end_lineno=line,
        end_col_offset=col + len(identifier),
    )


def _setup_refs_test(
    mock_language_server,
    mock_text_document,
    mock_workspace,
    module: Module,
    word_at_pos: str,
    uri: str = "file:///tmp/test.vy",
):
    """Common setup for reference tests."""
    mock_text_document.uri = uri
    mock_text_document.word_at_position.return_value = word_at_pos
    mock_workspace.get_text_document.return_value = mock_text_document
    mock_language_server.workspace = mock_workspace
    mock_language_server.get_module.return_value = module


def _call_refs(
    mock_language_server,
    uri: str = "file:///tmp/test.vy",
    include_declaration: bool = False,
):
    """Call goto_references and return the result."""
    params = ReferenceParams(
        text_document=TextDocumentIdentifier(uri=uri),
        position=Position(line=0, character=0),
        context=ReferenceContext(include_declaration=include_declaration),
    )
    return goto_references(mock_language_server, params)


class TestGotoReferencesAST:
    """Tests using manually constructed AST for edge cases."""

    def test_import_alias_references(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test finding references across imports."""
        # Target module with event definition
        target_module = _make_module("/tmp/target.vy")
        event_def = nodes.EventDef(
            ast_type="EventDef",
            name="Transfer",
            lineno=1,
            col_offset=0,
            end_lineno=1,
            end_col_offset=10,
        )
        target_module.ast.body.append(event_def)
        target_module.namespace["Transfer"] = event_def
        target_module.events.add(event_def)

        # Importer module with alias reference
        importer_module = _make_module("/tmp/importer.vy")
        importer_module.imports["token"] = "/tmp/target.vy"

        alias_name = _make_name("token", 4)
        alias_reference = nodes.Attribute(
            ast_type="Attribute",
            value=alias_name,
            attr="Transfer",
            lineno=4,
            col_offset=0,
            end_lineno=4,
            end_col_offset=13,
        )
        alias_name.parent = alias_reference
        importer_module.ast.body.append(alias_reference)

        # Set up mocks
        importer_uri = "file:///tmp/importer.vy"
        target_uri = "file:///tmp/target.vy"

        importer_doc = mock_text_document
        importer_doc.uri = importer_uri
        importer_doc.word_at_position.return_value = "token.Transfer"

        target_doc = Mock()
        target_doc.uri = target_uri

        mock_workspace.get_text_document.side_effect = (
            lambda uri: importer_doc if uri == importer_uri else target_doc
        )
        mock_language_server.workspace = mock_workspace

        def _get_module(doc, workspace_path=None):
            if doc.uri == importer_uri:
                return importer_module
            return target_module

        mock_language_server.get_module.side_effect = _get_module

        result = _call_refs(
            mock_language_server, importer_uri, include_declaration=True
        )

        assert len(result) == 2
        uris = {loc.uri for loc in result}
        assert importer_uri in uris
        assert target_uri in uris

    def test_flag_member_not_counted_as_reference(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test that flag member with same name as constant is not a reference."""
        module = _make_module()

        # Constant named 'xs'
        const_target = _make_name("xs", 1)
        const_decl = nodes.VariableDecl(
            ast_type="VariableDecl",
            target=const_target,
            lineno=1,
            col_offset=0,
            end_lineno=1,
            end_col_offset=25,
            is_constant=True,
            is_immutable=False,
        )
        const_target.parent = const_decl
        module.ast.body.append(const_decl)
        module.namespace["xs"] = const_decl
        module.variables.add(const_decl)

        # Flag with member named 'xs' - should NOT be a reference
        flag_member = _make_name("xs", 4)
        flag_def = nodes.FlagDef(
            ast_type="FlagDef",
            name="F",
            body=[flag_member],
            lineno=3,
            col_offset=0,
            end_lineno=4,
            end_col_offset=6,
        )
        flag_member.parent = flag_def
        module.ast.body.append(flag_def)
        module.namespace["F"] = flag_def

        _setup_refs_test(
            mock_language_server, mock_text_document, mock_workspace, module, "xs"
        )

        result = _call_refs(mock_language_server)
        assert len(result) == 0

    def test_event_field_not_counted_as_reference(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test that event field with same name as constant is not a reference."""
        module = _make_module()

        # Constant named 'value'
        const_target = _make_name("value", 1)
        const_decl = nodes.VariableDecl(
            ast_type="VariableDecl",
            target=const_target,
            lineno=1,
            col_offset=0,
            end_lineno=1,
            end_col_offset=20,
            is_constant=True,
            is_immutable=False,
        )
        const_target.parent = const_decl
        module.ast.body.append(const_decl)
        module.namespace["value"] = const_decl
        module.variables.add(const_decl)

        # Event with field named 'value' - should NOT be a reference
        event_field = _make_name("value", 4)
        event_def = nodes.EventDef(
            ast_type="EventDef",
            name="Transfer",
            body=[event_field],
            lineno=3,
            col_offset=0,
            end_lineno=4,
            end_col_offset=10,
        )
        event_field.parent = event_def
        module.ast.body.append(event_def)
        module.namespace["Transfer"] = event_def

        _setup_refs_test(
            mock_language_server, mock_text_document, mock_workspace, module, "value"
        )

        result = _call_refs(mock_language_server)
        assert len(result) == 0

    def test_struct_field_not_counted_as_reference(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test that struct field with same name as constant is not a reference."""
        module = _make_module()

        # Constant named 'amount'
        const_target = _make_name("amount", 1)
        const_decl = nodes.VariableDecl(
            ast_type="VariableDecl",
            target=const_target,
            lineno=1,
            col_offset=0,
            end_lineno=1,
            end_col_offset=22,
            is_constant=True,
            is_immutable=False,
        )
        const_target.parent = const_decl
        module.ast.body.append(const_decl)
        module.namespace["amount"] = const_decl
        module.variables.add(const_decl)

        # Struct with field named 'amount' - should NOT be a reference
        struct_field = _make_name("amount", 4)
        struct_def = nodes.StructDef(
            ast_type="StructDef",
            name="Payment",
            body=[struct_field],
            lineno=3,
            col_offset=0,
            end_lineno=4,
            end_col_offset=12,
        )
        struct_field.parent = struct_def
        module.ast.body.append(struct_def)
        module.namespace["Payment"] = struct_def

        _setup_refs_test(
            mock_language_server, mock_text_document, mock_workspace, module, "amount"
        )

        result = _call_refs(mock_language_server)
        assert len(result) == 0
