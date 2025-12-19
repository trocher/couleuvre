"""
Full compilation diagnostics for the Vyper Language Server.

This module provides functionality to run Vyper semantic analysis
and extract diagnostics (errors, warnings) for the editor.

Unlike AST parsing (which stops early), semantic analysis catches:
- Type errors
- Semantic errors
- Import resolution errors
- Undeclared definitions
- And more...

For Vyper >= 0.4.0, we stop at the "annotated AST" step which runs
semantic analysis without generating bytecode (faster).
For older versions, we run full compilation.
"""

import json
import logging
import re
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import List, Optional, Tuple

from lsprotocol import types
from packaging.version import Version

from couleuvre.ast.environment import resolve_environment

logger = logging.getLogger("couleuvre")

# Pattern to extract line/column from Vyper error messages
# Vyper format: "line 6:17" (line:column)
_ERROR_LOCATION_PATTERN = re.compile(r"line\s+(\d+):(\d+)")

# Pattern to extract the error type (e.g., "TypeMismatch", "UndeclaredDefinition")
_ERROR_TYPE_PATTERN = re.compile(r"vyper\.exceptions\.(\w+)")


def _get_compile_script(
    file_path: str,
    vyper_version: str,
    search_paths: list[str],
    source: Optional[str] = None,
) -> str:
    """
    Generate a Python script that performs full Vyper compilation.

    This runs the complete compilation pipeline, not just AST extraction.
    """
    if Version(vyper_version) < Version("0.4.0"):
        # For older versions, pass source directly
        if source is None:
            source = Path(file_path).read_text()
        return dedent(
            f"""
            import json
            import sys
            import traceback

            try:
                from vyper import compile_code
                # Full compilation - will raise on any error
                compile_code({json.dumps(source)})
                print(json.dumps({{"success": True}}))
            except Exception as e:
                error_info = {{
                    "success": False,
                    "error_type": type(e).__name__,
                    "message": str(e),
                    "traceback": traceback.format_exc()
                }}
                # Try to extract location from annotations (Vyper AST nodes)
                if hasattr(e, 'annotations') and e.annotations:
                    node = e.annotations[0]
                    if hasattr(node, 'lineno'):
                        error_info["lineno"] = node.lineno
                        error_info["col_offset"] = getattr(node, 'col_offset', 0)
                        error_info["end_lineno"] = getattr(node, 'end_lineno', node.lineno)
                        error_info["end_col_offset"] = getattr(node, 'end_col_offset', error_info["col_offset"] + 1)
                print(json.dumps(error_info))
            """
        )

    # For version >= 0.4.0, use FilesystemInputBundle and stop at annotated AST
    # This runs semantic analysis (type checking) without full bytecode generation
    return dedent(
        f"""
        import json
        import sys
        import traceback
        from pathlib import Path

        try:
            from vyper.compiler import CompilerData
            from vyper.compiler.input_bundle import FilesystemInputBundle

            search_paths = [Path(p) for p in {json.dumps(search_paths)}]
            input_bundle = FilesystemInputBundle(search_paths)

            # Load file through input bundle
            file = input_bundle.load_file({json.dumps(file_path)})

            # Create CompilerData and run semantic analysis up to annotated AST
            # This catches type errors without generating bytecode
            compiler_data = CompilerData(file, input_bundle)

            # Accessing annotated_vyper_module triggers semantic analysis
            # This is faster than full compilation but still catches type errors
            _ = compiler_data.annotated_vyper_module

            print(json.dumps({{"success": True}}))
        except Exception as e:
            error_info = {{
                "success": False,
                "error_type": type(e).__name__,
                "message": str(e),
                "traceback": traceback.format_exc()
            }}
            # Try to extract location from annotations (Vyper AST nodes)
            if hasattr(e, 'annotations') and e.annotations:
                node = e.annotations[0]
                if hasattr(node, 'lineno'):
                    error_info["lineno"] = node.lineno
                    error_info["col_offset"] = getattr(node, 'col_offset', 0)
                    error_info["end_lineno"] = getattr(node, 'end_lineno', node.lineno)
                    error_info["end_col_offset"] = getattr(node, 'end_col_offset', error_info["col_offset"] + 1)
            print(json.dumps(error_info))
        """
    )


def parse_error_location(message: str) -> Tuple[int, int]:
    """
    Extract line and column from a Vyper error message.

    Vyper format: "line 6:17" where 6 is line (1-based), 17 is column (0-based).

    Returns (line, column) as 0-based indices for LSP.
    Defaults to (0, 0) if no location found.
    """
    match = _ERROR_LOCATION_PATTERN.search(message)
    if match:
        line = int(match.group(1)) - 1  # Convert to 0-based
        col = int(match.group(2))  # Already 0-based in Vyper
        return max(0, line), max(0, col)
    return 0, 0


def _parse_error_type(traceback_str: str) -> Optional[str]:
    """Extract the Vyper exception type from a traceback."""
    match = _ERROR_TYPE_PATTERN.search(traceback_str)
    if match:
        return match.group(1)
    return None


