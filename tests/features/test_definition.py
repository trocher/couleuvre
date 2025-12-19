"""
Tests for the goto-definition feature.

Uses the VyperTestHarness for clean, declarative tests.
"""

from lsprotocol.types import DefinitionParams, Position, TextDocumentIdentifier

from couleuvre.server import goto_definition


class TestGotoDefinition:
    """Test suite for goto_definition feature."""

    # =========================================================================
    # State Variables
    # =========================================================================

    def test_state_variable(self, vyper_harness):
        """Test goto definition for a state variable reference."""
        source = """# pragma version 0.3.10

a: uint256

def foo():
    x: uint256 = self.a
"""
        vyper_harness.setup(source, word_at_pos="self.a")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_self_reference(self, vyper_harness):
        """Test goto definition for self.variable reference."""
        source = """# pragma version 0.3.10

my_var: uint256

def get_var() -> uint256:
    return self.my_var
"""
        vyper_harness.setup(source, word_at_pos="self.my_var")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_multiple_state_variables(self, vyper_harness):
        """Test goto definition with multiple state variables."""
        source = """# pragma version 0.3.10

balance: uint256
owner: address
name: String[100]

@external
def get_info() -> (uint256, address, String[100]):
    return (self.balance, self.owner, self.name)
"""
        vyper_harness.setup(source, word_at_pos="self.balance")
        vyper_harness.assert_definition_at(expected_line=2)

        vyper_harness.setup(source, word_at_pos="self.owner")
        vyper_harness.assert_definition_at(expected_line=3)

        vyper_harness.setup(source, word_at_pos="self.name")
        vyper_harness.assert_definition_at(expected_line=4)

    def test_public_variable(self, vyper_harness):
        """Test goto definition for public state variable."""
        source = """# pragma version 0.3.10

total_supply: public(uint256)

@external
def mint(amount: uint256):
    self.total_supply += amount
"""
        vyper_harness.setup(source, word_at_pos="self.total_supply")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_hashmap_variable(self, vyper_harness):
        """Test goto definition for HashMap variable."""
        source = """# pragma version 0.3.10

balances: HashMap[address, uint256]

@external
def get_balance(addr: address) -> uint256:
    return self.balances[addr]
"""
        vyper_harness.setup(source, word_at_pos="self.balances")
        vyper_harness.assert_definition_at(expected_line=2)

    # =========================================================================
    # Constants and Immutables
    # =========================================================================

    def test_constant_variable(self, vyper_harness):
        """Test goto definition for a constant variable."""
        source = """# pragma version 0.3.10

MAX_SUPPLY: constant(uint256) = 1000000

def get_max_supply() -> uint256:
    return MAX_SUPPLY
"""
        vyper_harness.setup(source, word_at_pos="MAX_SUPPLY")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_immutable_variable(self, vyper_harness):
        """Test goto definition for an immutable variable."""
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
        vyper_harness.assert_definition_at(expected_line=2)

    # =========================================================================
    # Functions
    # =========================================================================

    def test_function_reference(self, vyper_harness):
        """Test goto definition for a function reference."""
        source = """# pragma version 0.3.10


def bar():
    pass

@external
def foo():
    self.bar()
"""
        vyper_harness.setup(source, word_at_pos="self.bar")
        vyper_harness.assert_definition_at(expected_line=3)

    def test_multiple_functions(self, vyper_harness):
        """Test goto definition when multiple functions exist."""
        source = """# pragma version 0.3.10

def helper_one():
    pass

def helper_two():
    pass

@external
def main():
    self.helper_one()
    self.helper_two()
"""
        vyper_harness.setup(source, word_at_pos="self.helper_one")
        vyper_harness.assert_definition_at(expected_line=2)

        vyper_harness.setup(source, word_at_pos="self.helper_two")
        vyper_harness.assert_definition_at(expected_line=5)

    # =========================================================================
    # Structs
    # =========================================================================

    def test_struct_reference(self, vyper_harness):
        """Test goto definition for a struct reference."""
        source = """# pragma version 0.3.10

struct Person:
    name: String[100]
    age: uint256

def create_person() -> Person:
    return Person({name: "Alice", age: 30})
"""
        vyper_harness.setup(source, word_at_pos="Person")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_nested_struct(self, vyper_harness):
        """Test goto definition for nested struct types."""
        source = """# pragma version 0.4.0

struct Inner:
    value: uint256

struct Outer:
    inner: Inner
    count: uint256

@external
def create() -> Outer:
    i: Inner = Inner({value: 42})
    return Outer({inner: i, count: 1})
"""
        vyper_harness.setup(source, word_at_pos="Inner")
        vyper_harness.assert_definition_at(expected_line=2)

        vyper_harness.setup(source, word_at_pos="Outer")
        vyper_harness.assert_definition_at(expected_line=5)

    # =========================================================================
    # Events
    # =========================================================================

    def test_event_reference(self, vyper_harness):
        """Test goto definition for an event reference."""
        source = """# pragma version 0.4.0

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    amount: uint256

@external
def transfer(to: address, amount: uint256):
    log Transfer(msg.sender, to, amount)
"""
        vyper_harness.setup(source, word_at_pos="Transfer")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_event_with_indexed(self, vyper_harness):
        """Test goto definition for event with indexed parameters."""
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
        vyper_harness.assert_definition_at(expected_line=2)

    # =========================================================================
    # Flags
    # =========================================================================

    def test_flag_reference(self, vyper_harness):
        """Test goto definition for a flag reference."""
        source = """# pragma version 0.4.0

flag A:
    a

@external
def foo():
    x: A = A.a
"""
        vyper_harness.setup(source, word_at_pos="A")
        vyper_harness.assert_definition_at(expected_line=2)

    def test_flag_with_members(self, vyper_harness):
        """Test goto definition for flag with multiple members."""
        source = """# pragma version 0.4.0

flag Permissions:
    READ
    WRITE
    EXECUTE

@external
def check_permission(p: Permissions) -> bool:
    return p == Permissions.READ
"""
        vyper_harness.setup(source, word_at_pos="Permissions")
        vyper_harness.assert_definition_at(expected_line=2)

    # =========================================================================
    # Interfaces
    # =========================================================================

    def test_interface_reference(self, vyper_harness):
        """Test goto definition for an interface reference."""
        source = """# pragma version 0.4.0

interface IERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable
    def balanceOf(owner: address) -> uint256: view

@external
def check_balance(token: IERC20, owner: address) -> uint256:
    return token.balanceOf(owner)
"""
        vyper_harness.setup(source, word_at_pos="IERC20")
        vyper_harness.assert_definition_at(expected_line=2)

    # =========================================================================
    # Multiple Types in One Source
    # =========================================================================

    def test_multiple_types(self, vyper_harness):
        """Test goto definition for multiple different types."""
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
        vyper_harness.setup(source, word_at_pos="Transfer")
        vyper_harness.assert_definition_at(expected_line=2)

        vyper_harness.setup(source, word_at_pos="Token")
        vyper_harness.assert_definition_at(expected_line=7)

        vyper_harness.setup(source, word_at_pos="A")
        vyper_harness.assert_definition_at(expected_line=10)

    # =========================================================================
    # Negative Cases / Edge Cases
    # =========================================================================

    def test_not_found(self, vyper_harness):
        """Test goto definition when symbol is not found."""
        source = """# pragma version 0.3.10

def foo():
    pass
"""
        vyper_harness.setup(source, word_at_pos="nonexistent_symbol")
        vyper_harness.assert_no_definition()

        vyper_harness.setup(source, word_at_pos=None)
        vyper_harness.assert_no_definition()

        vyper_harness.setup(source, word_at_pos="")
        vyper_harness.assert_no_definition()

        vyper_harness.setup(source, word_at_pos="pass")
        vyper_harness.assert_no_definition()

    def test_index_error(
        self, mock_language_server, mock_text_document, mock_workspace
    ):
        """Test goto definition when word_at_position raises IndexError."""
        mock_text_document.uri = "file:///test.vy"
        mock_text_document.word_at_position.side_effect = IndexError("out of range")
        mock_workspace.get_text_document.return_value = mock_text_document
        mock_language_server.workspace = mock_workspace

        params = DefinitionParams(
            text_document=TextDocumentIdentifier(uri="file:///test.vy"),
            position=Position(line=100, character=100),
        )
        result = goto_definition(mock_language_server, params)
        assert result is None

    def test_local_var_does_not_resolve_to_state_var(self, vyper_harness):
        """Test that a local variable resolves to local definition, not state variable."""
        source = """# pragma version 0.4.0

a: uint256

@external
def foo():
    a: uint256 = 1
    b: uint256 = a
"""
        # When cursor is inside the function, 'a' should resolve to the LOCAL var (line 6)
        # not the state variable (line 2)
        vyper_harness.setup(source, word_at_pos="a")
        vyper_harness.assert_definition_at(
            expected_line=6, expected_char=4, cursor_line=7, cursor_char=17
        )

    def test_state_var_at_module_level_resolves(self, vyper_harness):
        """Test that state variable at module level resolves (self fallback enabled)."""
        source = """# pragma version 0.4.0

a: uint256
"""
        vyper_harness.setup(source, word_at_pos="a")
        vyper_harness.assert_definition_at(expected_line=2, cursor_line=2)

    def test_flag_member_does_not_resolve_to_constant(self, vyper_harness):
        """Test that flag member doesn't resolve to constant with same name."""
        source = """# pragma version 0.4.0

xs: constant(uint256) = 0

flag F:
    xs
"""
        vyper_harness.setup(source, word_at_pos="xs")
        vyper_harness.assert_no_definition(cursor_line=5, cursor_char=4)

    def test_event_field_does_not_resolve_to_constant(self, vyper_harness):
        """Test that event field doesn't resolve to constant with same name."""
        source = """# pragma version 0.4.0

value: constant(uint256) = 42

event Transfer:
    value: uint256
"""
        vyper_harness.setup(source, word_at_pos="value")
        vyper_harness.assert_no_definition(cursor_line=5, cursor_char=4)

    def test_struct_field_does_not_resolve_to_constant(self, vyper_harness):
        """Test that struct field doesn't resolve to constant with same name."""
        source = """# pragma version 0.4.0

amount: constant(uint256) = 100

struct Payment:
    amount: uint256
"""
        vyper_harness.setup(source, word_at_pos="amount")
        vyper_harness.assert_no_definition(cursor_line=5, cursor_char=4)

    # =========================================================================
    # Local Variables (Function Arguments, Loop Iterators, etc.)
    # =========================================================================

    def test_function_argument_definition(self, vyper_harness):
        """Test goto definition for a function argument."""
        source = """# pragma version 0.4.0

@external
def foo(amount: uint256):
    x: uint256 = amount
"""
        vyper_harness.setup(source, word_at_pos="amount")
        # 'amount' on line 4 should resolve to the function argument on line 3
        vyper_harness.assert_definition_at(
            expected_line=3, expected_char=8, cursor_line=4, cursor_char=17
        )

    def test_local_variable_definition(self, vyper_harness):
        """Test goto definition for a local variable declared in function body."""
        source = """# pragma version 0.4.0

@external
def foo():
    x: uint256 = 5
    y: uint256 = x + 1
"""
        vyper_harness.setup(source, word_at_pos="x")
        # 'x' on line 5 should resolve to the local var on line 4
        vyper_harness.assert_definition_at(
            expected_line=4, expected_char=4, cursor_line=5, cursor_char=17
        )

    def test_for_loop_iterator_definition(self, vyper_harness):
        """Test goto definition for a for loop iterator variable."""
        source = """# pragma version 0.4.0

@external
def foo():
    total: uint256 = 0
    for i: uint256 in range(10):
        total += i
"""
        vyper_harness.setup(source, word_at_pos="i")
        # 'i' on line 6 should resolve to the loop iterator on line 5
        vyper_harness.assert_definition_at(
            expected_line=5, expected_char=8, cursor_line=6, cursor_char=17
        )

    def test_multiple_function_arguments(self, vyper_harness):
        """Test goto definition with multiple function arguments."""
        source = """# pragma version 0.4.0

@external
def transfer(sender: address, receiver: address, amount: uint256):
    x: uint256 = amount
"""
        vyper_harness.setup(source, word_at_pos="amount")
        vyper_harness.assert_definition_at(
            expected_line=3, expected_char=49, cursor_line=4, cursor_char=17
        )

    def test_local_variable_shadows_state_variable(self, vyper_harness):
        """Test that local variable definition shadows state variable."""
        source = """# pragma version 0.4.0

counter: uint256

@external
def foo():
    counter: uint256 = 10
    x: uint256 = counter
"""
        vyper_harness.setup(source, word_at_pos="counter")
        # 'counter' on line 7 should resolve to the LOCAL var on line 6, not state var on line 2
        vyper_harness.assert_definition_at(
            expected_line=6, expected_char=4, cursor_line=7, cursor_char=17
        )
