import logging
import re
from typing import Optional, Tuple
from couleuvre.ast_parser import vyper_ast
from couleuvre.ast_parser.ast_parser import get_json_ast
from pathlib import Path

logger = logging.getLogger("couleuvre")


def parse_module(
    path: str,
    default_version: Optional[str] = None,
    workspace_path: Optional[str] = None,
) -> "Module":
    pattern = r"#\s*(?:@version|pragma\s+version)\s*(?:[<>=!~^]*)\s*(\d+\.\d+\.\d+)"
    content = Path(path).read_text()
    match = re.search(pattern, content)
    if not match:
        if default_version is not None:
            version = default_version
        else:
            raise ValueError("Version not found in the content")
    else:
        version = match.group(1)
    assert version is not None
    vyper_module = get_json_ast(path, version, workspace_path=workspace_path)
    visitor = VyperAstVisitor(vyper_module, version)
    visitor.visit(vyper_module)
    return visitor.module


class Import:
    def __init__(self, module: Optional[str], name: str, alias: Optional[str] = None):
        self.module = module
        self.name = name
        self.alias = alias


class Module:
    def __init__(self, ast, vyper_version):
        self.version = vyper_version
        self.ast = ast
        self.namespace = {"self": {}}

        self.flags = set()
        self.functions = set()
        self.events = set()
        self.interfaces = set()
        self.structs = set()
        self.variables = set()
        self.imports = dict()

    def external_namespace(self):
        return {
            k: v for k, v in self.namespace.items() if k != "self"
        } | self.namespace["self"]


class VyperNodeVisitorBase:
    ignored_types: Tuple = ()
    scope_name = ""

    def visit(self, node, *args):
        if isinstance(node, self.ignored_types):
            return
        node_type = type(node).__name__
        visitor_fn = getattr(self, f"visit_{node_type}", None)
        if visitor_fn is None:
            logger.info(
                f"Unsupported syntax for {self.scope_name} namespace: {node_type}",
                node,
            )
            return
        visitor_fn(node, *args)


class VyperAstVisitor(VyperNodeVisitorBase):
    def __init__(self, node, vyper_version: str):
        self.module: Module = Module(node, vyper_version)

    def visit_Module(self, node):
        for child in node.body:
            self.visit(child)
        pass

    def visit_VariableDecl(self, node):
        self.module.variables.add(node)
        if node.is_constant or node.is_immutable:
            self.module.namespace[node.target.id] = node
        else:
            self.module.namespace["self"][node.target.id] = node

    def visit_FunctionDef(self, node):
        self.module.functions.add(node)
        self.module.namespace["self"][node.name] = node

    def visit_FlagDef(self, node):
        self.module.flags.add(node)
        self.module.namespace[node.name] = node

    def visit_EventDef(self, node):
        self.module.events.add(node)
        self.module.namespace[node.name] = node

    def visit_InterfaceDef(self, node):
        self.module.interfaces.add(node)
        self.module.namespace[node.name] = node

    def visit_StructDef(self, node):
        self.module.structs.add(node)
        self.module.namespace[node.name] = node

    def _handle_import(self, node):
        resolved_path = (
            node.import_info.get("resolved_path") if node.import_info else None
        )
        if resolved_path is None:
            return
        if node.alias:
            self.module.imports[node.alias] = resolved_path
        self.module.imports[node.name] = resolved_path

    def visit_Import(self, node):
        self._handle_import(node)

    def visit_ImportFrom(self, node):
        self._handle_import(node)

    def visit_ImplementsDecl(self, node):
        pass

    def visit_UsesDecl(self, node):
        pass

    def visit_InitializesDecl(self, node):
        pass

    def visit_ExportsDecl(self, node):
        pass

    # For backwards compatibility
    def visit_AnnAssign(self, node):
        if isinstance(node.parent, vyper_ast.Module):
            if node.annotation is not None and isinstance(
                node.annotation, vyper_ast.Call
            ):
                if (
                    node.annotation.func.id == "constant"
                    or node.annotation.func.id == "immutable"
                ):
                    self.module.namespace[node.target.id] = node
            self.module.namespace["self"][node.target.id] = node
