#!/usr/bin/env python3
"""
Shishya — what every app on the clone's screen shares. Runs INSIDE the sandbox.

The Windows build's apps are Qt rather than GTK. GTK on Windows is a second
operating system's worth of DLLs; Qt is native here, publishes itself to UI
Automation the way GTK published itself to AT-SPI, and runs inside an
AppContainer without complaint. The apps' logic did not move — it lives in
vm/shell (common, books, library, documents, codegen, checks…) and is shared
with the Mac's GTK apps. Only the windows are new.

Four things live here:

  look       one stylesheet, the panel's Swiss-technical palette
  windows    every app parents itself into the clone's screen, so the clone
             has ONE screen the panel can show — the 1440x900 the VM had
  threads    model calls take minutes; ui() hands a result back safely
  recording  the recorder. On the Mac it watched AT-SPI from outside the
             apps; here it is an event filter inside each one, because UI
             Automation does not cross out of an AppContainer, and the only
             outside alternative is a global keyboard hook — which would also
             hear everything YOU type, in every program. This one hears only
             the clone's own apps, and only while a lesson is being taught.
"""

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("SHISHYA_ROOT") or HERE.parent)
for p in (ROOT / "vm" / "shell", ROOT / "vm", HERE):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from PySide6.QtCore import QEvent, QObject, QPointF, QRect, QRectF, Qt, QTimer, Signal   # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QPainter, QPainterPath,   # noqa: E402
                           QPalette, QPen, QWindow)
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication,   # noqa: E402
                               QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import common   # noqa: E402

# ─── look ───────────────────────────────────────────────────────────────────
# One product, three surfaces: the home page, the clone's desk, and the apps
# on it. The desk is deep ink with cream text; what you read and type into is
# warm paper, with the home page's tints for emphasis. Corners are round and
# edges are quiet. The look this replaced was black hairlines on cold white,
# which belonged to neither the desk nor the home page — and it styled only
# some widgets, so on a PC in dark mode the rest (the chat itself, Findings,
# the bill) came out black with dark text on it.

ACCENT = "#0078d4"      # Settings' accent replaces it when an app starts
DOCK_SPACE = 88         # the strip the clone's dock floats in (desktop.RESERVED)
SCREEN_W, SCREEN_H = 1440, 900
INK, PAPER, SURFACE = "#1B1F38", "#FAF7F0", "#FFFFFF"
RULE, MUTED, SOFT = "#E6E1D5", "#6E7183", "#F3EFE5"
DESK, DESK_EDGE, DESK_TEXT = "#1E2340", "#2C3256", "#FBF7EC"
# The home page's tints: (fill, the dark that is drawn on it).
TINT = {"butter": ("#F3E3A6", "#633806"), "mint": ("#CFE8DA", "#085041"),
        "peach": ("#F6CDB8", "#712B13"), "lav": ("#D6D2F4", "#3C3489"),
        "paper": ("#E8E4D8", "#444441")}

# Line icons, 24x24, the same drawings as the home page's tiles.
ICONS = {
    "chat": "M4 5h16v11H9l-5 4z",
    "bill": "M6 3h12v18l-3-2-3 2-3-2-3 2z M9 8h6 M9 12h6",
    "inbox": "M4 13l3-8h10l3 8v6H4z M4 13h5l1 2h4l1-2h5",
    "folder": "M3 7h7l2 2h9v10H3z",
    "teach": "M12 4a4 4 0 1 0 0.01 0z M4 21c1-4 4-6 8-6c4 0 7 2 8 6",
    "doc": "M7 3h7l5 5v13H7z M14 3v5h5 M10 13h6 M10 17h6",
    "find": "M11 5a6 6 0 1 0 0.01 0z M20 20l-4.5-4.5",
    "chart": "M5 20V10 M12 20V4 M19 20v-7",
    "sheet": "M4 4h16v16H4z M4 10h16 M10 4v16",
    "book": "M4 6c3-2 5-2 8 0v13c-3-2-5-2-8 0z M12 6c3-2 5-2 8 0v13c-3-2-5-2-8 0z",
    "code": "M8 8l-4 4 4 4 M16 8l4 4-4 4 M14 5l-4 14",
    "bank": "M3 10l9-6 9 6 M5 10v8 M10 10v8 M14 10v8 M19 10v8 M3 20h18",
    "card": "M3 6h18v13H3z M3 10h18 M7 15h4",
    "pulse": "M3 12h4l3-7 4 14 3-7h4",
    "globe": "M12 3a9 9 0 1 0 0.01 0z M3 12h18 M12 3c3 3 3 15 0 18 M12 3c-3 3-3 15 0 18",
    "gauge": "M3 4h18v16H3z M7 15l3-4 3 2 4-5",
    "model": "M12 9a3 3 0 1 0 0.01 0z M12 3v3 M12 18v3 M3 12h3 M18 12h3",
    "sliders": "M4 7h10 M18 7h2 M4 17h2 M10 17h10 M16 5v4 M8 15v4",
    "search": "M11 5a6 6 0 1 0 0.01 0z M20 20l-4.5-4.5",
    "grid": "M4 4h7v7H4z M13 4h7v7h-7z M4 13h7v7H4z M13 13h7v7h-7z",
}

# A window's title → its icon and tint, the same pair its tile has in the
# start panel, so a window, its dock button and its tile are recognisably one.
WINDOW_ICONS = {
    "shishya": ("chat", "butter"), "billing": ("bill", "butter"), "inbox": ("inbox", "mint"),
    "files": ("folder", "paper"), "teach a lesson": ("teach", "lav"),
    "make a document": ("doc", "peach"), "findings": ("find", "peach"),
    "reports": ("chart", "peach"), "training data": ("book", "lav"), "sheets": ("sheet", "mint"),
    "code": ("code", "paper"), "vs code": ("code", "lav"), "banking": ("bank", "mint"),
    "credit assistant": ("card", "mint"), "activity": ("pulse", "paper"),
    "browser": ("globe", "paper"), "system": ("gauge", "paper"), "models": ("model", "paper"),
    "settings": ("sliders", "paper"),
}


