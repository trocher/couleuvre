from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Type


@dataclass(eq=False)
class BaseNode:
    ast_type: str
    src: Optional[str] = None
    lineno: int = 0
    col_offset: int = 0
    end_lineno: int = 0
    end_col_offset: int = 0
    node_id: Optional[int] = None
    parent: Optional["BaseNode"] = field(default=None, repr=False, compare=False)

    def __hash__(self):
        return hash(self.node_id)

    def __eq__(self, other):
        return isinstance(other, BaseNode) and self.node_id == other.node_id


@dataclass(eq=False)
class TopLevel(BaseNode):
    name: Optional[str] = None
    body: List[Any] = field(default_factory=list)
    doc_string: Optional[Any] = None


@dataclass(eq=False)
class Module(TopLevel):
    path: Optional[str] = None
    body: List[Any] = field(default_factory=list)
    resolved_path: Optional[str] = None
    source_id: Optional[int] = None
    is_interface: Optional[bool] = None
    settings: Optional[Any] = None
    source_sha256sum: Optional[str] = None


@dataclass(eq=False)
class FunctionDef(TopLevel):
    args: Optional[Any] = None
    returns: Optional[Any] = None
    decorator_list: List[Any] = field(default_factory=list)
    pos: Optional[Any] = None


@dataclass(eq=False)
class DocStr(BaseNode):
    value: str = ""


@dataclass(eq=False)
class arguments(BaseNode):
    args: List[Any] = field(default_factory=list)
    defaults: List[Any] = field(default_factory=list)
    default: Optional[Any] = None


@dataclass(eq=False)
class arg(BaseNode):
    arg: str = ""
    annotation: Optional[Any] = None


@dataclass(eq=False)
class Return(BaseNode):
    value: Optional[Any] = None


@dataclass(eq=False)
class Expr(BaseNode):
    value: Any = None


@dataclass(eq=False)
class NamedExpr(BaseNode):
    target: Any = None
    value: Any = None


@dataclass(eq=False)
class Log(BaseNode):
    value: Any = None


@dataclass(eq=False)
class FlagDef(TopLevel):
    pass


@dataclass(eq=False)
class EventDef(TopLevel):
    pass


@dataclass(eq=False)
class InterfaceDef(TopLevel):
    pass


@dataclass(eq=False)
class StructDef(TopLevel):
    pass


@dataclass(eq=False)
class ExprNode(BaseNode):
    pass


@dataclass(eq=False)
class Constant(ExprNode):
    value: Any = None


@dataclass(eq=False)
class Num(Constant):
    pass


@dataclass(eq=False)
class Int(Num):
    pass


@dataclass(eq=False)
class Decimal(Num):
    pass


@dataclass(eq=False)
class Hex(Constant):
    value: str = ""


@dataclass(eq=False)
class Str(Constant):
    value: str = ""


@dataclass(eq=False)
class Bytes(Constant):
    value: bytes = b""


@dataclass(eq=False)
class HexBytes(BaseNode):
    value: Optional[bytes] = None


@dataclass(eq=False)
class ListNode(BaseNode):  # to avoid clashing with built-in `list`
    elements: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class TupleNode(BaseNode):  # to avoid clashing with built-in `tuple`
    elements: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class NameConstant(BaseNode):
    value: Any = None


@dataclass(eq=False)
class Ellipsis(BaseNode):
    value: Optional[Any] = None  # will be a string from `node_source_code`


@dataclass(eq=False)
class DictNode(BaseNode):  # to avoid clashing with built-in `Dict`
    keys: List[Any] = field(default_factory=list)
    values: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class Name(BaseNode):
    id: str = ""


@dataclass(eq=False)
class UnaryOp(BaseNode):
    op: Any = None
    operand: Any = None


@dataclass(eq=False)
class Operator(BaseNode):
    pass


@dataclass(eq=False)
class USub(BaseNode):
    pass


@dataclass(eq=False)
class Not(BaseNode):
    pass


@dataclass(eq=False)
class Invert(BaseNode):
    pass


@dataclass(eq=False)
class BinOp(BaseNode):
    left: Any = None
    op: Any = None
    right: Any = None


@dataclass(eq=False)
class Add(BaseNode):
    pass


@dataclass(eq=False)
class Sub(BaseNode):
    pass


@dataclass(eq=False)
class Mult(BaseNode):
    pass


@dataclass(eq=False)
class Div(BaseNode):
    pass


@dataclass(eq=False)
class FloorDiv(BaseNode):
    pass


