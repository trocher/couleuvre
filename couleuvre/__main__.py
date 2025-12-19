"""Entry point for `python -m couleuvre`."""

from couleuvre.server import server
from pygls.cli import start_server

start_server(server)
