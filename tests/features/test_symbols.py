from couleuvre.features.symbols import get_document_symbols
from couleuvre.parser import Module, parse_module
from lsprotocol.types import SymbolKind
from pathlib import Path
import tempfile


def _flatten_symbols(symbols):
    """Helper function to flatten symbol hierarchy into a single list"""
    flattened = []
    for symbol in symbols:
        flattened.append(symbol)
        if hasattr(symbol, "children") and symbol.children:
            flattened.extend(_flatten_symbols(symbol.children))
    return flattened


def _create_symbol_map(symbols):
    """Helper function to create a name->kind mapping from symbols"""
    flattened = _flatten_symbols(symbols)
    return {symbol.name: symbol.kind for symbol in flattened}


def _parse_src(source: str) -> Module:
    with tempfile.NamedTemporaryFile(suffix=".vy", mode="w") as f:
        f.write(source)
        f.flush()
        return parse_module(f.name)


def test_symbols_real_contract():
    path = Path("examples/CurveTwocrypto.vy")
    symbols = get_document_symbols(parse_module(str(path)))
    assert len(symbols) == 128
    flattened = _flatten_symbols(symbols)
    # Note: 446 includes local variables (function arguments, loop iterators, etc.)
    # The old count of 317 did not include local variables
    assert len(flattened) == 446


def test_symbols_constructor():
    source = """
# pragma version 0.4.0
def foo():
    pass
@deploy
def __init__():
    im = 1
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    # TODO should it be fixed ?
    # assert symbol_map["__init__"] == SymbolKind.Constructor
    assert symbol_map["foo"] == SymbolKind.Function


def test_symbols_constant_immutables():
    source = """
# pragma version 0.4.0
a:uint256
x:constant(uint256) = 3
i:immutable(uint256)
@deploy
def __init__():
    im = 1
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["x"] == SymbolKind.Constant
    assert symbol_map["i"] == SymbolKind.Constant
    assert symbol_map["a"] == SymbolKind.Variable


def test_symbols_interfaces():
    source = """
# pragma version 0.4.0

interface ERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable
    def balanceOf(account: address) -> uint256: view

interface IERC721:
    def ownerOf(tokenId: uint256) -> address: view
    def safeTransferFrom(from_: address, to: address, tokenId: uint256): nonpayable
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["ERC20"] == SymbolKind.Interface
    assert symbol_map["IERC721"] == SymbolKind.Interface
    assert symbol_map["transfer"] == SymbolKind.Method
    assert symbol_map["balanceOf"] == SymbolKind.Method
    assert symbol_map["ownerOf"] == SymbolKind.Method
    assert symbol_map["safeTransferFrom"] == SymbolKind.Method


def test_symbols_events():
    source = """
# pragma version 0.4.0

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256

event CustomEvent:
    data: bytes32
    timestamp: uint256
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["Transfer"] == SymbolKind.Event
    assert symbol_map["Approval"] == SymbolKind.Event
    assert symbol_map["CustomEvent"] == SymbolKind.Event
    # Event parameters should be fields (children of events)
    assert symbol_map["sender"] == SymbolKind.Field
    assert symbol_map["receiver"] == SymbolKind.Field
    assert symbol_map["value"] == SymbolKind.Field
    assert symbol_map["owner"] == SymbolKind.Field
    assert symbol_map["spender"] == SymbolKind.Field
    assert symbol_map["data"] == SymbolKind.Field
    assert symbol_map["timestamp"] == SymbolKind.Field


def test_symbols_enums():
    source = """
# pragma version 0.4.0

enum Status:
    PENDING
    APPROVED
    REJECTED

enum Priority:
    LOW
    MEDIUM
    HIGH
    CRITICAL
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["Status"] == SymbolKind.Enum
    assert symbol_map["Priority"] == SymbolKind.Enum
    assert symbol_map["PENDING"] == SymbolKind.EnumMember
    assert symbol_map["APPROVED"] == SymbolKind.EnumMember
    assert symbol_map["REJECTED"] == SymbolKind.EnumMember
    assert symbol_map["LOW"] == SymbolKind.EnumMember
    assert symbol_map["MEDIUM"] == SymbolKind.EnumMember
    assert symbol_map["HIGH"] == SymbolKind.EnumMember
    assert symbol_map["CRITICAL"] == SymbolKind.EnumMember


def test_symbols_structs():
    source = """