def icon_for(title):
    t = (title or "").lower()
    if t in WINDOW_ICONS:
        return WINDOW_ICONS[t]
    for name, pair in WINDOW_ICONS.items():
        if t.startswith(name) or name in t:
            return pair
    return "grid", "paper"


def mix(a, b, t):
    """Colour a moved t of the way to colour b, as #rrggbb."""
    a, b = QColor(a), QColor(b)
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in
                                   ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue())))


def look_accent():
    """The accent chosen in Settings (shared/.desktop.json), or the default."""
    try:
        chosen = json.loads((common.SHARED / ".desktop.json").read_text(encoding="utf-8")).get("accent")
        return chosen if QColor(chosen or "").isValid() else ACCENT
    except (OSError, ValueError, AttributeError):
        return ACCENT


def stylesheet(accent=ACCENT):
    wash = mix(accent, "#ffffff", 0.84)          # a selected row: the accent, mostly paper
    return f"""
* {{ font-family: "Segoe UI Variable Text", "Segoe UI", "Inter", sans-serif; font-size: 13px;
     color: {INK}; }}
QWidget#appBody {{ background: {PAPER}; border-bottom-left-radius: 9px;
                   border-bottom-right-radius: 9px; }}
QDialog, QMessageBox, QFileDialog {{ background: {PAPER}; }}
QLabel {{ background: transparent; }}
QLabel[role="title"] {{ font-size: 17px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 11px; letter-spacing: 1.2px;
                          font-weight: 600; padding-top: 8px; }}
QToolTip {{ background: {DESK}; color: {DESK_TEXT}; border: 1px solid {DESK_EDGE};
            padding: 4px 8px; }}

QPushButton {{ background: {SURFACE}; border: 1px solid {RULE}; padding: 7px 14px;
               border-radius: 8px; }}
QPushButton:hover {{ background: {SOFT}; border-color: #D5CFC0; }}
QPushButton:pressed {{ background: #E9E4D7; }}
QPushButton:focus {{ border-color: {accent}; }}
QPushButton:disabled {{ color: #A9A8A0; background: #F6F3EC; border-color: #ECE8DD; }}
QPushButton[kind="primary"] {{ background: {DESK}; color: {DESK_TEXT}; border-color: {DESK};
                               font-weight: 600; }}
QPushButton[kind="primary"]:hover {{ background: {accent}; border-color: {accent}; color: white; }}
QPushButton[kind="primary"]:pressed {{ background: {mix(accent, "#000000", 0.18)}; }}
QPushButton[kind="primary"]:disabled {{ background: #B9BAC6; border-color: #B9BAC6;
                                        color: #F3F1EA; }}

QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {SURFACE}; border: 1px solid {RULE}; padding: 6px 9px; border-radius: 8px;
    selection-background-color: {accent}; selection-color: white; }}
QPlainTextEdit, QTextEdit {{ border-radius: 10px; padding: 8px; }}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover {{ border-color: #D5CFC0; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {accent}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {{ background: #F6F3EC;
                                                                   color: {MUTED}; }}
QComboBox QAbstractItemView {{ background: {SURFACE}; border: 1px solid {RULE};
    selection-background-color: {wash}; selection-color: {INK}; outline: 0; }}

QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget, QListView {{
    background: {SURFACE}; alternate-background-color: #FCFAF6; border: 1px solid {RULE};
    border-radius: 10px; gridline-color: #EFEBE1; selection-background-color: {wash};
    selection-color: {INK}; outline: 0; }}
QTableWidget::item, QTableView::item {{ padding: 3px 6px; }}
QListWidget::item, QListView::item {{ padding: 5px 10px; border-radius: 6px; }}
QListWidget::item:hover, QListView::item:hover {{ background: {SOFT}; }}
QListWidget::item:selected, QListView::item:selected {{ background: {wash}; color: {INK}; }}
QHeaderView {{ background: transparent; border: 0; }}
QHeaderView::section {{ background: {SOFT}; color: #4B4F66; border: 0;
    border-bottom: 1px solid {RULE}; padding: 7px 8px; font-weight: 600; font-size: 12px; }}
QHeaderView::section:horizontal:first {{ border-top-left-radius: 9px; }}
QHeaderView::section:horizontal:last {{ border-top-right-radius: 9px; }}
QHeaderView::section:horizontal:only-one {{ border-top-left-radius: 9px;
                                            border-top-right-radius: 9px; }}
QTableCornerButton::section {{ background: {SOFT}; border: 0; border-bottom: 1px solid {RULE};
                               border-top-left-radius: 9px; }}

QTabWidget::pane {{ border: 1px solid {RULE}; border-radius: 10px; background: {SURFACE};
                    top: 6px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{ padding: 6px 16px; margin-right: 4px; border: 0; border-radius: 8px;
                background: transparent; color: {MUTED}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ background: {SOFT}; color: {INK}; }}
QTabBar::tab:selected {{ background: {DESK}; color: {DESK_TEXT}; }}

QProgressBar {{ border: 0; background: #ECE7DB; border-radius: 7px; min-height: 14px;
                max-height: 14px; text-align: center; font-size: 10px; color: {INK}; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 7px; }}

QScrollArea {{ background: transparent; border: 0; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 10px; }}
QSplitter::handle:vertical {{ height: 10px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle {{ background: #D8D2C3; border-radius: 4px; }}
QScrollBar::handle:vertical {{ min-height: 28px; }}
QScrollBar::handle:horizontal {{ min-width: 28px; }}
QScrollBar::handle:hover {{ background: #BDB6A6; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
QMenu {{ background: {SURFACE}; border: 1px solid {RULE}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: {SOFT}; color: {INK}; }}
QFrame#card {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 12px; }}
QFrame#bubbleYou {{ background: {TINT["butter"][0]}; border-radius: 14px; }}
QFrame#bubbleYou QLabel {{ color: #3B2606; }}
QFrame#bubbleShishya {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 14px; }}
QFrame#bubbleShishya[doing="true"] {{ background: transparent; border: 1px dashed #D5CFC0; }}
QPlainTextEdit#codeBlock {{ background: #F7F4EC; border: 1px solid {RULE}; border-radius: 8px;
    padding: 6px 8px; font-family: "Cascadia Mono", "Consolas", monospace; font-size: 12px; }}
QPushButton#chip {{ background: {SURFACE}; border: 1px solid {RULE}; border-radius: 15px;
                    padding: 6px 14px; color: #4B4F66; }}
QPushButton#chip:hover {{ background: {TINT["butter"][0]}; border-color: #E2CD86;
                          color: {TINT["butter"][1]}; }}
QFrame#titleBar {{ background: {DESK}; }}
QFrame#titleBar QLabel {{ color: {DESK_TEXT}; font-size: 12px; font-weight: 600; }}
"""