@dataclass(eq=False)
class Mod(BaseNode):
    pass


@dataclass(eq=False)
class Pow(BaseNode):
    pass


@dataclass(eq=False)
class BitAnd(BaseNode):
    pass


@dataclass(eq=False)
class BitOr(BaseNode):
    pass


@dataclass(eq=False)
class BitXor(BaseNode):
    pass


@dataclass(eq=False)
class LShift(BaseNode):
    pass


@dataclass(eq=False)
class RShift(BaseNode):
    pass


@dataclass(eq=False)
class BoolOp(BaseNode):
    op: Any = None
    values: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class And(BaseNode):
    pass


@dataclass(eq=False)
class Or(BaseNode):
    pass


@dataclass(eq=False)
class Compare(BaseNode):
    left: Any = None
    op: Any = None
    right: Any = None


@dataclass(eq=False)
class Eq(BaseNode):
    pass


@dataclass(eq=False)
class NotEq(BaseNode):
    pass


@dataclass(eq=False)
class Lt(BaseNode):
    pass


@dataclass(eq=False)
class LtE(BaseNode):
    pass


@dataclass(eq=False)
class Gt(BaseNode):
    pass


@dataclass(eq=False)
class GtE(BaseNode):
    pass


@dataclass(eq=False)
class In(BaseNode):
    pass


@dataclass(eq=False)
class NotIn(BaseNode):
    pass


@dataclass(eq=False)
class Call(BaseNode):
    func: Any = None
    args: List[Any] = field(default_factory=list)
    keywords: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class ExtCall(BaseNode):
    value: Any = None


@dataclass(eq=False)
class StaticCall(BaseNode):
    value: Any = None


@dataclass(eq=False)
class keyword(BaseNode):
    arg: Optional[str] = None
    value: Any = None


@dataclass(eq=False)
class Attribute(BaseNode):
    value: Any = None
    attr: str = ""


@dataclass(eq=False)
class Subscript(BaseNode):
    value: Any = None
    slice: Any = None


@dataclass(eq=False)
class Assign(BaseNode):
    target: Any = None
    value: Any = None


@dataclass(eq=False)
class AnnAssign(BaseNode):
    target: Any = None
    annotation: Any = None
    value: Optional[Any] = None


@dataclass(eq=False)
class VariableDecl(BaseNode):
    target: Any = None
    annotation: Any = None
    value: Optional[Any] = None
    is_constant: Optional[bool] = None
    is_public: Optional[bool] = None
    is_immutable: Optional[bool] = None
    is_transient: Optional[bool] = None
    is_reentrant: Optional[bool] = None


@dataclass(eq=False)
class AugAssign(BaseNode):
    op: Any = None
    target: Any = None
    value: Any = None


@dataclass(eq=False)
class Raise(BaseNode):
    exc: Any = None


@dataclass(eq=False)
class Assert(BaseNode):
    test: Any = None
    msg: Any = None


@dataclass(eq=False)
class Pass(BaseNode):
    pass


@dataclass(eq=False)
class Import(BaseNode):
    name: Optional[str] = None
    alias: Optional[str] = None
    import_info: Optional[Dict] = None


@dataclass(eq=False)
class ImportFrom(BaseNode):
    name: Optional[str] = None
    alias: Optional[str] = None
    level: Optional[int] = None
    module: Optional[str] = None
    import_info: Optional[Dict] = None


@dataclass(eq=False)
class ImplementsDecl(BaseNode):
    annotation: Any = None


@dataclass(eq=False)
class UsesDecl(BaseNode):
    annotation: Any = None


@dataclass(eq=False)
class InitializesDecl(BaseNode):
    annotation: Any = None


@dataclass(eq=False)
class ExportsDecl(BaseNode):
    annotation: Any = None


@dataclass(eq=False)
class If(BaseNode):
    test: Any = None
    body: List[Any] = field(default_factory=list)
    orelse: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class IfExp(BaseNode):
    test: Any = None
    body: Any = None
    orelse: Any = None


@dataclass(eq=False)
class For(BaseNode):
    target: Any = None
    iter: Any = None
    body: List[Any] = field(default_factory=list)


@dataclass(eq=False)
class Break(BaseNode):
    pass


@dataclass(eq=False)
class Continue(BaseNode):
    pass


AST_CLASS_MAP: Dict[str, Type[BaseNode]] = {
    cls.__name__: cls
    for cls in list(globals().values())
    if isinstance(cls, type) and issubclass(cls, BaseNode)
}
