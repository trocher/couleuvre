"""Tests for the completion feature."""

from typing import Any

import pytest
from lsprotocol.types import CompletionItemKind

from couleuvre.ast import nodes
from couleuvre.features.completion import (
    get_self_completions,
    _get_trigger_context,
    _is_internal_function,
)
from couleuvre.parser import parse_module


class MockTextDocument:
    """Mock TextDocument for testing."""

    def __init__(self, lines: list[str]):
        self.lines = lines


class TestGetTriggerContext:
    """Tests for _get_trigger_context function."""

    def test_self_dot(self):
        """Test detecting 'self.' trigger."""
        from lsprotocol.types import Position

        doc: Any = MockTextDocument(["    self."])
        pos = Position(line=0, character=9)
        assert _get_trigger_context(doc, pos) == "self"

    def test_module_dot(self):
        """Test detecting module trigger like 'MyModule.'."""
        from lsprotocol.types import Position

        doc: Any = MockTextDocument(["    result = MyModule."])
        pos = Position(line=0, character=22)
        assert _get_trigger_context(doc, pos) == "MyModule"

    def test_no_dot(self):
        """Test no trigger when no dot present."""
        from lsprotocol.types import Position

        doc: Any = MockTextDocument(["    x = 1"])
        pos = Position(line=0, character=9)
        assert _get_trigger_context(doc, pos) is None

    def test_middle_of_chain(self):
        """Test trigger in middle of attribute chain."""
        from lsprotocol.types import Position

        doc: Any = MockTextDocument(["    self.foo."])
        pos = Position(line=0, character=13)
        assert _get_trigger_context(doc, pos) == "foo"


class TestSelfCompletions:
    """Tests for get_self_completions function."""

    @pytest.fixture
    def module_with_vars_and_funcs(self, tmp_path):
        """Create a module with state variables and functions."""
        source = """
#pragma version ^0.4.0

# State variables (should appear)
counter: uint256
owner: address
data: DynArray[uint256, 10]

# Constants/immutables (should NOT appear)
MAX_VALUE: constant(uint256) = 100
DEPLOYER: immutable(address)

@deploy
def __init__():
    DEPLOYER = msg.sender

@internal
def _helper() -> uint256:
    return self.counter

@internal
def _calculate(x: uint256) -> uint256:
    return x * 2

@external
def increment():
    self.counter += 1

@view
@external
def get_counter() -> uint256:
    return self.counter
"""
        file_path = tmp_path / "test.vy"
        file_path.write_text(source)
        return parse_module(str(file_path))

    def test_includes_state_variables(self, module_with_vars_and_funcs):
        """Test that state variables are included."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "counter" in labels
        assert "owner" in labels
        assert "data" in labels

    def test_excludes_constants(self, module_with_vars_and_funcs):
        """Test that constants are excluded."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "MAX_VALUE" not in labels

    def test_excludes_immutables(self, module_with_vars_and_funcs):
        """Test that immutables are excluded."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "DEPLOYER" not in labels

    def test_includes_internal_functions(self, module_with_vars_and_funcs):
        """Test that internal functions are included."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "_helper" in labels
        assert "_calculate" in labels

    def test_excludes_external_functions(self, module_with_vars_and_funcs):
        """Test that external functions are excluded."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "increment" not in labels
        assert "get_counter" not in labels

    def test_excludes_dunder_methods(self, module_with_vars_and_funcs):
        """Test that __init__ and similar are excluded."""
        completions = get_self_completions(module_with_vars_and_funcs)
        labels = [c.label for c in completions]

        assert "__init__" not in labels

    def test_variable_completion_kind(self, module_with_vars_and_funcs):
        """Test that variables have correct completion kind."""
        completions = get_self_completions(module_with_vars_and_funcs)
        counter_comp = next(c for c in completions if c.label == "counter")

        assert counter_comp.kind == CompletionItemKind.Variable

    def test_function_completion_kind(self, module_with_vars_and_funcs):
        """Test that functions have correct completion kind."""
        completions = get_self_completions(module_with_vars_and_funcs)
        helper_comp = next(c for c in completions if c.label == "_helper")

        assert helper_comp.kind == CompletionItemKind.Function

    def test_function_has_snippet(self, module_with_vars_and_funcs):
        """Test that functions have snippet insert text."""
        from lsprotocol.types import InsertTextFormat

        completions = get_self_completions(module_with_vars_and_funcs)
        helper_comp = next(c for c in completions if c.label == "_helper")

        assert helper_comp.insert_text == "_helper($0)"
        assert helper_comp.insert_text_format == InsertTextFormat.Snippet


class TestIsInternalFunction:
    """Tests for _is_internal_function helper."""

    def test_internal_decorator(self, tmp_path):
        """Test function with @internal decorator."""
        source = """
#pragma version ^0.4.0

@internal
def _foo():
    pass
"""
        file_path = tmp_path / "test.vy"
        file_path.write_text(source)
        module = parse_module(str(file_path))

        func = list(module.functions)[0]
        assert isinstance(func, nodes.FunctionDef)
        assert _is_internal_function(func) is True

    def test_external_decorator(self, tmp_path):
        """Test function with @external decorator."""
        source = """
#pragma version ^0.4.0

@external
def foo():
    pass
"""
        file_path = tmp_path / "test.vy"
        file_path.write_text(source)
        module = parse_module(str(file_path))

        func = list(module.functions)[0]
        assert isinstance(func, nodes.FunctionDef)
        assert _is_internal_function(func) is False

    def test_view_external_decorator(self, tmp_path):
        """Test function with @view @external decorators."""
        source = """
#pragma version ^0.4.0

@view
@external
def foo() -> uint256:
    return 0
"""
        file_path = tmp_path / "test.vy"
        file_path.write_text(source)
        module = parse_module(str(file_path))

        func = list(module.functions)[0]
        assert isinstance(func, nodes.FunctionDef)
        assert _is_internal_function(func) is False

    def test_no_decorator(self, tmp_path):
        """Test function with no decorator is considered internal."""
        source = """
#pragma version ^0.4.0

def _helper():
    pass
"""
        file_path = tmp_path / "test.vy"
        file_path.write_text(source)
        module = parse_module(str(file_path))

        func = list(module.functions)[0]
        assert isinstance(func, nodes.FunctionDef)
        assert _is_internal_function(func) is True
