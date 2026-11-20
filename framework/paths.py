"""Where things live.

Two roots:
- PACKAGE_DIR: the installed rbc_bi package (framework code, theme, JSON Schema).
- ROOT: the project folder with dashboards/, semantic/, config/ and data/. It is NOT assumed to be
  next to the package, because a normal (non-editable) install puts the package in site-packages.
  Resolution order: $RBC_BI_ROOT, then the current directory or its nearest parent that has
  config/platform.yaml, then the folder containing the package (editable install / source checkout).
"""

from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
MARKER = Path("config") / "platform.yaml"


def find_root(start: Path | None = None) -> Path:
    if os.environ.get("RBC_BI_ROOT"):
        return Path(os.environ["RBC_BI_ROOT"]).resolve()
    here = Path(start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / MARKER).is_file():
            return d
    return PACKAGE_DIR.parent


ROOT = find_root()

DASHBOARDS_DIR = ROOT / "dashboards"
SEMANTIC_DIR = ROOT / "semantic"
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
FRAMEWORK_DIR = PACKAGE_DIR
THEME_DIR = PACKAGE_DIR / "theme"
SCHEMA_PATH = PACKAGE_DIR / "spec" / "dashboard.schema.json"


def rel(path: Path) -> str:
    """Repo-relative, forward-slash path for error messages."""
    try:
        return Path(path).resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return Path(path).as_posix()
