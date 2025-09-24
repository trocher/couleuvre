import os
from pathlib import Path
import subprocess
import json
import sys
from couleuvre.ast_parser.vyper_wrapper import ensure_vyper_version
from couleuvre.ast_parser.vyper_ast import BaseNode, AST_CLASS_MAP
import logging
from typing import Any, Dict, Optional
from packaging.version import Version
from couleuvre import utils  # <--- added

logger = logging.getLogger("vyper-lsp")


def _obtain_sys_path(python_bin) -> list[str]:
    """
    Obtain all the system paths in which the compiler would
    normally look for modules. This allows to lint vyper files
    that import a module that is installed as a virtual environment
    dependency.
    """

    command = [python_bin, "-c", "import sys; print(sys.path)"]

    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    stdout, stderr = process.communicate()

    paths = stdout.strip().strip("[]").replace("'", "").split(", ")
    return paths


def get_search_paths(
    python_bin: Optional[str] = None,
    include_sys_path: bool = True,
) -> list[str]:
    """
    Build the search path list passed to Vyper's FilesystemInputBundle.

    - If include_sys_path is False, return an empty list (no search paths).
    - If include_sys_path is True, obtain sys.path from the provided python_bin
      (intended for the couleuvre-managed env) and include "." for workspace resolution.
    """
    search_paths: list[str] = []

    if include_sys_path and python_bin:
        search_paths = _obtain_sys_path(python_bin)
        if "." not in search_paths:
            search_paths.append(".")

    logger.info(f"Final search paths: {search_paths}")
    return search_paths


def get_script(file_path: str, vyper_version: str, search_paths: list[str]) -> str:
    if Version(vyper_version) >= Version("0.4.1"):
        pass
        return f"""
import copy
import json
from vyper.semantics.analysis.imports import resolve_imports
from packaging.version import Version
from pathlib import Path
from vyper.compiler import CompilerData
from vyper.compiler.input_bundle import FilesystemInputBundle
search_paths = {repr(search_paths)}
search_paths = [Path(p) for p in search_paths]
input_bundle = FilesystemInputBundle(search_paths)
file = input_bundle.load_file({repr(file_path)})
module = CompilerData(file, input_bundle).vyper_module
with input_bundle.search_path(Path(module.resolved_path).parent):
    imports = resolve_imports(module, input_bundle)

print(json.dumps(module.to_dict()))
"""
    else:
        content = Path(file_path).read_text()
        return f"""
import json
from vyper.compiler import CompilerData
data = CompilerData({repr(content)}).vyper_module
print(json.dumps(data.to_dict()))
"""


def get_json_ast(
    path: str, vyper_version: str, workspace_path: Optional[str] = None
) -> BaseNode:
    # Decide which Python to use:
    use_local_env = False
    try:
        use_local_env = utils.get_installed_vyper_version() == Version(vyper_version)
    except Exception:
        use_local_env = False

    if use_local_env:
        # Use current interpreter; no search paths
        python_bin = sys.executable
        logger.info(f"Using local environment's vyper {vyper_version}")
    else:
        # Use couleuvre-managed venv and include its sys.path as search paths
        venv_path = ensure_vyper_version(vyper_version)
        python_bin = os.path.join(Path(venv_path), "bin", "python")
        logger.info(f"Using couleuvre-managed vyper {vyper_version} at {python_bin}")

    search_paths = get_search_paths(
        python_bin=python_bin,
        include_sys_path=True,
    )
    script = get_script(path, vyper_version, search_paths)

    result = subprocess.run(
        [python_bin, "-c", script],
        shell=True,
        input=script,
        capture_output=True,
        text=True,
        cwd=workspace_path,
    )

    if result.returncode != 0:
        logger.error(
            f"Failed to get AST for Vyper {vyper_version}: subprocess error: {result.stderr.strip()}"
        )
    else:
        logger.info(f"Got Vyper AST from Vyper {vyper_version}")

    parsed_json = json.loads(result.stdout)
    lsp_ast = _from_vyper_json_ast(parsed_json)

    logger.info("Parsed Vyper AST to LSP AST")
    return lsp_ast


# === Converter ===


def _from_vyper_json_ast(
    ast_dict: Dict[str, Any], parent: Optional[BaseNode] = None
) -> BaseNode:
    ast_type = ast_dict["ast_type"]
    if ast_type == "List":
        ast_type = "ListNode"
    elif ast_type == "Tuple":
        ast_type = "TupleNode"
    elif ast_type == "Dict":
        ast_type = "DictNode"
    elif ast_type == "EnumDef":
        ast_type = "FlagDef"
    cls = AST_CLASS_MAP.get(ast_type, BaseNode)
    cls_fields = cls.__dataclass_fields__

    kwargs = {"ast_type": ast_type}

    for key, value in ast_dict.items():
        if key not in cls_fields:
            logger.error(
                f"Key '{str(key)}' not found in {str(cls.__name__)} dataclass fields"
            )
            continue
        if isinstance(value, list):
            children = []
            for item in value:
                if isinstance(item, dict) and "ast_type" in item:
                    child = _from_vyper_json_ast(item)
                    child.parent = None  # Temporary
                    children.append(child)
                else:
                    children.append(item)
            kwargs[key] = children
        elif isinstance(value, dict) and "ast_type" in value:
            child = _from_vyper_json_ast(value)
            child.parent = None  # Temporary
            kwargs[key] = child
        else:
            kwargs[key] = value
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
