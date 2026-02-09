import importlib
import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

from couleuvre.parser import Module
from couleuvre.server import VyperLanguageServer

server_module = importlib.import_module("couleuvre.server")


class FakeLoop:
    def __init__(self) -> None:
        self.threadsafe_calls = 0
        self.created_tasks = 0

    def is_running(self) -> bool:
        return True

    def create_task(self, coro):
        self.created_tasks += 1
        coro.close()
        return Mock()

    def call_soon_threadsafe(self, callback) -> None:
        self.threadsafe_calls += 1
        callback()


def test_schedule_import_parsing_uses_saved_loop_from_worker_thread(monkeypatch):
    ls = VyperLanguageServer("couleuvre-test", "v0")
    fake_loop = FakeLoop()
    ls._event_loop = cast(asyncio.AbstractEventLoop, fake_loop)
    module = cast(Module, SimpleNamespace(imports={"dep": "/tmp/dep.vy"}))

    monkeypatch.setattr(
        server_module.uris, "from_fs_path", lambda path: f"file://{path}"
    )
    parse_import_mock = Mock()
    monkeypatch.setattr(ls, "_parse_import", parse_import_mock)

    ls.schedule_import_parsing(module, workspace_path="/tmp/workspace")

    assert fake_loop.threadsafe_calls == 1
    assert fake_loop.created_tasks == 1
    parse_import_mock.assert_not_called()


def test_schedule_import_parsing_falls_back_to_inline_without_loop(monkeypatch):
    ls = VyperLanguageServer("couleuvre-test", "v0")
    ls._event_loop = None
    module = cast(Module, SimpleNamespace(imports={"dep": "/tmp/dep.vy"}))

    monkeypatch.setattr(
        server_module.uris, "from_fs_path", lambda path: f"file://{path}"
    )
    parse_import_mock = Mock()
    monkeypatch.setattr(ls, "_parse_import", parse_import_mock)

    ls.schedule_import_parsing(module, workspace_path="/tmp/workspace")

    parse_import_mock.assert_called_once_with(
        "file:///tmp/dep.vy", "/tmp/dep.vy", "/tmp/workspace"
    )