def palette(accent=ACCENT):
    """Every colour role, set — so nothing an app forgot to style can fall
    back to the PC's own theme. In dark mode that fallback is black."""
    pal = QPalette()
    for role, colour in (
            (QPalette.Window, PAPER), (QPalette.WindowText, INK), (QPalette.Base, SURFACE),
            (QPalette.AlternateBase, "#FCFAF6"), (QPalette.Text, INK), (QPalette.Button, SURFACE),
            (QPalette.ButtonText, INK), (QPalette.BrightText, "#ffffff"),
            (QPalette.ToolTipBase, DESK), (QPalette.ToolTipText, DESK_TEXT),
            (QPalette.PlaceholderText, "#9A9CA8"), (QPalette.Highlight, accent),
            (QPalette.HighlightedText, "#ffffff"), (QPalette.Link, accent),
            (QPalette.Light, "#ffffff"), (QPalette.Midlight, SOFT), (QPalette.Mid, RULE),
            (QPalette.Dark, "#B9B3A4"), (QPalette.Shadow, "#8E897C")):
        pal.setColor(role, QColor(colour))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor("#A9A8A0"))
    return pal


_paths = {}


def icon_path(d):
    """The small subset of SVG path syntax the icons above use."""
    if d in _paths:
        return _paths[d]
    import re
    path = QPainterPath()
    x = y = sx = sy = 0.0
    for cmd, args in re.findall(r"([MmLlHhVvZzAaCc])([^MmLlHhVvZzAaCc]*)", d):
        nums = [float(n) for n in re.findall(r"-?\d*\.?\d+", args)]
        if cmd in "Mm":
            for i in range(0, len(nums), 2):
                dx, dy = nums[i], nums[i + 1]
                x, y = (x + dx, y + dy) if cmd == "m" else (dx, dy)
                if i == 0:
                    path.moveTo(x, y)
                    sx, sy = x, y
                else:
                    path.lineTo(x, y)
        elif cmd in "Ll":
            for i in range(0, len(nums), 2):
                dx, dy = nums[i], nums[i + 1]
                x, y = (x + dx, y + dy) if cmd == "l" else (dx, dy)
                path.lineTo(x, y)
        elif cmd in "Hh":
            for n in nums:
                x = x + n if cmd == "h" else n
                path.lineTo(x, y)
        elif cmd in "Vv":
            for n in nums:
                y = y + n if cmd == "v" else n
                path.lineTo(x, y)
        elif cmd in "Cc":
            for i in range(0, len(nums), 6):
                c = nums[i:i + 6]
                if cmd == "c":
                    c = [c[0] + x, c[1] + y, c[2] + x, c[3] + y, c[4] + x, c[5] + y]
                path.cubicTo(*c)
                x, y = c[4], c[5]
        elif cmd in "Aa":
            # Only full circles are drawn with arcs here ("a r r 0 1 0 .01 0"):
            # the centre is a radius to the right of where the arc starts.
            for i in range(0, len(nums), 7):
                rx = nums[i]
                ex, ey = nums[i + 5], nums[i + 6]
                if cmd == "a":
                    ex, ey = ex + x, ey + y
                path.addEllipse(QRectF(x - rx, y, 2 * rx, 2 * rx))
                x, y = ex, ey
                path.moveTo(x, y)
        elif cmd in "Zz":
            path.closeSubpath()
            x, y = sx, sy
    _paths[d] = path
    return path


def paint_icon(p, rect, icon, tint, radius=None):
    """A tinted rounded square with a line drawing in the tint's dark."""
    fill, ink = TINT.get(tint, TINT["paper"])
    r = QRectF(rect)
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(fill))
    p.drawRoundedRect(r, radius or r.width() * 0.28, radius or r.width() * 0.28)
    k = r.width() * 0.5 / 24
    p.translate(r.x() + r.width() * 0.25, r.y() + r.height() * 0.25)
    p.scale(k, k)
    pen = QPen(QColor(ink), 1.8)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    p.drawPath(icon_path(ICONS.get(icon, ICONS["grid"])))
    p.restore()


def style(widget, **props):
    """Set dynamic properties the stylesheet keys on (role=muted…)."""
    for k, v in props.items():
        widget.setProperty(k, v)
    return widget


def label(text="", role=None, wrap=False, name=None):
    lab = QLabel(text)
    if role:
        lab.setProperty("role", role)
    if wrap:
        lab.setWordWrap(True)
    if name:
        lab.setObjectName(name)
        lab.setAccessibleName(name)
    lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def button(text, handler=None, primary=False, name=None):
    """A button published under the name a lesson will use for it."""
    b = QPushButton(text)
    b.setAccessibleName(text)
    b.setObjectName(name or _ident(text))
    if primary:
        b.setProperty("kind", "primary")
    if handler:
        b.clicked.connect(lambda *_: handler())
    return b


def entry(placeholder="", name=None, accessible=None):
    e = QLineEdit()
    e.setPlaceholderText(placeholder)
    if name:
        e.setObjectName(name)
    e.setAccessibleName(accessible or placeholder or name or "")
    return e


def human(n):
    """A file size the way a person reads one."""
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def _ident(text):
    out = "".join(ch for ch in text.title() if ch.isalnum())
    return out[:1].lower() + out[1:] if out else "control"


# ─── threads ────────────────────────────────────────────────────────────────

class _Bridge(QObject):
    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda fn: fn(), Qt.QueuedConnection)


_bridge = None


def ui(fn, *args, **kwargs):
    """Run fn on the UI thread, from any thread. The GLib.idle_add of here."""
    _bridge.call.emit(lambda: fn(*args, **kwargs))


