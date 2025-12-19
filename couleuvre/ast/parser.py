import json
import logging
import tempfile
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Optional

from packaging.version import Version

from couleuvre.ast.environment import resolve_environment
from couleuvre.ast.nodes import AST_CLASS_MAP, BaseNode, Module

logger = logging.getLogger("couleuvre")

_AST_TYPE_ALIASES = {
    "List": "ListNode",
    "Tuple": "TupleNode",
    "Dict": "DictNode",
    "EnumDef": "FlagDef",
}


def get_script(
    file_path: str,
    vyper_version: str,
    search_paths: list[str],
    source: Optional[str] = None,
) -> str:
    if Version(vyper_version) < Version("0.4.1"):
        # For older versions, we can pass source directly to CompilerData
        if source is None:
            source = Path(file_path).read_text()
        return dedent(
            f"""
            import json
            from vyper.compiler import CompilerData

            data = CompilerData({json.dumps(source)}).vyper_module
            print(json.dumps(data.to_dict()))
            """
        )

    # For version >= 0.4.1, we need to use FilesystemInputBundle which reads from disk.
    # If source is provided, we'll write it to a temp file and use that path.
    return dedent(
        f"""
        import json
        from pathlib import Path
        from vyper.compiler import CompilerData
        from vyper.compiler.input_bundle import FilesystemInputBundle
        from vyper.semantics.analysis.imports import resolve_imports

        search_paths = [Path(p) for p in {json.dumps(search_paths)}]
        input_bundle = FilesystemInputBundle(search_paths)
        file = input_bundle.load_file({json.dumps(file_path)})
        module = CompilerData(file, input_bundle).vyper_module
        try:
            with input_bundle.search_path(Path(module.resolved_path).parent):
                resolve_imports(module, input_bundle)
        except Exception:
            pass
        print(json.dumps(module.to_dict()))
        """
    )


def get_json_ast(
    path: str,
    vyper_version: str,
    workspace_path: Optional[str] = None,
    source: Optional[str] = None,
) -> Module:
    env = resolve_environment(vyper_version)
    search_paths = env.get_search_paths(include_sys_path=True)

    # For Vyper >= 0.4.1 with unsaved buffer, write to a temp file
    # so FilesystemInputBundle can read it
    temp_file = None
    effective_path = path
    if source is not None and Version(vyper_version) >= Version("0.4.1"):
        # Create temp file with same extension to preserve file type detection
        suffix = Path(path).suffix or ".vy"
        temp_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, delete=False, dir=Path(path).parent
        )
        temp_file.write(source)
        temp_file.close()
        effective_path = temp_file.name

    try:
        script = get_script(effective_path, vyper_version, search_paths, source)
        result = env.run_script(script, cwd=workspace_path)
    finally:
        # Clean up temp file if we created one
        if temp_file is not None:
            try:
                Path(temp_file.name).unlink()
            except OSError:
                pass

    if result.returncode != 0:
        error_message = result.stderr.strip() or "Unknown error"
        # Replace temp file name with original path in error messages
        if temp_file is not None:
            temp_name = Path(temp_file.name).name
            error_message = error_message.replace(temp_name, Path(path).name)
        logger.error(
            "Failed to get AST for Vyper %s: subprocess error: %s",
            vyper_version,
            error_message,
        )
        raise RuntimeError(error_message)

    logger.info("Got Vyper AST from Vyper %s", vyper_version)

    try:
        parsed_json = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse AST output for Vyper %s: %s", vyper_version, exc)
        raise
    lsp_ast = _from_vyper_json_ast(parsed_json)
    if not isinstance(lsp_ast, Module):
        raise TypeError("Expected AST root to be a Module node")
    logger.info("Parsed Vyper AST to LSP AST")
    return lsp_ast


# === Converter ===


def _from_vyper_json_ast(
    ast_dict: Dict[str, Any], parent: Optional[BaseNode] = None
) -> BaseNode:
    def _convert_child(value: Any) -> Any:
        if isinstance(value, list):
            return [_convert_child(item) for item in value]
        if isinstance(value, dict) and "ast_type" in value:
            return _from_vyper_json_ast(value)
        return value

    ast_type = _AST_TYPE_ALIASES.get(ast_dict["ast_type"])
    if ast_type is None:
        ast_type = ast_dict["ast_type"]
    cls = AST_CLASS_MAP.get(ast_type, BaseNode)
    cls_fields = cls.__dataclass_fields__

    kwargs = {"ast_type": ast_type}

    for key, value in ast_dict.items():
        if key not in cls_fields:
            logger.error(
                f"Key '{str(key)}' not found in {str(cls.__name__)} dataclass fields"
            )
            continue
        kwargs[key] = _convert_child(value)
    # TODO sus type ignore
    node = cls(**kwargs)  # type: ignore
    node.parent = parent

    # Now update children with the correct parent reference
    for key, value in kwargs.items():
        if isinstance(value, BaseNode):
            value.parent = node
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, BaseNode):
                    item.parent = node

    return node