# pragma version 0.4.0

struct Person:
    name: String[50]
    age: uint256
    active: bool

struct Token:
    symbol: String[10]
    decimals: uint8
    total_supply: uint256
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["Person"] == SymbolKind.Struct
    assert symbol_map["Token"] == SymbolKind.Struct
    assert symbol_map["name"] == SymbolKind.Field
    assert symbol_map["age"] == SymbolKind.Field
    assert symbol_map["active"] == SymbolKind.Field
    assert symbol_map["symbol"] == SymbolKind.Field
    assert symbol_map["decimals"] == SymbolKind.Field
    assert symbol_map["total_supply"] == SymbolKind.Field


def test_symbols_function_decorators():
    source = """
# pragma version 0.4.0

@external
def external_func():
    pass

@internal
def internal_func():
    pass

@external
@view
def view_func() -> uint256:
    return 42

@external
@pure
def pure_func(x: uint256) -> uint256:
    return x * 2

@external
@payable
def payable_func():
    pass

@external
@nonreentrant
def nonreentrant_func():
    pass
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["external_func"] == SymbolKind.Function
    assert symbol_map["internal_func"] == SymbolKind.Function
    assert symbol_map["view_func"] == SymbolKind.Function
    assert symbol_map["pure_func"] == SymbolKind.Function
    assert symbol_map["payable_func"] == SymbolKind.Function
    assert symbol_map["nonreentrant_func"] == SymbolKind.Function


def test_symbols_variables_complex():
    source = """
# pragma version 0.4.0

# State variables
owner: public(address)
balances: public(HashMap[address, uint256])
allowances: HashMap[address, HashMap[address, uint256]]
total_supply: uint256

# Constants with different types
MAX_SUPPLY: constant(uint256) = 1000000
CONTRACT_NAME: constant(String[32]) = "MyToken"
DECIMALS: constant(uint8) = 18
ZERO_ADDRESS: constant(address) = 0x0000000000000000000000000000000000000000

# Immutables
deployer: immutable(address)
creation_time: immutable(uint256)
initial_rate: immutable(uint256)
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)

    # State variables
    assert symbol_map["owner"] == SymbolKind.Variable
    assert symbol_map["balances"] == SymbolKind.Variable
    assert symbol_map["allowances"] == SymbolKind.Variable
    assert symbol_map["total_supply"] == SymbolKind.Variable

    # Constants
    assert symbol_map["MAX_SUPPLY"] == SymbolKind.Constant
    assert symbol_map["CONTRACT_NAME"] == SymbolKind.Constant
    assert symbol_map["DECIMALS"] == SymbolKind.Constant
    assert symbol_map["ZERO_ADDRESS"] == SymbolKind.Constant

    # Immutables
    assert symbol_map["deployer"] == SymbolKind.Constant
    assert symbol_map["creation_time"] == SymbolKind.Constant
    assert symbol_map["initial_rate"] == SymbolKind.Constant