def background(work, done=None, failed=None):
    """work() on a thread; done(result) or failed(exception) back on the UI."""
    import threading

    def run():
        try:
            result = work()
        except Exception as e:                       # noqa: BLE001
            if failed:
                ui(failed, e)
            elif done:
                ui(done, f"{type(e).__name__}: {e}")
            return
        if done:
            ui(done, result)
    threading.Thread(target=run, daemon=True).start()


# ─── the application ────────────────────────────────────────────────────────

def application(name):
    """The QApplication every app starts from, with the clone's look, its
    taskbar identity, and the recorder installed."""
    global _bridge
    if _already_open(name):
        sys.exit(0)                 # it was open: brought forward, not opened twice
    if sys.platform == "win32":
        import ctypes
        # Grouped under the clone in the Windows taskbar, never under Python —
        # an app of the clone should not look like one of yours.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shishya.Clone")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(name)
    # Light, whatever the PC is set to. Qt follows Windows' dark mode for
    # every widget a stylesheet does not cover, and the clone's apps are
    # paper: in dark mode the chat came out black on black.
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except (AttributeError, TypeError):
        pass
    for chosen in ("windows11", "windowsvista", "Fusion"):
        if chosen.lower() in [s.lower() for s in __import__("PySide6.QtWidgets",
                                                            fromlist=["QStyleFactory"]).QStyleFactory.keys()]:
            app.setStyle(chosen)
            break
    accent = look_accent()
    app.setPalette(palette(accent))
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(stylesheet(accent))
    _bridge = _Bridge()
    app._focus_on_click = FocusOnClick(app)
    app.installEventFilter(app._focus_on_click)
    app._cloak_popups = CloakPopups(app)
    app.installEventFilter(app._cloak_popups)
    Recorder.install(app, name)
    return app


# ─── windows on the clone's screen ──────────────────────────────────────────
# The clone's screen is one window; every app is a child window of it. A child
# window gets nothing from Windows that a window on your own desktop has — no
# frame, no minimise, no maximise, no edge to resize by, no rounded corners —
# so all of it is here: what a window IS on the clone's screen.

MINIMISED = "ShishyaMinimised"     # a window property: hidden, but still open
_libs = {}


def _user32():
    """user32 with the handle-sized argument types these calls need. A
    private instance: the types must not leak into other code's calls."""
    if "user32" not in _libs:
        import ctypes
        from ctypes import wintypes
        u = ctypes.WinDLL("user32")
        u.GetParent.argtypes = [wintypes.HWND]
        u.GetParent.restype = wintypes.HWND
        u.IsWindowVisible.argtypes = [wintypes.HWND]
        u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
        u.SetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.HANDLE]
        u.GetPropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        u.GetPropW.restype = wintypes.HANDLE
        u.RemovePropW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        u.RemovePropW.restype = wintypes.HANDLE
        u.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
        u.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE, wintypes.BOOL]
        u.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
        u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        u.SetFocus.argtypes = [wintypes.HWND]
        g = ctypes.WinDLL("gdi32")
        g.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
        g.CreateRoundRectRgn.restype = wintypes.HANDLE
        _libs["user32"], _libs["gdi32"] = u, g
    return _libs["user32"]


def desk_windows(desk):
    """The app windows on the clone's screen, oldest first, as
    (handle, title, minimised). Asked of Windows rather than tracked, so a
    window any process opened is here."""
    if sys.platform != "win32" or not desk:
        return []
    import ctypes
    from ctypes import wintypes
    u = _user32()
    out = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        if u.GetParent(h) == desk:
            hidden = bool(u.GetPropW(h, MINIMISED))
            if hidden or u.IsWindowVisible(h):
                buf = ctypes.create_unicode_buffer(200)
                u.GetWindowTextW(h, buf, 200)
                if buf.value:
                    out.append((int(h), buf.value, hidden))
        return True
    u.EnumChildWindows(desk, proc(each), 0)
    return list(reversed(out))             # Windows lists children topmost first


def restore_window(hwnd):
    """Show a window again if it was minimised, and bring it to the front."""
    u = _user32()
    u.RemovePropW(hwnd, MINIMISED)
    u.ShowWindow(hwnd, 5)                                          # SW_SHOW
    u.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # to the top, as it is
    u.SetFocus(hwnd)


def minimise_window(hwnd):
    """Out of sight, still open: hidden, and marked so the dock keeps its
    button and opening the app again brings this one back."""
    u = _user32()
    u.SetPropW(hwnd, MINIMISED, 1)
    u.ShowWindow(hwnd, 0)                                          # SW_HIDE


def _already_open(name):
    """An app opened twice is one window brought forward, not two. Only a
    plain open: Files asked for a particular folder, or Sheets for a
    particular file, is a new window."""
    desk = int(os.environ.get("SHISHYA_DESKTOP_HWND") or 0)
    if not desk or sys.platform != "win32" or len(sys.argv) > 1:
        return False
    import ctypes
    from ctypes import wintypes
    for hwnd, title, _hidden in desk_windows(desk):
        pid = wintypes.DWORD(0)
        _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if title == name and pid.value != os.getpid():
            restore_window(hwnd)
            return True
    return False


class _TitleIcon(QWidget):
    CHROME = True

    def __init__(self, title):
        super().__init__()
        self.pair = icon_for(title)
        self.setFixedSize(20, 20)

    def paintEvent(self, _e):
        p = QPainter(self)
        paint_icon(p, QRectF(0, 0, 20, 20), *self.pair, radius=6)
        p.end()


