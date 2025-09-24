import logging
from pygls.server import LanguageServer


class LspLogHandler(logging.Handler):
    """Custom log handler that sends logs to the LSP client."""

    def __init__(self, ls: LanguageServer):
        super().__init__()
        self.ls = ls

    def emit(self, record):
        try:
            message = self.format(record)
            # Avoid sending logs if the server isn't fully initialized
            if self.ls and hasattr(self.ls, "show_message_log"):
                self.ls.show_message_log(message)
        except Exception:
            self.handleError(record)


def setup_logging(ls: LanguageServer, level=logging.INFO) -> logging.Logger:
    """Configures logging for the LSP server."""
    logger = logging.getLogger("vyper-lsp")
    logger.setLevel(level)

    # Prevent duplicate log handlers in case of reload
    if not logger.hasHandlers():
        # Console handler (stdout for debugging)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)

        # LSP log handler
        lsp_handler = LspLogHandler(ls)
        lsp_handler.setLevel(level)
        lsp_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        lsp_handler.setFormatter(lsp_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(lsp_handler)

    return logger
