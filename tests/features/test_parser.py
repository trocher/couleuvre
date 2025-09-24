import pytest
from couleuvre.ast_parser.ast_parser import get_json_ast

EXAMPLE_VYPER_CONTRACT = """
@external
def foo(x: uint256) -> uint256:
    return x + 1
"""

VYPER_VERSIONS = [
    "0.3.1",
    "0.3.2",
    "0.3.3",
    "0.3.4",
    "0.3.5",
    "0.3.6",
    "0.3.7",
    "0.3.8",
    "0.3.9",
    "0.3.10",
    "0.3.10rc3",
    "0.4.0",
    "0.4.0b1",
    "0.4.1",
    "0.4.2",
    "0.4.3",
]


@pytest.mark.parametrize("vyper_version", VYPER_VERSIONS)
def test_lsp_parses_vyper_contract(vyper_version):
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".vy", mode="w") as f:
        f.write(EXAMPLE_VYPER_CONTRACT)
        f.flush()
        ast = get_json_ast(f.name, vyper_version)
    assert ast is not None
    assert hasattr(ast, "body")
