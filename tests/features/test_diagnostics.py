"""Tests for the diagnostics module."""

from lsprotocol.types import DiagnosticSeverity

from couleuvre.features.diagnostics import (
    parse_error_location,
    _parse_error_type,
    _get_severity,
)


class TestParseErrorLocation:
    """Tests for parse_error_location function."""

    def test_line_colon_column(self):
        """Test parsing 'line X:Y' format (Vyper's actual format)."""
        line, col = parse_error_location('function "foo", line 10:5')
        assert line == 9  # 0-based
        assert col == 5

    def test_line_column_in_context(self):
        """Test parsing with full Vyper error context."""
        message = """Expected uint256 but literal can only be cast as String[5].

  function "foo", line 6:17
       5 def foo():
  ---> 6     y: uint256 = "hello"
"""
        line, col = parse_error_location(message)
        assert line == 5  # 0-based (line 6 -> 5)
        assert col == 17

    def test_no_location(self):
        """Test parsing when no location is present."""
        line, col = parse_error_location("Some error without location")
        assert line == 0
        assert col == 0

    def test_undeclared_var_format(self):
        """Test parsing undeclared variable error format."""
        message = "'x' has not been declared.\n\n  function \"foo\", line 5:4"
        line, col = parse_error_location(message)
        assert line == 4  # 0-based (line 5 -> 4)
        assert col == 4


class TestParseErrorType:
    """Tests for _parse_error_type function."""

    def test_vyper_exception(self):
        """Test extracting Vyper exception type."""
        traceback = "vyper.exceptions.TypeMismatch: expected uint256"
        assert _parse_error_type(traceback) == "TypeMismatch"

    def test_undeclared_definition(self):
        """Test extracting UndeclaredDefinition."""
        traceback = "vyper.exceptions.UndeclaredDefinition: 'foo' is not defined"
        assert _parse_error_type(traceback) == "UndeclaredDefinition"

    def test_no_exception(self):
        """Test when no Vyper exception is found."""
        traceback = "Some generic error"
        assert _parse_error_type(traceback) is None


class TestGetSeverity:
    """Tests for _get_severity function."""

    def test_error_types(self):
        """Test that most types are errors."""
        assert _get_severity("TypeMismatch") == DiagnosticSeverity.Error
        assert _get_severity("UndeclaredDefinition") == DiagnosticSeverity.Error
        assert _get_severity(None) == DiagnosticSeverity.Error

    def test_warning_types(self):
        """Test that certain types are warnings."""
        assert _get_severity("DeprecationWarning") == DiagnosticSeverity.Warning
        assert _get_severity("SyntaxWarning") == DiagnosticSeverity.Warning
