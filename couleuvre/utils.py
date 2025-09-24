import logging
from importlib.metadata import version
from lsprotocol.types import Position, Range, Location
from packaging.version import Version
from couleuvre.ast_parser.vyper_ast import BaseNode

logger = logging.getLogger("couleuvre")


def get_installed_vyper_version():
    return Version(version("vyper"))


def range_from_node(node: BaseNode) -> Range:
    return Range(
        start=Position(line=node.lineno - 1, character=node.col_offset),
        end=Position(line=node.end_lineno - 1, character=node.end_col_offset),
    )


def range_from_start() -> Range:
    return Range(
        start=Position(line=0, character=0),
        end=Position(line=0, character=0),
    )


def location_from_start(uri: str) -> Location:
    return Location(uri=uri, range=range_from_start())
