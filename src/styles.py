"""The app's colour palette.

One place for the hex values the UI paints with, so a colour used by the keypad,
the cards and the drawers cannot drift between them. This module only names the
colours - it never changes which control gets which.
"""

# Surfaces
APP_BACKGROUND = "#10131A"      # the page itself
PANEL_BACKGROUND = "#1B202B"    # display panel, history drawer
CARD_BACKGROUND = "#252B38"     # chain cards, history cards, ordinary keys

# Keys
ACCENT = "#4F7DFF"              # "=" and the conversion icons
KEY_DANGER = "#7B3340"          # AC and backspace
KEY_OPERATOR = "#303B50"        # operator keys and the scientific rows
KEY_DEFAULT = CARD_BACKGROUND   # digits and everything else
KEY_INK = "#40FFFFFF"           # the ripple spreading through a pressed key

# Text
TEXT_PRIMARY = "#FFFFFF"
TEXT_MUTED = "#9CA3AF"          # captions, secondary lines, hints
TEXT_SOFT = "#D1D5DB"           # the formula line inside a chain card
TEXT_FAINT = "#6B7280"          # the quiet hint under the conversion form
TEXT_ERROR = "#F28B82"          # a form that cannot be run as it stands