class ChromeButton(QPushButton):
    """Minimise, maximise or close: a line drawing on the title bar."""

    NAMES = {"min": ("Minimise", "minimiseWindow"), "max": ("Maximise", "maximiseWindow"),
             "close": ("Close", "closeWindow")}

    def __init__(self, kind, window, handler):
        super().__init__()
        self.kind, self.window_ = kind, window
        tip, ident = self.NAMES[kind]
        self.setAccessibleName(tip)
        self.setToolTip(tip)
        self.setObjectName(ident)
        self.setFixedSize(44, TitleBar.HEIGHT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_Hover, True)
        self.clicked.connect(lambda *_: handler())

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse():
            p.fillRect(self.rect(), QColor("#C8402F") if self.kind == "close"
                       else QColor(255, 255, 255, 30))
        pen = QPen(QColor(DESK_TEXT), 1.3)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        cx, cy = self.width() / 2, self.height() / 2
        if self.kind == "min":
            p.drawLine(QPointF(cx - 5, cy + 4), QPointF(cx + 5, cy + 4))
        elif self.kind == "max" and self.window_.is_maximised():
            p.drawRoundedRect(QRectF(cx - 5.5, cy - 2.5, 8, 8), 1.5, 1.5)
            p.drawPolyline([QPointF(cx - 2.5, cy - 2.5), QPointF(cx - 2.5, cy - 5.5),
                            QPointF(cx + 5.5, cy - 5.5), QPointF(cx + 5.5, cy + 2.5),
                            QPointF(cx + 2.5, cy + 2.5)])
        elif self.kind == "max":
            p.drawRoundedRect(QRectF(cx - 5, cy - 5, 10, 10), 1.5, 1.5)
        else:
            p.drawLine(QPointF(cx - 4.5, cy - 4.5), QPointF(cx + 4.5, cy + 4.5))
            p.drawLine(QPointF(cx + 4.5, cy - 4.5), QPointF(cx - 4.5, cy + 4.5))
        p.end()


