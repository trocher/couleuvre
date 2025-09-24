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


def ensure_vyper_version(version: str) -> Path:
    """
    Ensure the specified vyper version is available in a uv-managed virtual environment.
    Returns the path to the virtual environment.
    """
    venv_path = _get_venv_path(version)

    if not venv_path.exists():
        print(f"[couleuvre] Creating uv env for vyper {version}...")

        py_version = _get_py_version_for_vy_version(version)
        # Create the environment and install vyper using uv
        # uv venv --python=3.x <venv_path>
        subprocess.run(
            f"uv venv --python {py_version} {venv_path}",
            shell=True,
            check=True,
        )
        if Version(version) <= Version("0.2.7"):
            subprocess.run(
                f"source {venv_path}/bin/activate && uv pip install --upgrade setuptools",
                shell=True,
                check=True,
            )
        # uv pip install vyper==<version>
        subprocess.run(
            f"source {venv_path}/bin/activate && uv pip install vyper=={version}",
            shell=True,
            check=True,
        )

    return venv_path