def test_symbols_mixed_complex():
    source = """
# pragma version 0.4.0

# Interfaces
interface IERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable

# Events
event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    amount: uint256

# Enums
enum TokenType:
    STANDARD
    DEFLATIONARY
    REBASE

# Structs
struct UserInfo:
    balance: uint256
    last_update: uint256
    token_type: TokenType

# Constants and immutables
PRECISION: constant(uint256) = 10**18
factory: immutable(address)

# State variables
users: HashMap[address, UserInfo]
token_count: uint256

# Functions
@deploy
def __init__(_factory: address):
    factory = _factory

@external
def get_user_info(user: address) -> UserInfo:
    return self.users[user]

@internal
def _update_user(user: address, amount: uint256):
    self.users[user].balance = amount
    self.users[user].last_update = block.timestamp
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)

    # Check all symbol types are present
    assert symbol_map["IERC20"] == SymbolKind.Interface
    assert symbol_map["transfer"] == SymbolKind.Method
    assert symbol_map["Transfer"] == SymbolKind.Event
    assert symbol_map["TokenType"] == SymbolKind.Enum
    assert symbol_map["STANDARD"] == SymbolKind.EnumMember
    assert symbol_map["UserInfo"] == SymbolKind.Struct
    assert symbol_map["balance"] == SymbolKind.Field
    assert symbol_map["PRECISION"] == SymbolKind.Constant
    assert symbol_map["factory"] == SymbolKind.Constant
    assert symbol_map["users"] == SymbolKind.Variable
    assert symbol_map["__init__"] == SymbolKind.Function
    assert symbol_map["get_user_info"] == SymbolKind.Function
    assert symbol_map["_update_user"] == SymbolKind.Function


def test_symbols_empty_file():
    source = """
# pragma version 0.4.0
    """
    symbols = get_document_symbols(_parse_src(source))
    assert len(symbols) == 0


def test_symbols_only_comments():
    source = """
# pragma version 0.4.0
# This is a comment
# Another comment
    """
    symbols = get_document_symbols(_parse_src(source))
    assert len(symbols) == 0


def test_symbols_pragma_only():
    source = """
# pragma version 0.4.0
# pragma optimize gas
# pragma evm-version paris
    """
    symbols = get_document_symbols(_parse_src(source))
    assert len(symbols) == 0


def test_symbols_function_parameters():
    source = """
# pragma version 0.4.0

@external
def complex_function(
    user: address,
    amount: uint256,
    data: bytes32,
    recipients: DynArray[address, 10]
) -> (uint256, bool):
    return amount, True

@internal
def _helper(x: uint256, y: uint256) -> uint256:
    return x + y
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["complex_function"] == SymbolKind.Function
    assert symbol_map["_helper"] == SymbolKind.Function
    # Parameters should be included as variables within the function scope
    # Note: This depends on implementation details of the symbol visitor


def test_symbols_nested_structures():
    source = """
# pragma version 0.4.0

struct Address:
    street: String[100]
    city: String[50]
    country: String[50]

struct Person:
    name: String[50]
    age: uint256
    address: Address

struct Company:
    name: String[100]
    employees: DynArray[Person, 1000]
    headquarters: Address
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["Address"] == SymbolKind.Struct
    assert symbol_map["Person"] == SymbolKind.Struct
    assert symbol_map["Company"] == SymbolKind.Struct
    assert symbol_map["street"] == SymbolKind.Field
    assert symbol_map["name"] == SymbolKind.Field
    assert symbol_map["employees"] == SymbolKind.Field
    assert symbol_map["headquarters"] == SymbolKind.Field


def test_symbols_implements():
    source = """
# pragma version 0.4.0

interface IERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable

implements: IERC20

@external
def transfer(to: address, amount: uint256) -> bool:
    return True
    """
    symbols = get_document_symbols(_parse_src(source))

    symbol_map = _create_symbol_map(symbols)
    assert symbol_map["IERC20"] == SymbolKind.Interface
    assert symbol_map["transfer"] == SymbolKind.Function
    sub_map = _create_symbol_map(
        [symbol for symbol in symbols if symbol.kind == SymbolKind.Interface]
    )
    assert sub_map["transfer"] == SymbolKind.Method


def test_symbols_count_verification():
    """Test that symbol counts match expected values for complex contracts"""
    source = """
# pragma version 0.4.0

# 3 constants
MAX_USERS: constant(uint256) = 1000
MIN_AMOUNT: constant(uint256) = 100
CONTRACT_VERSION: constant(String[10]) = "1.0.0"

# 2 immutables
owner: immutable(address)
deployed_at: immutable(uint256)

# 3 state variables
user_count: uint256
total_balance: uint256
is_paused: bool

