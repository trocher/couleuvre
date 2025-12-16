import json
import logging
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


def get_script(file_path: str, vyper_version: str, search_paths: list[str]) -> str:
    if Version(vyper_version) < Version("0.4.1"):
        content = Path(file_path).read_text()
        return dedent(
            f"""
            import json
            from vyper.compiler import CompilerData

            data = CompilerData({json.dumps(content)}).vyper_module
            print(json.dumps(data.to_dict()))
            """
        )

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
    path: str, vyper_version: str, workspace_path: Optional[str] = None
) -> Module:
    env = resolve_environment(vyper_version)
    search_paths = env.get_search_paths(include_sys_path=True)
    script = get_script(path, vyper_version, search_paths)

    result = env.run_script(script, cwd=workspace_path)

    if result.returncode != 0:
        error_message = result.stderr.strip() or "Unknown error"
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
