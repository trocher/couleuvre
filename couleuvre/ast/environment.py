"""
Environment abstraction for Vyper execution.

Provides a base class and two implementations:
- SystemEnvironment: Uses vyper from the current Python environment
- CouleuvreEnvironment: Uses a couleuvre-managed virtual environment
"""

import json
import logging
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from packaging.version import Version

from couleuvre.ast.vyper_wrapper import ensure_vyper_version

logger = logging.getLogger("couleuvre")


class VyperEnvironment(ABC):
    """
    Abstract base class for Vyper execution environments.

    Subclasses must implement:
    - python_bin: Path to the Python interpreter
    - vyper_version: The version of Vyper in this environment
    """

    @property
    @abstractmethod
    def python_bin(self) -> str:
        """Return the path to the Python interpreter."""
        ...

    @property
    @abstractmethod
    def vyper_version(self) -> str:
        """Return the Vyper version string."""
        ...

    def get_sys_path(self) -> list[str]:
        """
        Obtain all the system paths in which the compiler would
        normally look for modules. This allows to lint vyper files
        that import a module that is installed as a virtual environment
        dependency.
        """
        command = [
            self.python_bin,
            "-c",
            "import json, sys; print(json.dumps(sys.path))",
        ]

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(
                "Unable to read sys.path from %s: %s",
                self.python_bin,
                result.stderr.strip(),
            )
            return []

        try:
            paths = json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.warning("Unable to decode sys.path from %s", self.python_bin)
            return []

        return paths

    def get_search_paths(self, include_sys_path: bool = True) -> list[str]:
        """
        Build the search path list passed to Vyper's FilesystemInputBundle.

        - If include_sys_path is False, return an empty list (no search paths).
        - If include_sys_path is True, obtain sys.path from the environment's
          Python interpreter and include "." for workspace resolution.
        """
        search_paths: list[str] = []

        if include_sys_path:
            search_paths.extend(self.get_sys_path())
            if "." not in search_paths:
                search_paths.append(".")

        logger.info(f"Final search paths: {search_paths}")
        return search_paths

    def run_script(
        self, script: str, cwd: Optional[str] = None
    ) -> subprocess.CompletedProcess:
        """
        Run a Python script in this environment.

        Args:
            script: The Python script to execute
            cwd: Working directory for the subprocess

        Returns:
            The completed process result
        """
        return subprocess.run(
            [self.python_bin, "-c", script],
            capture_output=True,
            text=True,
            cwd=cwd,
        )


class SystemEnvironment(VyperEnvironment):
    """
    Environment using Vyper from the current Python environment.

    Use this when the user has Vyper installed in their active environment
    and it matches the required version.
    """

    def __init__(self, vyper_version: str):
        self._vyper_version = vyper_version
        logger.info("Using system environment's vyper %s", vyper_version)

    @property
    def python_bin(self) -> str:
        return sys.executable

    @property
    def vyper_version(self) -> str:
        return self._vyper_version


class CouleuvreEnvironment(VyperEnvironment):
    """
    Environment using a couleuvre-managed virtual environment.

    This creates/uses a dedicated virtual environment managed by couleuvre
    with a specific Vyper version installed via uv.
    """

    def __init__(self, vyper_version: str):
        self._vyper_version = vyper_version
        self._venv_path = ensure_vyper_version(vyper_version)
        logger.info(
            "Using couleuvre-managed vyper %s at %s",
            vyper_version,
            self._venv_path,
        )

    @property
    def python_bin(self) -> str:
        return os.path.join(self._venv_path, "bin", "python")

    @property
    def vyper_version(self) -> str:
        return self._vyper_version

    @property
    def venv_path(self) -> Path:
        """Return the path to the managed virtual environment."""
        return self._venv_path


def resolve_environment(vyper_version: str) -> VyperEnvironment:
    """
    Resolve the appropriate environment for the given Vyper version.

    If the current Python environment has the required Vyper version installed,
    returns a SystemEnvironment. Otherwise, returns a CouleuvreEnvironment
    which will create/use a managed virtual environment.

    Args:
        vyper_version: The required Vyper version string

    Returns:
        The appropriate VyperEnvironment instance
    """
    from couleuvre import utils

    try:
        installed_version = utils.get_installed_vyper_version()
    except Exception:
        installed_version = None

    if installed_version and installed_version == Version(vyper_version):
        return SystemEnvironment(vyper_version)
    else:
        return CouleuvreEnvironment(vyper_version)
