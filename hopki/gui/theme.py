"""Color themes for the Hopki GUI, derived from ``theme_seuss.css``.

Qt's stylesheet language is *not* web CSS — it has no ``var()``, ``@import``, named
gradients, transitions or animations. So rather than feed the .css to Qt (which would ignore
almost all of it), we parse the **palette** out of its ``[data-theme="dark"|"light"]`` blocks
and build a Qt-valid stylesheet plus pyqtgraph colors from those colors. The .css stays the
source of truth: edit its variables and the app re-themes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .resources import asset_path

_CSS_PATH = asset_path("theme_seuss.css")

# Fallbacks if the CSS is missing or a variable can't be parsed (mirror theme_seuss.css).
_DEFAULTS: dict[str, dict[str, str]] = {
    "Dark": {
        "bg": "#0d1117", "bg-surface": "#161b22", "bg-elevated": "#1c2128",
        "border": "#484f58", "text": "#c9d1d9", "text-bright": "#f0f6fc",
        "text-muted": "#8b949e", "accent": "#58a6ff", "red": "#f85149",
        "green": "#56d364", "purple": "#bc8cff", "orange": "#f0883e",
    },
    "Light": {
        "bg": "#F4E7C6", "bg-surface": "#FFFFFF", "bg-elevated": "#FFF0CC",
        "border": "#E8B84B", "text": "#2B2B2B", "text-bright": "#1A1A1A",
        "text-muted": "#6B5B3E", "accent": "#2B78C4", "red": "#E63B2E",
        "green": "#4CAF50", "purple": "#9C27B0", "orange": "#FF8C00",
    },
}


@dataclass(frozen=True)
class Theme:
    name: str
    bg: str
    surface: str
    elevated: str
    border: str
    text: str
    text_bright: str
    text_muted: str
    accent: str
    red: str
    green: str
    purple: str
    orange: str

    # --- plot role colors -------------------------------------------------
    @property
    def plot_bg(self) -> str:
        return self.surface

    @property
    def plot_fg(self) -> str:
        return self.text

    @property
    def grid(self) -> str:
        return self.border

    @property
    def incident(self) -> str:
        return self.accent

    @property
    def reflected(self) -> str:
        return self.red

    @property
    def transmitted(self) -> str:
        return self.green

    @property
    def engineering(self) -> str:
        return self.purple

    @property
    def true_curve(self) -> str:
        return self.text_bright

    @property
    def timcut(self) -> str:
        return self.orange

    def qss(self) -> str:
        """A Qt stylesheet built from this palette (storybook-ish: rounded, bordered)."""
        return f"""
        QWidget {{ background: {self.bg}; color: {self.text}; font-size: 12px; }}
        QLabel {{ background: transparent; }}
        QPushButton {{
            background: {self.elevated}; color: {self.text_bright};
            border: 2px solid {self.border}; border-radius: 10px;
            padding: 6px 14px; font-weight: 600;
        }}
        QPushButton:hover {{ border-color: {self.accent}; }}
        QPushButton:disabled {{ color: {self.text_muted}; border-color: {self.border}; }}
        QCheckBox {{ background: transparent; spacing: 6px; }}
        QCheckBox::indicator {{
            width: 16px; height: 16px; border: 2px solid {self.border};
            border-radius: 5px; background: {self.surface};
        }}
        QCheckBox::indicator:checked {{ background: {self.accent}; border-color: {self.accent}; }}
        QSpinBox, QDoubleSpinBox, QComboBox {{
            background: {self.surface}; color: {self.text};
            border: 2px solid {self.border}; border-radius: 8px;
            padding: 3px 6px; min-height: 24px;
        }}
        QComboBox {{ padding-right: 26px; min-width: 96px; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding; subcontrol-position: top right; width: 22px;
            border-left: 2px solid {self.border};
        }}
        QComboBox::down-arrow {{ width: 11px; height: 11px; }}
        QComboBox QAbstractItemView {{
            background: {self.surface}; color: {self.text};
            border: 2px solid {self.border}; outline: 0;
            selection-background-color: {self.accent}; selection-color: {self.text_bright};
        }}
        QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{
            subcontrol-origin: border; width: 20px;
            border-left: 2px solid {self.border}; background: {self.elevated};
        }}
        QAbstractSpinBox::up-button {{ subcontrol-position: top right; border-top-right-radius: 6px; }}
        QAbstractSpinBox::down-button {{ subcontrol-position: bottom right; border-bottom-right-radius: 6px; }}
        QAbstractSpinBox::up-arrow {{ width: 11px; height: 11px; }}
        QAbstractSpinBox::down-arrow {{ width: 11px; height: 11px; }}
        QListWidget {{
            background: {self.surface}; color: {self.text};
            border: 2px solid {self.border}; border-radius: 8px; padding: 2px;
        }}
        QListWidget::item {{ padding: 2px 4px; }}
        QGroupBox {{
            border: 2px solid {self.border}; border-radius: 10px;
            margin-top: 10px; padding: 8px 6px 6px 6px; font-weight: 700;
        }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {self.text_bright}; }}
        QLineEdit {{
            background: {self.surface}; color: {self.text};
            border: 2px solid {self.border}; border-radius: 6px; padding: 2px 6px; min-height: 22px;
        }}
        QLineEdit:focus {{ border-color: {self.accent}; }}
        QSlider::groove:horizontal {{ height: 6px; background: {self.border}; border-radius: 3px; }}
        QSlider::handle:horizontal {{
            background: {self.accent}; width: 16px; margin: -6px 0; border-radius: 8px;
        }}
        QToolButton {{
            background: {self.elevated}; color: {self.text_bright};
            border: 2px solid {self.border}; border-radius: 10px;
            padding: 6px 10px; font-weight: 700; text-align: left;
        }}
        QToolButton:hover {{ border-color: {self.accent}; }}
        QScrollArea {{ border: none; background: {self.bg}; }}
        QSplitter::handle {{ background: {self.border}; }}
        QTabBar::tab {{
            background: {self.elevated}; color: {self.text_muted};
            border: 2px solid {self.border}; border-bottom: none;
            border-top-left-radius: 10px; border-top-right-radius: 10px;
            padding: 6px 16px; margin-right: 2px; font-weight: 700;
        }}
        QTabBar::tab:selected {{ color: {self.text_bright}; background: {self.surface}; }}
        QTabWidget::pane {{ border: 2px solid {self.border}; border-radius: 8px; }}
        """


def _parse_block(css: str, selector: str) -> dict[str, str]:
    match = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    if not match:
        return {}
    return {
        name: value.strip()
        for name, value in re.findall(r"--([\w-]+)\s*:\s*([^;]+);", match.group(1))
    }


def _theme_from(name: str, palette: dict[str, str]) -> Theme:
    d = _DEFAULTS[name]

    def get(key: str) -> str:
        value = palette.get(key, "").strip()
        return value if value.startswith("#") else d[key]

    return Theme(
        name=name, bg=get("bg"), surface=get("bg-surface"), elevated=get("bg-elevated"),
        border=get("border"), text=get("text"), text_bright=get("text-bright"),
        text_muted=get("text-muted"), accent=get("accent"), red=get("red"),
        green=get("green"), purple=get("purple"), orange=get("orange"),
    )


def load_themes(css_path: str | Path = _CSS_PATH) -> dict[str, Theme]:
    """Return ``{"Light": Theme, "Dark": Theme}`` parsed from the Seuss CSS palette."""
    try:
        css = Path(css_path).read_text(encoding="utf-8")
    except OSError:
        css = ""
    return {
        "Light": _theme_from("Light", _parse_block(css, '[data-theme="light"]')),
        "Dark": _theme_from("Dark", _parse_block(css, '[data-theme="dark"]')),
    }
