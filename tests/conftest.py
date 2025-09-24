from unittest.mock import Mock
import pytest

from couleuvre.main import VyperLanguageServer
from pygls.workspace import TextDocument


@pytest.fixture
def mock_language_server():
    """Create a mock VyperLanguageServer."""
    ls = Mock(spec=VyperLanguageServer)
    # Provide a logger so production code can call ls.logger.info(...)
    ls.logger = Mock()
    # Optional: make info/debug no-ops
    ls.logger.info = Mock()
    ls.logger.debug = Mock()
    return ls


@pytest.fixture
def mock_text_document():
    """Create a mock TextDocument."""
    return Mock(spec=TextDocument)


@pytest.fixture
def mock_workspace():
    """Create a mock workspace."""
    return Mock()
