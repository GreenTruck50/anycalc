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


@dataclass(frozen=True)
class NamedColor:
    name: str
    value: str


# The theme that takes its accent colors from the user instead of shipping its
# own. It is the only one whose color dropdowns are shown.
CUSTOM_THEME_NAME = "Custom"

# The dropdown entry that opens a color picker instead of picking a named color.
# It is not a color itself, so it is kept out of COLOR_OPTIONS.
CUSTOM_COLOR_KEY = "custom"


# The named colors the settings dropdowns offer, grouped by hue and carrying
# several shades per family. Every theme's default accents - Dark's "Blue" and
# operator key "Slate", Light's "Royal blue" and "Light gray", and the same for
# Midnight, Forest, Sepia and High contrast - are entries here, which is what
# lets "Reset to defaults" put them back by name, so never drop those values
# from this list.
COLOR_OPTIONS = (
    # Blues
    NamedColor("Blue", "#4F7DFF"),
    NamedColor("Royal blue", "#3155C7"),
    NamedColor("Sky blue", "#0EA5E9"),
    NamedColor("Navy", "#1E3A8A"),
    NamedColor("Indigo", "#4F46E5"),
    # Purples and pinks
    NamedColor("Violet", "#8B5CF6"),
    NamedColor("Purple", "#7E22CE"),
    NamedColor("Lavender", "#A78BFA"),
    NamedColor("Magenta", "#D946EF"),
    NamedColor("Pink", "#EC4899"),
    NamedColor("Rose", "#F43F5E"),
    # Reds, oranges and browns
    NamedColor("Red", "#EF4444"),
    NamedColor("Crimson", "#DC143C"),
    NamedColor("Maroon", "#7B1E27"),
    NamedColor("Orange", "#F97316"),
    NamedColor("Amber", "#F59E0B"),
    NamedColor("Gold", "#EAB308"),
    NamedColor("Brown", "#8B5A2B"),
    # Greens
    NamedColor("Green", "#22C55E"),
    NamedColor("Dark green", "#166534"),
    NamedColor("Forest green", "#228B22"),
    NamedColor("Olive", "#808000"),
    NamedColor("Lime", "#84CC16"),
    NamedColor("Emerald", "#10B981"),
    NamedColor("Teal", "#14B8A6"),
    NamedColor("Turquoise", "#2DD4BF"),
    NamedColor("Cyan", "#06B6D4"),
    # Neutrals
    NamedColor("Slate", "#303B50"),
    NamedColor("Charcoal", "#1F2937"),
    NamedColor("Gray", "#64748B"),
    NamedColor("Light gray", "#D1D5DB"),
)


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
    AppTheme(
        name="Midnight",
        mode="dark",
        app_background="#070C18",
        panel_background="#111827",
        card_background="#1B2334",
        accent="#0EA5E9",
        key_danger="#7B3340",
        key_operator="#303B50",
        key_ink="#40FFFFFF",
        text_primary="#F2F6FF",
        text_muted="#A8B3C7",
        text_soft="#C9D3E5",
        text_faint="#5D6A82",
        text_error="#F97066",
    ),
    AppTheme(
        name="Forest",
        mode="dark",
        app_background="#0C1710",
        panel_background="#14231A",
        card_background="#1D3125",
        accent="#10B981",
        key_danger="#7B3340",
        key_operator="#166534",
        key_ink="#40FFFFFF",
        text_primary="#EAF3EC",
        text_muted="#A3B8A8",
        text_soft="#CFE0D2",
        text_faint="#5C7264",
        text_error="#F97066",
    ),
    AppTheme(
        name="Sepia",
        mode="light",
        app_background="#F3EBDA",
        panel_background="#FCF6E8",
        card_background="#E9DFC9",
        accent="#8B5A2B",
        key_danger="#EFD3CC",
        key_operator="#EAB308",
        key_ink="#408B5A2B",
        text_primary="#3A2E22",
        text_muted="#6B5A48",
        text_soft="#4C3D2E",
        text_faint="#8A7863",
        text_error="#B42318",
    ),
    AppTheme(
        name="High contrast",
        mode="dark",
        app_background="#000000",
        panel_background="#0B0B0B",
        card_background="#1A1A1A",
        accent="#EAB308",
        key_danger="#E5484D",
        key_operator="#D1D5DB",
        key_ink="#40FFFFFF",
        text_primary="#FFFFFF",
        text_muted="#E6E6E6",
        text_soft="#FFFFFF",
        text_faint="#A3A3A3",
        text_error="#FF6B6B",
    ),
    # The user's own palette. It starts on Dark's surfaces and accents, and the
    # two color settings then replace the accent and the operator-key color.
    AppTheme(
        name=CUSTOM_THEME_NAME,
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


# The dropdown entry that follows the operating system instead of picking a
# palette of its own. It is not a theme in THEMES - it has no colors - it is a
# rule for choosing between the built-ins, which is why it lives beside them
# rather than inside the tuple.
SYSTEM_THEME_NAME = "System"


def is_system_theme(name: str) -> bool:
    """Whether a theme name asks to follow the system rather than pick a palette."""

    return name == SYSTEM_THEME_NAME


def system_theme(brightness: object) -> AppTheme:
    """The built-in palette the host platform's brightness asks for.

    A dark system gets the dark palette and a light system the light one; a
    platform that reports nothing at all - a test, or a desktop toolkit that
    never answers - keeps the app's own default.
    """

    value = getattr(brightness, "value", brightness)
    if value == "light":
        return get_theme("Light")
    return DEFAULT_THEME


def normalize_color(color: str) -> str:
    """Validate a six-digit RGB hex color and return it in uppercase."""

    if not isinstance(color, str) or _HEX_COLOR_PATTERN.fullmatch(color) is None:
        raise ValueError("color must be a six-digit hexadecimal RGB value")
    return color.upper()


def is_named_color(color: str) -> bool:
    """Whether a color is one of the named palette entries."""

    try:
        normalized = normalize_color(color)
    except ValueError:
        return False
    return any(option.value == normalized for option in COLOR_OPTIONS)


def color_options() -> tuple[NamedColor, ...]:
    """The entry that opens a color picker, then the named colors.

    "Custom color" leads the list rather than trailing it: it is a mode rather
    than another color, and keeping it apart from the named palette also keeps it
    on screen when a dropdown opens on a named color. The picker that entry
    reveals holds the color that actually gets applied.
    """

    return (NamedColor("Custom color", CUSTOM_COLOR_KEY), *COLOR_OPTIONS)


def custom_color_label(color: str) -> str:
    """The "Custom color" entry's label, naming the hex it currently holds."""

    if is_named_color(color):
        return "Custom color"
    try:
        return f"Custom color ({normalize_color(color)})"
    except ValueError:
        return "Custom color"


def custom_color_value_label(color: str) -> str:
    """The caption that names the custom color currently in use."""

    try:
        return f"Custom color: {normalize_color(color)}"
    except ValueError:
        return "Custom color"


def picker_color(color: object) -> str:
    """Read a color back from a color picker as a validated hex color.

    A picker reports "#RRGGBB", or "#AARRGGBB" while alpha is enabled, in
    whichever case it feels like; both fold into the six-digit uppercase form
    the rest of the app stores.
    """

    text = str(color or "").strip().upper()
    if text.startswith("#") and len(text) == 9:
        text = f"#{text[3:]}"
    return normalize_color(text)


def get_active_theme() -> AppTheme:
    """The theme whose colors are live right now."""

    return _active_theme


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
