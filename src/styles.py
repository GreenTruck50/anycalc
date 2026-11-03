"""The app's named colour themes and the active palette."""

import re
from dataclasses import dataclass

_HEX_COLOR_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}")


@dataclass(frozen=True)
class AppTheme:
    name: str
    mode: str
    app_background: str
    panel_background: str
    card_background: str
    accent: str
    key_danger: str
    key_operator: str
    key_ink: str
    text_primary: str
    text_muted: str
    text_soft: str
    text_faint: str
    text_error: str

    def palette(
        self,
        primary_color: str | None = None,
        secondary_color: str | None = None,
    ) -> dict[str, str]:
        primary = self.accent if primary_color is None else primary_color
        secondary = self.key_operator if secondary_color is None else secondary_color
        return {
            "APP_BACKGROUND": self.app_background,
            "PANEL_BACKGROUND": self.panel_background,
            "CARD_BACKGROUND": self.card_background,
            "ACCENT": primary,
            "KEY_DANGER": self.key_danger,
            "KEY_OPERATOR": secondary,
            "KEY_DEFAULT": self.card_background,
            "KEY_INK": self.key_ink,
            "TEXT_PRIMARY": self.text_primary,
            "TEXT_MUTED": self.text_muted,
            "TEXT_SOFT": self.text_soft,
            "TEXT_FAINT": self.text_faint,
            "TEXT_ERROR": self.text_error,
        }


THEMES = (
    AppTheme(
        name="Dark",
        mode="dark",
        app_background="#10131A",
        panel_background="#1B202B",
        card_background="#252B38",
        accent="#4F7DFF",
        key_danger="#7B3340",
        key_operator="#303B50",
        key_ink="#40FFFFFF",
        text_primary="#FFFFFF",
        text_muted="#9CA3AF",
        text_soft="#D1D5DB",
        text_faint="#6B7280",
        text_error="#F28B82",
    ),
    AppTheme(
        name="Light",
        mode="light",
        app_background="#F3F4F6",
        panel_background="#FFFFFF",
        card_background="#E5E7EB",
        accent="#3155C7",
        key_danger="#F6D7DB",
        key_operator="#D1D5DB",
        key_ink="#403155C7",
        text_primary="#171923",
        text_muted="#5B6472",
        text_soft="#3D4652",
        text_faint="#667085",
        text_error="#B42318",
    ),
)

DEFAULT_THEME = THEMES[0]
_active_theme = DEFAULT_THEME
_active_primary_color = DEFAULT_THEME.accent
_active_secondary_color = DEFAULT_THEME.key_operator


def get_theme(name: str) -> AppTheme:
    """Return a configured theme by its display name."""

    for theme in THEMES:
        if theme.name == name:
            return theme
    raise ValueError(f"Unknown theme: {name}")


def normalize_color(color: str) -> str:
    """Validate a six-digit RGB hex color and return it in uppercase."""

    if not isinstance(color, str) or _HEX_COLOR_PATTERN.fullmatch(color) is None:
        raise ValueError("color must be a six-digit hexadecimal RGB value")
    return color.upper()


def active_palette() -> dict[str, str]:
    """Return the active palette, including custom accent colors."""

    return _active_theme.palette(_active_primary_color, _active_secondary_color)


def set_active_theme(
    name: str,
    primary_color: str | None = None,
    secondary_color: str | None = None,
) -> tuple[AppTheme, AppTheme]:
    """Set the palette constants and return the previous and current themes."""

    global _active_theme, ACCENT, APP_BACKGROUND, CARD_BACKGROUND, KEY_DANGER
    global KEY_DEFAULT, KEY_INK, KEY_OPERATOR, PANEL_BACKGROUND
    global TEXT_ERROR, TEXT_FAINT, TEXT_MUTED, TEXT_PRIMARY, TEXT_SOFT
    global _active_primary_color, _active_secondary_color
    previous = _active_theme
    current = get_theme(name)
    next_primary_color = normalize_color(
        current.accent if primary_color is None else primary_color
    )
    next_secondary_color = normalize_color(
        current.key_operator if secondary_color is None else secondary_color
    )
    _active_theme = current
    _active_primary_color = next_primary_color
    _active_secondary_color = next_secondary_color
    palette = active_palette()
    ACCENT = palette["ACCENT"]
    APP_BACKGROUND = palette["APP_BACKGROUND"]
    CARD_BACKGROUND = palette["CARD_BACKGROUND"]
    KEY_DANGER = palette["KEY_DANGER"]
    KEY_DEFAULT = palette["KEY_DEFAULT"]
    KEY_INK = palette["KEY_INK"]
    KEY_OPERATOR = palette["KEY_OPERATOR"]
    PANEL_BACKGROUND = palette["PANEL_BACKGROUND"]
    TEXT_ERROR = palette["TEXT_ERROR"]
    TEXT_FAINT = palette["TEXT_FAINT"]
    TEXT_MUTED = palette["TEXT_MUTED"]
    TEXT_PRIMARY = palette["TEXT_PRIMARY"]
    TEXT_SOFT = palette["TEXT_SOFT"]
    return previous, current


ACCENT: str = DEFAULT_THEME.accent
APP_BACKGROUND: str = DEFAULT_THEME.app_background
CARD_BACKGROUND: str = DEFAULT_THEME.card_background
KEY_DANGER: str = DEFAULT_THEME.key_danger
KEY_DEFAULT: str = DEFAULT_THEME.card_background
KEY_INK: str = DEFAULT_THEME.key_ink
KEY_OPERATOR: str = DEFAULT_THEME.key_operator
PANEL_BACKGROUND: str = DEFAULT_THEME.panel_background
TEXT_ERROR: str = DEFAULT_THEME.text_error
TEXT_FAINT: str = DEFAULT_THEME.text_faint
TEXT_MUTED: str = DEFAULT_THEME.text_muted
TEXT_PRIMARY: str = DEFAULT_THEME.text_primary
TEXT_SOFT: str = DEFAULT_THEME.text_soft
