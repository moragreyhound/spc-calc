"""Design tokens — Tokyo Night / AstroVim palette, JetBrains Mono typography.

Dark, flat, single-accent-per-role. No gradients, no neon, no slop.
"""

# Surfaces, back to front
BG = "#1a1b26"          # editor background
PANEL = "#16161e"       # sidebar / rail (darker, like VS Code activity bar)
SURFACE = "#1f2335"     # cards, preview pane
RAISED = "#292e42"      # hover / selection
BORDER = "#101014"      # hairline borders... softened below
BORDER_SOFT = "#2b2f45"

# Text
TEXT = "#c0caf5"
MUTED = "#a9b1d6"
FAINT = "#565f89"
GUTTER = "#3b4261"

# Accents (one role each)
BLUE = "#7aa2f7"        # selection, links, primary brand
PURPLE = "#bb9af7"      # primary action ("=", create, unlock)
CYAN = "#7dcfff"        # operators, info
GREEN = "#9ece6a"       # success, text files
RED = "#f7768e"         # danger, delete, video
ORANGE = "#ff9e64"      # warnings, archives
YELLOW = "#e0af68"      # audio
TEAL = "#73daca"        # misc

# Semantic
DANGER = RED
OK = GREEN
WARN = ORANGE

# File-kind colors (VS Code inspired)
KIND_COLORS = {
    "text": GREEN,
    "code": BLUE,
    "image": PURPLE,
    "audio": YELLOW,
    "video": RED,
    "pdf": RED,
    "archive": ORANGE,
    "file": CYAN,
}
KIND_LABELS = {
    "text": "Text",
    "code": "Code",
    "image": "Image",
    "audio": "Audio",
    "video": "Video",
    "pdf": "PDF",
    "archive": "Archive",
    "file": "File",
}

FONT_FAMILY = "JetBrains Mono"  # resolved at runtime against installed fonts
FONT_FALLBACKS = ["Cascadia Code", "Cascadia Mono", "Consolas", "Menlo", "Segoe UI"]

DISPLAY_SIZE = 30
HISTORY_SIZE = 12
MONO = FONT_FAMILY  # widgets that want the mono face

# Key style presets for the calculator keypad
KEY_HEIGHT = 58
KEY_RADIUS = 14

KEY_STYLES = {
    "num": {"fg_color": SURFACE, "hover_color": RAISED, "text_color": TEXT},
    "fn": {"fg_color": PANEL, "hover_color": RAISED, "text_color": FAINT},
    "op": {"fg_color": SURFACE, "hover_color": RAISED, "text_color": CYAN},
    "eq": {"fg_color": PURPLE, "hover_color": "#c4b5fd", "text_color": "#1a1b26"},
}


def resolve_mono_family(root) -> str:
    """Pick the first monospace face that is actually installed."""
    import tkinter.font as tkfont

    try:
        installed = set(tkfont.families(root))
    except Exception:
        installed = set()
    for candidate in [FONT_FAMILY] + FONT_FALLBACKS:
        if candidate in installed:
            return candidate
    return "Segoe UI"