class TitleBar(QFrame):
    """What a window on the clone's screen has instead of a Windows frame:
    its icon and title, a bar to drag it by — to the top edge to fill the
    screen, to a side edge for half of it — and minimise, maximise, close."""

    CHROME = True          # the recorder ignores it: our furniture, not the task
    HEIGHT = 36

    def __init__(self, window, title):
        super().__init__(window)
        self.setObjectName("titleBar")
        self.window_ = window
        self.setFixedHeight(self.HEIGHT)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(_TitleIcon(title))
        row.addSpacing(9)
        self.text = QLabel(title)
        row.addWidget(self.text, 1)
        for kind, handler in (("min", window.minimise), ("max", window.toggle_maximise),
                              ("close", window.close)):
            row.addWidget(ChromeButton(kind, window, handler))
        self._drag = None
        self._moved = False

    def _at(self, e):
        """The pointer, in the clone's screen coordinates."""
        return self.window_.pos() + self.mapTo(self.window_, e.position().toPoint())

    def mousePressEvent(self, e):
        self.window_.raise_()
        if e.button() == Qt.LeftButton:
            self._drag = e.globalPosition().toPoint() - self.window_.pos()
            self._moved = False

    def mouseMoveEvent(self, e):
        if self._drag is None:
            return
        w = self.window_
        want = e.globalPosition().toPoint() - self._drag
        if w.is_maximised():
            # Pulled off the edge it filled: back to its own size, under the pointer.
            if (want - w.pos()).manhattanLength() < 10:
                return
            share = e.position().x() / max(1, self.width())
            at = self._at(e)
            w.restore_size()
            w.move(int(at.x() - w.width() * share), max(0, at.y() - self.HEIGHT // 2))
            self._drag = e.globalPosition().toPoint() - w.pos()
            want = w.pos()
        self._moved = True
        # Never dragged off the clone's screen: a window you cannot reach
        # the title of is a window you cannot close.
        want.setX(max(-w.width() + 80, min(want.x(), SCREEN_W - 80)))
        want.setY(max(0, min(want.y(), SCREEN_H - DOCK_SPACE - self.HEIGHT)))
        w.move(want)

    def mouseReleaseEvent(self, e):
        if self._drag is not None and self._moved:
            at = self._at(e)
            if at.y() <= 2:
                self.window_.snap("full")
            elif at.x() <= 2:
                self.window_.snap("left")
            elif at.x() >= SCREEN_W - 3:
                self.window_.snap("right")
        self._drag = None

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag = None
            self.window_.toggle_maximise()


class SizeGrip(QWidget):
    """The corner a window is resized by."""

    CHROME = True

    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.setFixedSize(18, 18)
        self.setCursor(Qt.SizeFDiagCursor)
        self.setAccessibleName("Resize")
        self._from = None

    def mousePressEvent(self, e):
        self._from = (e.globalPosition().toPoint(), self.window_.size())

    def mouseMoveEvent(self, e):
        if self._from is None:
            return
        w = self.window_
        moved = e.globalPosition().toPoint() - self._from[0]
        w.resize(max(w.MIN_W, min(self._from[1].width() + moved.x(), SCREEN_W - max(0, w.x()))),
                 max(w.MIN_H, min(self._from[1].height() + moved.y(),
                                  SCREEN_H - DOCK_SPACE - max(0, w.y()))))

    def mouseReleaseEvent(self, _e):
        self._from = None

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C6C0B1"))
        for x, y in ((12, 12), (7, 12), (12, 7)):
            p.drawEllipse(QPointF(x, y), 1.3, 1.3)
        p.end()


class Window(QWidget):
    """An app window. Put the app's contents into self.body.

    On the clone's screen (SHISHYA_DESKTOP_HWND set) it parents itself into
    that window and is its own frame: title bar, rounded corners, minimise,
    maximise, a corner to resize by. Run on its own — while developing, or on
    Linux — it is an ordinary window with an ordinary frame.
    """

    RADIUS, MIN_W, MIN_H = 10, 420, 280

    def __init__(self, title, width=860, height=600):
        super().__init__()
        self.setObjectName("appRoot")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.desk = int(os.environ.get("SHISHYA_DESKTOP_HWND") or 0)
        self._normal = None            # the size to go back to, while filling the screen or half
        self._placed = False
        self.bar = self.grip = None
        if self.desk:
            # One point of the desk's edge colour all round: the frame.
            outer.setContentsMargins(1, 1, 1, 1)
            self.bar = TitleBar(self, title)
            outer.addWidget(self.bar)
            height += TitleBar.HEIGHT
        self.body = QWidget()
        self.body.setObjectName("appBody")
        outer.addWidget(self.body, 1)
        if self.desk:
            self.grip = SizeGrip(self)
        # The clone's screen is 1440x900 with a floating dock along the
        # bottom; nothing opens bigger than what is left of it.
        self.resize(min(width, SCREEN_W - 40), min(height, SCREEN_H - DOCK_SPACE - 12))

    def show(self):
        if self.desk:
            self.winId()
            handle = self.windowHandle()
            handle.setParent(QWindow.fromWinId(self.desk))
            # In the middle of what the dock leaves free, stepped down and
            # right by how many windows are already open, so a second window
            # does not sit exactly on the first — and all of it on the screen,
            # where its title and its buttons can be reached.
            step = _open_on(self.desk) % 6
            free = SCREEN_H - DOCK_SPACE
            w, h = min(self.width(), SCREEN_W - 24), min(self.height(), free - 16)
            self.resize(w, h)
            self.move(max(8, min((SCREEN_W - w) // 2 + step * 30, SCREEN_W - w - 8)),
                      max(8, min((free - h) // 2 + step * 26, free - h - 8)))
            self._placed = True
        super().show()
        self.raise_()
        self._reshape()

    # ── its size on the screen ──
    def is_maximised(self):
        return self._normal is not None

    def snap(self, where):
        """Fill the screen above the dock ("full"), or its left or right half."""
        if not self.desk:
            return
        if self._normal is None:
            self._normal = self.geometry()
        area = QRect(0, 0, SCREEN_W, SCREEN_H - DOCK_SPACE)
        if where == "left":
            area.setWidth(SCREEN_W // 2)
        elif where == "right":
            area.setLeft(SCREEN_W // 2)
        self.setGeometry(area)
        self._reshape()

    def restore_size(self):
        if self._normal is not None:
            was, self._normal = self._normal, None
            self.setGeometry(was)
            self._reshape()

    def toggle_maximise(self):
        if not self.desk:
            return self.showNormal() if self.isMaximized() else self.showMaximized()
        return self.restore_size() if self._normal is not None else self.snap("full")

    def minimise(self):
        if self.desk and sys.platform == "win32":
            minimise_window(int(self.winId()))
        else:
            self.showMinimized()

    def _reshape(self):
        """Round the corners (square while it fills the screen) and keep the
        resize corner in its corner."""
        if self.grip:
            self.grip.setVisible(self._normal is None)
            self.grip.move(self.width() - 20, self.height() - 20)
            self.grip.raise_()
        if self.bar:
            self.bar.update()
        if not self._placed or sys.platform != "win32":
            return
        import ctypes
        from ctypes import wintypes
        u = _user32()
        hwnd = int(self.winId())
        if self._normal is not None:
            u.SetWindowRgn(hwnd, None, True)
            return
        # In device pixels, straight from Windows: Qt's own mask is in points,
        # which on a 200% screen makes every step of the curve two pixels.
        rect = wintypes.RECT()
        u.GetClientRect(hwnd, ctypes.byref(rect))
        d = round(2 * self.RADIUS * self.devicePixelRatioF())
        region = _libs["gdi32"].CreateRoundRectRgn(0, 0, rect.right + 1, rect.bottom + 1, d, d)
        u.SetWindowRgn(hwnd, region, True)          # Windows owns the region from here

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._reshape()

    def paintEvent(self, _e):
        if self.desk:
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(DESK_EDGE))
            p.end()

    def mousePressEvent(self, e):
        self.raise_()
        super().mousePressEvent(e)


def _dialog(parent, title, start, pattern, mode):
    """Qt's own file dialog, never the Windows one.

    The Windows dialog opens on YOUR folders — OneDrive, Desktop, Documents —
    every one of which the sandbox is refused, so it greets the clone with
    "Access is denied". Qt's dialog starts in shared/ and shows only what the
    clone can actually reach.
    """
    from PySide6.QtWidgets import QFileDialog
    d = QFileDialog(parent, title, str(start or common.SHARED), pattern)
    d.setOption(QFileDialog.DontUseNativeDialog, True)
    d.setFileMode(mode)
    d.setSidebarUrls([__import__("PySide6.QtCore", fromlist=["QUrl"]).QUrl.fromLocalFile(str(p))
                      for p in (common.WORK, common.SHARED / "inbox", common.TRAINING)
                      if p.exists()])
    return d


def open_files(parent, title, start=None, pattern="All files (*)", many=False):
    from PySide6.QtWidgets import QFileDialog
    d = _dialog(parent, title, start, pattern,
                QFileDialog.ExistingFiles if many else QFileDialog.ExistingFile)
    return [Path(p) for p in d.selectedFiles()] if d.exec() else []


def save_file(parent, title, suggested, pattern="All files (*)"):
    from PySide6.QtWidgets import QFileDialog
    d = _dialog(parent, title, Path(suggested).parent, pattern, QFileDialog.AnyFile)
    d.setAcceptMode(QFileDialog.AcceptSave)
    d.selectFile(Path(suggested).name)
    return Path(d.selectedFiles()[0]) if d.exec() and d.selectedFiles() else None


def open_app(name, *args):
    """Open another of the clone's apps on its screen.

    On Windows this is a request to the host, never a process started from
    in here: an AppContainer process may not create another, so a Popen
    from inside failed silently and the app never came. The host starts it
    into the same container and job (host/winhost.py). One file per request,
    so two quick picks both land."""
    if sys.platform == "win32":
        req = common.SHARED / f".launch-{time.time_ns()}.json"
        req.write_text(json.dumps({"app": name, "args": [str(a) for a in args]}),
                       encoding="utf-8")
        return True
    import subprocess
    subprocess.Popen([sys.executable, str(Path(__file__).parent / "apps" / name),
                      *map(str, args)])
    return True


def _open_on(desk):
    """How many app windows are already on the clone's screen."""
    if sys.platform != "win32":
        return 0
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    count = [0]
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        if user32.GetParent(h) == desk and user32.IsWindowVisible(h):
            count[0] += 1
        return True
    user32.EnumChildWindows(desk, proc(each), 0)
    return max(0, count[0] - 1)            # the taskbar is a child window too


def run(window):
    """Show the window and run until it is closed."""
    window.show()
    return QApplication.instance().exec()


# ─── the recorder ───────────────────────────────────────────────────────────
# Same trace format as vm/recorder.py, so host/synth.py reads both without
# knowing which wrote it: one JSON object per line, kind "step", with the
# event named in AT-SPI's vocabulary (object:state-changed:focused, typed…)
# and a target of {name, role, path, text}.
#
# Teaching is switched on by a file, traces/.recording, written by the
# Shishya app when somebody presses Teach me. Every app polls it; each writes
# its own trace-<pid>.jsonl, and the Shishya app merges them in time order
# when the lesson ends. No app can write into another's file, so there is no
# lock to get wrong.

FLAG = common.TRACES / ".recording"

ROLES = ((QPushButton, "push button"), (QCheckBox, "check box"), (QComboBox, "combo box"),
         (QLineEdit, "text"), (QPlainTextEdit, "text"), (QTextEdit, "text"),
         (QAbstractItemView, "table"), (QAbstractButton, "push button"), (QLabel, "label"))


def role_of(w):
    for kind, name in ROLES:
        if isinstance(w, kind):
            if name == "table" and hasattr(w, "currentItem"):
                return "table cell"
            return name
    return "panel"


def name_of(w):
    """The name a person would use. A table's name is its current cell's
    reference, because that is what a step about a spreadsheet is about."""
    ref = getattr(w, "current_ref", None)
    if callable(ref):
        try:
            return ref() or ""
        except Exception:
            pass
    return (w.accessibleName() or (w.text() if hasattr(w, "text") and callable(w.text)
                                  and isinstance(w, (QAbstractButton, QLabel)) else "")
            or w.objectName() or "")


def describe(w):
    if w is None:
        return None
    path, node = [], w
    while node is not None and len(path) < 8:
        path.append({"role": role_of(node), "name": name_of(node)})
        node = node.parentWidget()
    text = None
    if isinstance(w, QLineEdit):
        text = w.text()[:400]
    elif isinstance(w, (QPlainTextEdit, QTextEdit)):
        text = w.toPlainText()[:400]
    return {"name": name_of(w), "role": role_of(w), "path": list(reversed(path)), "text": text}


def _focus_target(w):
    """The control a click on w gives the keyboard to: w itself, or the
    nearest ancestor that takes focus by click (a table's viewport does not;
    the table does)."""
    node = w
    while node is not None:
        if node.isEnabled() and node.focusPolicy() & Qt.ClickFocus:
            return node
        if node.isWindow():
            return None
        node = node.parentWidget()
    return None


def _is_inside(w, outer):
    node = w
    while node is not None:
        if node is outer:
            return True
        node = node.parentWidget()
    return False


def _owning_grid(w):
    node = w
    while node is not None:
        if callable(getattr(node, "current_ref", None)):
            return node
        node = node.parentWidget()
    return None


PLACEMENT = common.SHARED / ".screen-mode"


def embedded_inside():
    """Is the clone's screen being shown inside Shishya's window right now?"""
    if os.environ.get("SHISHYA_SCREEN") != "embedded":
        return False
    try:
        return PLACEMENT.read_text(encoding="utf-8").strip() != "out"
    except OSError:
        return True


def cloak(hwnd, on=True):
    if sys.platform != "win32":
        return
    import ctypes
    flag = ctypes.c_int(1 if on else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(int(hwnd), 13, ctypes.byref(flag),   # DWMWA_CLOAK
                                               ctypes.sizeof(flag))


class CloakPopups(QObject):
    """Keep the clone's own menus and dialogs off the person's desktop.

    The clone's screen lives inside Shishya's window, cloaked. A menu, a
    drop-down or a dialog is a window of its own, though, and would appear
    on the real desktop over whatever the person was doing. Each one is
    cloaked as it is shown — it still draws, and Shishya paints it into the
    picture of the clone's screen — unless the screen has been popped out.
    """

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow() \
                and not getattr(obj, "desk", 0) and embedded_inside():
            if obj.windowHandle() is None or not obj.windowHandle().parent():
                cloak(obj.winId(), True)
        return False


class FocusOnClick(QObject):
    """Give the keyboard to what was clicked, even in a window Windows does
    not think is active.

    The clone's windows are children of its screen, and the screen is often
    not the foreground window — you are in the panel, taking the wheel
    through its picture. A click still arrives; Qt just does not move focus
    for a window it believes is inactive, so the next keystroke went to
    whichever control had focus before. This does what the click meant.
    """

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.MouseButtonPress and isinstance(obj, QWidget):
            top = obj.window()
            if isinstance(top, Window) and top.desk:
                top.raise_()              # a click anywhere in it, not only on its title
            target = _focus_target(obj)
            if target is not None and QApplication.focusWidget() is not target:
                target.setFocus(Qt.MouseFocusReason)
        return False


def _chrome(w):
    node = w
    while node is not None:
        if getattr(node, "CHROME", False):
            return True
        node = node.parentWidget()
    return False


class Recorder(QObject):
    COMMIT = {Qt.Key_Return: True, Qt.Key_Enter: True, Qt.Key_Tab: True,
              Qt.Key_Backtab: True, Qt.Key_Escape: False}

    _me = None

    @classmethod
    def install(cls, app, name):
        cls._me = cls(app, name)
        app.installEventFilter(cls._me)

    def __init__(self, app, name):
        super().__init__(app)
        self.appname = name
        self.run = None
        self.fh = None
        self.n = 0
        self.buffer = ""
        self.typing_at = None
        self.last_focus = None
        self.typed_at = 0.0
        self.last = None
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.check)
        self.poll.start(600)
        self.check()
        # Started while a lesson was being taught: opening this app is part
        # of the job. Said with its first step, so an app opened and never
        # used — or the Teach app itself, which records nothing — says nothing.
        self.opened = bool(self.fh)

    # ── on and off ──
    def check(self):
        try:
            run = json.loads(FLAG.read_text(encoding="utf-8")).get("run")
        except (OSError, ValueError):
            run = None
        if run == self.run:
            return
        self.opened = False          # a lesson begun after this app opened
        if self.fh:
            self.flush()
            self.fh.close()
            self.fh = None
        self.run = run
        if run:
            folder = common.TRACES / run
            (folder / "steps").mkdir(parents=True, exist_ok=True)
            self.fh = open(folder / f"trace-{os.getpid()}.jsonl", "a", encoding="utf-8")

    def write(self, obj):
        if not self.fh:
            return
        self.fh.write(json.dumps(obj, ensure_ascii=False) + "\n")
        self.fh.flush()

    def shot(self, widget):
        """A picture of the window the step happened in — evidence for the
        synthesiser, as scrot's screenshot was."""
        try:
            name = f"{os.getpid()}-{self.n:04d}.png"
            widget.window().grab().save(str(common.TRACES / self.run / "steps" / name), "PNG", 60)
            return name
        except Exception:
            return None

    def began(self):
        if self.opened and self.fh:
            self.opened = False
            self.n += 1
            self.write({"kind": "step", "i": self.n, "t": round(time.time() - 0.001, 3),
                        "event": "app:opened", "app": self.appname, "detail": None, "shot": None,
                        "target": {"name": self.appname, "role": "application", "path": [], "text": None}})

    def step(self, event, target, widget=None, detail=None):
        if not self.fh:
            return
        self.began()
        self.n += 1
        self.write({"kind": "step", "i": self.n, "t": round(time.time(), 3), "event": event,
                    "target": target, "app": self.appname, "detail": detail,
                    "shot": self.shot(widget) if widget is not None else None})

    @classmethod
    def note(cls, event, widget, detail=None):
        """For an app to report a step the filter cannot see — a spreadsheet
        cell becoming current, which moves no keyboard focus at all."""
        me = cls._me
        if me and me.fh and widget is not None:
            if event == "object:selection-changed":
                fp = (event, name_of(widget))
                if fp == me.last:
                    return
                me.last = fp
            me.step(event, describe(widget), widget, detail)

    # ── what was typed ──
    def flush(self, committed=True):
        text, where = self.buffer, self.typing_at
        self.buffer, self.typing_at = "", None
        if text and self.fh:
            self.began()
            self.n += 1
            self.write({"kind": "step", "i": self.n, "t": round(time.time(), 3),
                        "event": "typed" if committed else "typed-then-cancelled",
                        "target": where, "app": self.appname, "detail": text, "shot": None})

    def focused(self, w):
        """A control became the one being worked on."""
        # The first key into a cell opens an editor, which takes focus of its
        # own; anything within a moment of a keystroke is that, not the
        # person moving on — the same rule as recorder.py.
        if self.buffer and time.time() - self.typed_at > 1.2:
            self.flush()
        if _owning_grid(w) is not None:
            # A spreadsheet's own focus — the grid, or the editor it opens in
            # a cell — says nothing the cell's selection does not say better,
            # and the grid's name at the moment of the click is the cell it is
            # LEAVING. The selection note records where the person went.
            return
        fp = ("focus", name_of(w), role_of(w))
        if fp != self.last:
            self.last = fp
            self.last_focus = describe(w)
            self.step("object:state-changed:focused", self.last_focus, w)

    def eventFilter(self, obj, ev):
        if not self.fh or not isinstance(obj, QWidget):
            return False
        kind = ev.type()
        try:
            if kind == QEvent.FocusIn and not _chrome(obj) \
                    and ev.reason() != Qt.ActiveWindowFocusReason:
                # Not a window being activated handing focus back to its
                # first or last control: that is the window, not the person
                # (it was recorded as "moved to Open" on every new Sheets,
                # and came back from the model as a step opening a file).
                self.focused(obj)
            elif kind == QEvent.MouseButtonPress and not _chrome(obj):
                # A window on the clone's screen that Windows does not think
                # is active gets its clicks but sends no FocusIn — so the
                # click itself says where the person's attention went.
                target = _focus_target(obj)
                if target is not None and ev.timestamp() != getattr(self, "_press", None):
                    self._press = ev.timestamp()
                    self.focused(target)
            elif kind == QEvent.KeyPress and not _chrome(obj) \
                    and obj is QApplication.focusWidget():
                # Only at the focused widget: an application-wide filter sees
                # one key event once for every widget it propagates through,
                # and counting each would type every character three times.
                # And once only: the first key into a cell reaches the grid,
                # which opens an editor and hands the same key to it.
                stamp = (ev.timestamp(), ev.key(), ev.text())
                prev = getattr(self, "_key", None)
                if prev and prev[0] == stamp and _is_inside(obj, prev[1]):
                    return False
                self._key = (stamp, obj)
                key = ev.key()
                if key in self.COMMIT:
                    self.flush(committed=self.COMMIT[key])
                elif key == Qt.Key_Backspace:
                    self.buffer = self.buffer[:-1]
                elif ev.text() and ev.text().isprintable():
                    if not self.typing_at:
                        # A cell editor is a nameless line edit inside the
                        # grid; what was typed into is the cell.
                        grid = _owning_grid(obj)
                        self.typing_at = describe(grid or obj) or self.last_focus
                    self.buffer += ev.text()
                    self.typed_at = time.time()
            elif kind == QEvent.MouseButtonRelease and isinstance(obj, QAbstractButton) \
                    and not _chrome(obj) and obj.isEnabled():
                self.flush()
                self.step("object:clicked", describe(obj), obj)
            elif kind == QEvent.WindowActivate and obj.isWindow() and not _chrome(obj):
                self.step("window:activate", {"name": obj.windowTitle(), "role": "frame",
                                              "path": [], "text": None})
        except Exception as e:                               # noqa: BLE001
            self.write({"kind": "error", "i": self.n, "detail": repr(e)})
        return False                      # never swallow anything: we observe


def merge_trace(run_dir, label):
    """Every app's part of a lesson, as one trace in time order. Written by
    whoever ends the lesson, after every app has had a moment to flush."""
    run_dir = Path(run_dir)
    steps = []
    for part in sorted(run_dir.glob("trace-*.jsonl")):
        for line in part.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("kind") == "step":
                steps.append(row)
    steps.sort(key=lambda r: r.get("t", 0))
    started = steps[0]["t"] if steps else time.time()
    with open(run_dir / "trace.jsonl", "w", encoding="utf-8") as out:
        out.write(json.dumps({"kind": "meta", "label": label, "run": run_dir.name,
                              "started": started, "screen": "1440x900",
                              "recorder": "qt"}, ensure_ascii=False) + "\n")
        for i, row in enumerate(steps, 1):
            row["i"] = i
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
        out.write(json.dumps({"kind": "meta", "ended": time.time(), "steps": len(steps)}) + "\n")
    return len(steps)
