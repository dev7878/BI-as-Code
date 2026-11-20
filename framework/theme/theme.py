"""Apply the design tokens everywhere: Plotly templates, CSS variables, number formats."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
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
    """Patch Vizro's light and dark templates in place so every figure picks up the tokens."""
    t = tokens()
    for name in ("vizro_light", "vizro_dark"):
        tpl = pio.templates[name]
        tpl.layout.colorway = t["categorical"]
        tpl.layout.font.family = t["font"]["family"]
        tpl.layout.title.font.family = t["font"]["family"]
        tpl.layout.hoverlabel.font.family = t["font"]["family"]
        tpl.layout.legend.title.text = ""
        tpl.layout.margin = go.layout.Margin(l=8, r=8, t=24, b=8)
    pio.templates.default = "vizro_light"


def write_css_tokens() -> None:
    """Expose tokens as CSS custom properties for assets/rbc.css (written into the Dash assets folder)."""
    t = tokens()
    lines = [
        ":root {",
        f"  --rbc-primary: {t['brand']['primary']};",
        f"  --rbc-primary-dark: {t['brand']['primary_dark']};",
        f"  --rbc-accent: {t['brand']['accent']};",
        f"  --rbc-on-primary: {t['brand']['on_primary']};",
        f"  --rbc-font: {t['font']['family']};",
        f"  --rbc-page: {t['surface']['page']};",
        f"  --rbc-card: {t['surface']['card']};",
        f"  --rbc-border: {t['surface']['border']};",
        f"  --rbc-text: {t['text']['primary']};",
        f"  --rbc-text-secondary: {t['text']['secondary']};",
        f"  --rbc-text-muted: {t['text']['muted']};",
        f"  --rbc-positive: {t['status']['positive']};",
        f"  --rbc-negative: {t['status']['negative']};",
        "}",
    ]
    (ASSETS_DIR / "_tokens.css").write_text("\n".join(lines) + "\n", encoding="utf-8")
