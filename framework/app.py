"""Build one Vizro app from every spec in dashboards/.

    rbc-bi run              # dev server on http://localhost:8050 with live reload on YAML changes
    gunicorn "rbc_bi.app:server()"   # production-style
"""

from __future__ import annotations

import logging

from vizro import Vizro
from vizro.managers import data_manager

from rbc_bi import paths
from rbc_bi.compiler.compiler import build_dashboard
from rbc_bi.modules.cache import make_cache
from rbc_bi.semantic.resolver import register_datasets
from rbc_bi.spec.validator import Project, load_project
from rbc_bi.theme.theme import ASSETS_DIR, apply_plotly_theme, write_css_tokens

log = logging.getLogger(__name__)


def create_app(project: Project | None = None) -> Vizro:
    project = project or load_project()
    if project.semantic is None or project.platform is None:
        raise SystemExit("Cannot start: config or semantic layer is invalid.\n" + "\n".join(map(str, project.errors)))
    for e in project.errors:
        log.warning("spec error: %s", e)

    Vizro._reset()
    apply_plotly_theme()
    write_css_tokens()
    data_manager.cache = make_cache()
    used = {comp.body.dataset for s in project.dashboards for _, comp in s.components()}
    register_datasets(project.semantic, used)
    return Vizro(assets_folder=str(ASSETS_DIR)).build(build_dashboard(project))


def server():
    """WSGI entry point for gunicorn."""
    return create_app().dash.server


def _snapshot() -> dict[str, float]:
    """mtime of every spec, config, theme and framework file, plus the local warehouse.
    Adding, editing or deleting any of them reloads (a warehouse rebuild also clears the query cache)."""
    globs = [
        (paths.DASHBOARDS_DIR, "*.y*ml"), (paths.SEMANTIC_DIR, "*.y*ml"), (paths.CONFIG_DIR, "*.y*ml"),
        (paths.THEME_DIR, "*.yaml"), (paths.THEME_DIR / "assets", "*.css"), (paths.FRAMEWORK_DIR, "**/*.py"),
        (paths.DATA_DIR, "warehouse.duckdb"),
    ]
    out = {}
    for d, pattern in globs:
        for f in d.glob(pattern):
            if not f.name.startswith("_tokens"):
                try:
                    out[str(f)] = f.stat().st_mtime
                except OSError:
                    pass
    return out


def serve(port: int = 8050) -> None:
    """Run the app in this process (no reload)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    create_app().run(debug=False, port=port)


def run(port: int = 8050, reload: bool = True) -> None:
    """Dev server. With reload, a small supervisor restarts the app whenever a spec or framework file changes,
    so an agent can write YAML and the page updates on refresh."""
    if not reload:
        return serve(port)
    import subprocess
    import sys
    import time

    cmd = [sys.executable, "-m", "rbc_bi", "run", "--no-reload", "--port", str(port)]
    print(f"rbc-bi: serving on http://localhost:{port}  (watching dashboards/, semantic/, config/, framework/)",
          flush=True)
    seen = _snapshot()
    child = subprocess.Popen(cmd)
    try:
        while True:
            time.sleep(1)
            now = _snapshot()
            if now != seen:
                changed = sorted({paths.rel(f) for f in set(now) ^ set(seen)}
                                 | {paths.rel(f) for f in now if f in seen and now[f] != seen[f]})
                print(f"rbc-bi: change detected in {', '.join(changed[:5])} -> reloading", flush=True)
                seen = now
                child.terminate()
                child.wait()
                child = subprocess.Popen(cmd)
            elif child.poll() is not None:
                print("rbc-bi: app exited; waiting for a file change to restart", flush=True)
                while _snapshot() == seen:
                    time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        child.terminate()
