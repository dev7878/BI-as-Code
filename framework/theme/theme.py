"""Apply the design tokens everywhere: Plotly templates, CSS variables, number formats."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import vizro  # noqa: F401  (registers the vizro_light / vizro_dark templates we patch)
import yaml

THEME_DIR = Path(__file__).resolve().parent
ASSETS_DIR = THEME_DIR / "assets"


@lru_cache(maxsize=1)
def tokens() -> dict:
    with open(THEME_DIR / "tokens.yaml", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# d3 formats used for axes, hovers and tables, keyed by spec `format`.
D3_FORMATS = {"currency": "$,.0f", "percent": ".1%", "integer": ",.0f", "number": ",.2f"}
AXIS_FORMATS = {"currency": "$~s", "percent": ".0%", "integer": "~s", "number": "~s"}


def format_value(value: float, fmt: str) -> str:
    """Python-side formatting for KPI cards (compact, readable)."""
    if value is None or value != value:  # NaN
        return "-"
    if fmt == "percent":
        return f"{value:.1%}"
    sign = "-" if value < 0 else ""
    v = abs(value)
    prefix = "$" if fmt == "currency" else ""
    for div, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if v >= div and not (fmt == "integer" and v < 100_000):
            return f"{sign}{prefix}{v / div:,.2f}{suffix}"
    if fmt == "integer" or (fmt == "currency" and v >= 100):
        return f"{sign}{prefix}{v:,.0f}"
    return f"{sign}{prefix}{v:,.2f}"


def apply_plotly_theme() -> None:
    """Patch Vizro's light and dark templates in place so every figure follows the tokens in both modes.

    Charts draw on a transparent background (they sit on a card), with quiet grids and no axis lines.
    Ring/gap colours for donuts and scatter markers come from the template, so they match the surface
    in each mode instead of being baked into the figure.
    """
    t = tokens()
    for name, mode in (("vizro_light", "light"), ("vizro_dark", "dark")):
        m = t[mode]
        tpl = pio.templates[name]
        L = tpl.layout
        L.colorway = t["categorical"]
        L.font = dict(family=t["font"]["family"], color=m["text_2"], size=12)
        L.title.font.family = t["font"]["family"]
        L.paper_bgcolor = "rgba(0,0,0,0)"
        L.plot_bgcolor = "rgba(0,0,0,0)"
        L.margin = go.layout.Margin(l=8, r=8, t=28, b=8)
        L.legend = dict(title=dict(text=""), font=dict(color=m["text_2"], size=12), bgcolor="rgba(0,0,0,0)")
        L.hoverlabel = dict(bgcolor=m["surface"], bordercolor=m["border_strong"],
                            font=dict(family=t["font"]["family"], color=m["text"], size=12))
        for axis in (L.xaxis, L.yaxis):
            axis.gridcolor = m["grid"]
            axis.linecolor = m["border"]
            axis.zerolinecolor = m["border_strong"]
            axis.tickfont = dict(color=m["muted"], size=11)
            axis.title.font = dict(color=m["text_2"], size=12)
            axis.showline = False
            axis.ticks = ""
        L.xaxis.showgrid = False
        L.yaxis.showgrid = True
        tpl.data.pie = [go.Pie(marker=dict(line=dict(color=m["surface"], width=3)))]
        tpl.data.scatter = [go.Scatter(marker=dict(line=dict(color=m["surface"], width=1.5)))]
        tpl.data.bar = [go.Bar(marker=dict(line=dict(width=0)))]
    pio.templates.default = "vizro_light"


def _mode_css(selector: str, mode: str) -> str:
    t = tokens()
    m = t[mode]
    primary = t["brand"]["primary"] if mode == "light" else t["brand"]["primary_dark_mode"]
    v = {
        # Framework tokens (used by rbc.css)
        "--rbc-primary": primary,
        "--rbc-accent": t["brand"]["accent"],
        "--rbc-page": m["page"], "--rbc-surface": m["surface"], "--rbc-surface-2": m["surface_2"],
        "--rbc-border": m["border"], "--rbc-border-strong": m["border_strong"],
        "--rbc-text": m["text"], "--rbc-text-2": m["text_2"], "--rbc-muted": m["muted"],
        "--rbc-shadow": m["shadow"],
        "--rbc-good": m["good"], "--rbc-good-bg": m["good_bg"],
        "--rbc-bad": m["bad"], "--rbc-bad-bg": m["bad_bg"], "--rbc-flat-bg": m["flat_bg"],
        "--rbc-primary-soft": f"color-mix(in srgb, {primary} 12%, transparent)",
        # Bootstrap variables Vizro styles itself with
        "--bs-body-bg": m["page"], "--bs-body-color": m["text"], "--bs-emphasis-color": m["text"],
        "--bs-secondary-color": m["text_2"], "--bs-tertiary-color": m["muted"],
        "--bs-border-color": m["border"], "--bs-border-color-translucent": m["border"],
        "--bs-left-side-bg": m["surface"], "--bs-container-bg": m["surface"], "--bs-container-nested-bg": m["surface_2"],
        "--bs-kpi-card-bg": m["surface"], "--bs-tertiary-bg": m["surface_2"], "--bs-secondary-bg": m["surface_2"],
        "--bs-highlight-bg": f"color-mix(in srgb, {primary} 12%, transparent)",
        "--bs-nav-link-highlight": f"color-mix(in srgb, {primary} 12%, transparent)",
        "--bs-primary": primary, "--bs-link-color": primary, "--bs-link-hover-color": primary,
        "--bs-primary-bg-subtle": f"color-mix(in srgb, {primary} 12%, transparent)",
        "--bs-primary-text-emphasis": primary,
        "--bs-focus-ring-color": f"color-mix(in srgb, {t['brand']['accent']} 60%, transparent)",
        "--bs-box-shadow-sm": "none",
        "--bs-body-font-family": t["font"]["family"],
        "--input-field-bg": m["surface_2"],
        # Mantine (date picker, dropdown popovers)
        "--mantine-color-body": m["surface"], "--mantine-color-text": m["text"],
        "--mantine-color-dimmed": m["muted"], "--mantine-color-default": m["surface_2"],
        "--mantine-color-default-border": m["border"], "--mantine-color-default-hover": m["surface_2"],
        "--mantine-primary-color-filled": primary, "--mantine-primary-color-filled-hover": primary,
        "--mantine-primary-color-light": f"color-mix(in srgb, {primary} 14%, transparent)",
        "--mantine-primary-color-light-color": primary,
        "--mantine-font-family": t["font"]["family"],
    }
    body = "\n".join(f"  {k}: {val};" for k, val in v.items())
    return f"{selector} {{\n  color-scheme: {mode};\n{body}\n}}\n"


def write_css_tokens() -> None:
    """Generate assets/_tokens.css: one variable block per mode, keyed off Vizro's data-bs-theme attribute
    (which its light/dark toggle flips). html[...] outranks Bootstrap's own [data-bs-theme] blocks."""
    t = tokens()
    css = [
        "/* GENERATED from framework/theme/tokens.yaml by theme.py. Do not edit. */",
        _mode_css(':root, html[data-bs-theme="light"]', "light"),
        _mode_css('html[data-bs-theme="dark"]', "dark"),
        f":root {{ --rbc-radius-card: {t['radius']['card']}; --rbc-radius-control: {t['radius']['control']}; "
        f"--rbc-font: {t['font']['family']}; --rbc-mark: \"{t['brand']['mark']}\"; "
        f"--rbc-tagline: \"{t['brand']['tagline']}\"; }}",
    ]
    (ASSETS_DIR / "_tokens.css").write_text("\n".join(css) + "\n", encoding="utf-8")