# 1 enum with 3 members
enum Status:
    ACTIVE
    PAUSED
    TERMINATED

# 1 struct with 2 fields
struct User:
    balance: uint256
    status: Status

# 1 event with 2 fields
event UserUpdated:
    user: indexed(address)
    new_balance: uint256

# 1 interface with 1 method
interface IHelper:
    def help() -> bool: view

# 4 functions
@deploy
def __init__(_owner: address):
    owner = _owner

@external
def update_user(amount: uint256):
    pass

@external
@view
def get_status() -> Status:
    return Status.ACTIVE

@internal
def _validate():
    pass
    """
    symbols = get_document_symbols(_parse_src(source))
    flattened = _flatten_symbols(symbols)

    # Count symbols by type
    symbol_counts = {}
    for symbol in flattened:
        kind = symbol.kind
        symbol_counts[kind] = symbol_counts.get(kind, 0) + 1

    # Verify expected counts
    assert symbol_counts.get(SymbolKind.Constant, 0) == 5  # 3 constants + 2 immutables
    assert (
        symbol_counts.get(SymbolKind.Variable, 0) == 5
    )  # 3 state variables + 2 func arguments
    assert symbol_counts.get(SymbolKind.Enum, 0) == 1
    assert symbol_counts.get(SymbolKind.EnumMember, 0) == 3
    assert symbol_counts.get(SymbolKind.Struct, 0) == 1
    assert (
        symbol_counts.get(SymbolKind.Field, 0) == 4
    )  # 2 struct fields + 2 event fields
    assert symbol_counts.get(SymbolKind.Event, 0) == 1
    assert symbol_counts.get(SymbolKind.Interface, 0) == 1
    assert symbol_counts.get(SymbolKind.Method, 0) == 1  # interface method
    assert symbol_counts.get(SymbolKind.Function, 0) == 4  # 4 functions

    # Total should be 23 symbols
    assert len(flattened) == 26


def test_symbols_hierarchy_structure():
    """Test that symbols are properly hierarchical with children"""
    source = """
# pragma version 0.4.0

interface IERC20:
    def transfer(to: address, amount: uint256) -> bool: nonpayable
    def balanceOf(account: address) -> uint256: view

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

enum Status:
    ACTIVE
    PAUSED

struct User:
    balance: uint256
    status: Status
    """
    symbols = get_document_symbols(_parse_src(source))

    # Find specific parent symbols
    interface_symbol = next(s for s in symbols if s.name == "IERC20")
    event_symbol = next(s for s in symbols if s.name == "Transfer")
    enum_symbol = next(s for s in symbols if s.name == "Status")
    struct_symbol = next(s for s in symbols if s.name == "User")

    # Verify interface has method children
    assert interface_symbol.kind == SymbolKind.Interface

    children = interface_symbol.children or []
    assert len(children) == 2
    interface_methods = {child.name: child.kind for child in children}
    assert interface_methods["transfer"] == SymbolKind.Method
    assert interface_methods["balanceOf"] == SymbolKind.Method

    # Verify event has field children
    assert event_symbol.kind == SymbolKind.Event
    children = event_symbol.children or []
    assert len(children) == 3
    event_fields = {child.name: child.kind for child in children}
    assert event_fields["sender"] == SymbolKind.Field
    assert event_fields["receiver"] == SymbolKind.Field
    assert event_fields["value"] == SymbolKind.Field

    # Verify enum has member children
    assert enum_symbol.kind == SymbolKind.Enum
    children = enum_symbol.children or []
    assert len(children) == 2
    enum_members = {child.name: child.kind for child in children}
    assert enum_members["ACTIVE"] == SymbolKind.EnumMember
    assert enum_members["PAUSED"] == SymbolKind.EnumMember

    # Verify struct has field children
    assert struct_symbol.kind == SymbolKind.Struct
    children = struct_symbol.children or []
    assert len(children) == 2
    struct_fields = {child.name: child.kind for child in children}
    assert struct_fields["balance"] == SymbolKind.Field
    assert struct_fields["status"] == SymbolKind.Field
