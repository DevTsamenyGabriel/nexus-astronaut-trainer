"""Colors, fonts and configurable footer statuses.
Single place for look and footer config. Every value shown as a status is honest:
nothing says LIVE or CONNECTED unless a real check says so."""
from __future__ import annotations

from PyQt6.QtGui import QColor

# --- Palette ---
BG = "#05070f"
PANEL_TOP = "#0f1d33"
PANEL_BOT = "#0b1426"
BORDER = "#1f4d7a"
CYAN = "#7fd3ff"
GREEN = "#3ddc97"
AMBER = "#ffb347"
RED = "#ff5c5c"
BLUE = "#4aa3ff"
TEXT = "#d6e6f5"
MUTED = "#6f8aa6"

FONT_FAMILIES = ["Consolas", "Courier New", "monospace"]

# --- Bar thresholds for resource bars (0-100). Atlas confirmed 30 / 20. ---
THRESH_WARN = 30
THRESH_CRIT = 20

# --- Honest panel titles (all values are simulation values) ---
TITLE_TELEMETRY = "TELEMETRY (SIMULATED)"
TITLE_ALERT_TAG = "SIMULATED EVENT"


# --- Footer statuses: (label, value, color) ---
def footer_statuses(ai_online: bool | None = None):
    """Footer items. ai_online: True/False from a real check, None = not checked."""
    if ai_online is None:
        ai = ("AI", "NOT CHECKED", MUTED)
    elif ai_online:
        ai = ("AI", "ONLINE", GREEN)
    else:
        ai = ("AI", "OFFLINE", RED)
    return [
        ("MODE", "SIMULATION", AMBER),
        ai,
        ("VOICE", "NEEDS INTERNET", AMBER),
    ]


FOOTER_STATUSES = footer_statuses()
FOOTER_TEXT = "NEXUS v1.0 · BUILT IN ACCRA, GHANA 🇬🇭 · NASA SPACE APPS 2026"

# Global stylesheet (tooltips + thin scrollbars)
GLOBAL_QSS = f"""
QToolTip {{
    background: #0b1426; color: {TEXT}; border: 1px solid {BORDER};
    padding: 4px 6px;
}}
QLabel {{ background: transparent; color: {TEXT}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: #1f4d7a; border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
"""


def qc(hex_color: str, alpha: int = 255) -> QColor:
    """QColor from hex with alpha."""
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c

