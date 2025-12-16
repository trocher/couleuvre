import os
import subprocess
from pathlib import Path
from packaging.version import Version

VYPER_BASE_DIR = Path.home() / ".couleuvre" / "venvs"


def _get_venv_path(version: str) -> Path:
    return VYPER_BASE_DIR / version


def _get_py_version_for_vy_version(vy_version: str) -> str:
    vy_ver = Version(vy_version)

    if vy_ver <= Version("0.2.7"):
        return "3.8"
    if vy_ver <= Version("0.3.2"):
        return "3.9"
    return "3.10"


def _get_venv_python(venv_path: Path) -> str:
    """Get the path to the Python executable in a virtual environment."""
    return str(venv_path / "bin" / "python")


def ensure_vyper_version(version: str) -> Path:
    """
    Ensure the specified vyper version is available in a uv-managed virtual environment.
    Returns the path to the virtual environment.
    """
    venv_path = _get_venv_path(version)

    if not venv_path.exists():
        print(f"[couleuvre] Creating uv env for vyper {version}...")

        py_version = _get_py_version_for_vy_version(version)
        # Create the environment using uv
        subprocess.run(
            ["uv", "venv", "--python", py_version, str(venv_path)],
            check=True,
        )

        venv_python = _get_venv_python(venv_path)
        env = os.environ.copy()
        env["VIRTUAL_ENV"] = str(venv_path)

        if Version(version) <= Version("0.2.7"):
            subprocess.run(
                [
                    "uv",
                    "pip",
                    "install",
                    "--python",
                    venv_python,
                    "--upgrade",
                    "setuptools",
                ],
                env=env,
                check=True,
            )
        # Install vyper
        subprocess.run(
            ["uv", "pip", "install", "--python", venv_python, f"vyper=={version}"],
            env=env,
            check=True,
        )

    return venv_path