def _get_severity(error_type: Optional[str]) -> types.DiagnosticSeverity:
    """Map Vyper error types to LSP diagnostic severities."""
    # Most Vyper errors are actual errors
    # Could add warnings for deprecation notices, etc.
    warning_types = {"DeprecationWarning", "SyntaxWarning"}
    if error_type in warning_types:
        return types.DiagnosticSeverity.Warning
    return types.DiagnosticSeverity.Error


def create_diagnostic(
    message: str,
    start_line: int,
    start_col: int,
    end_line: Optional[int] = None,
    end_col: Optional[int] = None,
    severity: types.DiagnosticSeverity = types.DiagnosticSeverity.Error,
    source: str = "vyper",
) -> types.Diagnostic:
    """
    Create an LSP Diagnostic object.

    Args:
        message: The diagnostic message.
        start_line: 0-based starting line.
        start_col: 0-based starting column.
        end_line: 0-based ending line (defaults to start_line).
        end_col: 0-based ending column (defaults to start_col + 1).
        severity: The diagnostic severity.
        source: The source of the diagnostic (e.g., "vyper", "couleuvre").

    Returns:
        An LSP Diagnostic object.
    """
    if end_line is None:
        end_line = start_line
    if end_col is None:
        end_col = start_col + 1

    return types.Diagnostic(
        range=types.Range(
            start=types.Position(line=start_line, character=start_col),
            end=types.Position(line=end_line, character=end_col),
        ),
        message=message,
        severity=severity,
        source=source,
    )


def compile_and_get_diagnostics(
    path: str,
    vyper_version: str,
    workspace_path: Optional[str] = None,
    source: Optional[str] = None,
) -> List[types.Diagnostic]:
    """
    Run full Vyper compilation and extract diagnostics.

    Args:
        path: Path to the Vyper source file.
        vyper_version: The Vyper version to use.
        workspace_path: Root path for resolving relative imports.
        source: Optional source content (for unsaved buffers).

    Returns:
        List of LSP Diagnostic objects.
    """
    env = resolve_environment(vyper_version)
    search_paths = env.get_search_paths(include_sys_path=True)

    # For Vyper >= 0.4.0 with unsaved buffer, write to a temp file
    temp_file = None
    effective_path = path
    if source is not None and Version(vyper_version) >= Version("0.4.0"):
        suffix = Path(path).suffix or ".vy"
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, dir=Path(path).parent
        )
        temp_file.write(source)
        temp_file.close()
        effective_path = temp_file.name

    try:
        script = _get_compile_script(
            effective_path, vyper_version, search_paths, source
        )
        result = env.run_script(script, cwd=workspace_path)
    finally:
        # Clean up temp file
        if temp_file is not None:
            try:
                Path(temp_file.name).unlink()
            except OSError:
                pass

    # Parse the JSON result
    diagnostics: List[types.Diagnostic] = []
    temp_name = Path(temp_file.name).name if temp_file else None
    original_name = Path(path).name

    def sanitize_message(msg: str) -> str:
        """Replace temp file name with original file name in messages."""
        if temp_name:
            return msg.replace(temp_name, original_name)
        return msg

    try:
        output = json.loads(result.stdout)
    except json.JSONDecodeError:
        # If we can't parse JSON, check stderr for errors
        if result.stderr:
            error_message = sanitize_message(result.stderr.strip())
            line, col = parse_error_location(error_message)
            diagnostics.append(create_diagnostic(error_message, line, col))
        return diagnostics

    if output.get("success"):
        # No errors - return empty diagnostics
        return []

    # Extract error information
    error_type = output.get("error_type")
    message = sanitize_message(output.get("message", "Unknown compilation error"))
    traceback_str = sanitize_message(output.get("traceback", ""))

    # Try to get more specific error type from traceback
    if not error_type or error_type == "Exception":
        parsed_type = _parse_error_type(traceback_str)
        if parsed_type:
            error_type = parsed_type

    # Extract location - prefer structured data from Vyper AST nodes
    if "lineno" in output:
        # Use precise location from Vyper exception annotations
        start_line = output["lineno"] - 1  # Convert to 0-based
        start_col = output.get("col_offset", 0)
        end_line = output.get("end_lineno", output["lineno"]) - 1
        end_col = output.get("end_col_offset", start_col + 1)
    else:
        # Fallback to parsing error message
        start_line, start_col = parse_error_location(message)
        if start_line == 0 and start_col == 0:
            start_line, start_col = parse_error_location(traceback_str)
        end_line = start_line
        end_col = start_col + 1

    severity = _get_severity(error_type)

    # Format the message nicely
    formatted_message = f"[{error_type}] {message}" if error_type else message

    diagnostics.append(
        create_diagnostic(
            message=formatted_message,
            start_line=start_line,
            start_col=start_col,
            end_line=end_line,
            end_col=end_col,
            severity=severity,
        )
    )

    return diagnostics
