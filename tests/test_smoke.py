import tomllib
from pathlib import Path

import canditrack

ROOT = Path(__file__).resolve().parent.parent


def test_version_matches_pyproject():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert canditrack.__version__ == pyproject["project"]["version"]


def test_uv_lock_version_matches_pyproject():
    # release-please actualiza ambos; si se desincronizan, `uv sync --locked` falla en la CI.
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    package = next(p for p in lock["package"] if p["name"] == "canditrack")

    assert package["version"] == pyproject["project"]["version"]
