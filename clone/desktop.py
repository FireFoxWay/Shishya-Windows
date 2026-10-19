#!/usr/bin/env python3
"""
Shishya — the clone's screen. Runs INSIDE the sandbox.

On the Mac this was a GTK desktop on a 1440x900 Xvfb display, watched
through noVNC. On Windows it is one window, 1440x900 points, and every app
the clone opens parents itself into it (kit.Window). That keeps what made
the VM's display worth having:

  - one screen the panel can show and you can take over, with the clone's
    work on it and nothing of yours;
  - a fixed size, because taught procedures reference on-screen layout and a
    screen that resized with your monitor would quietly invalidate them;
  - a clear line on your own desktop between the clone's windows and yours.

The look is "the apprentice's desk": deep ink, the शि mark in the corner,
a few cards on the left that are true (today's takings, stock, what Shishya
is doing), and one floating dock — the Shishya orb, the windows that are
open, the time. The orb opens the start panel: search, six pinned apps,
recent work; everything else is one click further, under All apps. The
same colours and icons as the home page, so the two read as one product.

    pythonw desktop.py
"""

import ctypes
import datetime as dt
import json
import math
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

# The bundled runtime is an embeddable Python, which does not put a script's
# own folder on the path; kit sits beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import kit   # noqa: E402
from PySide6.QtCore import QDateTime, QPoint, QRect, QRectF, Qt, QTimer  # noqa: E402
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QLinearGradient,  # noqa: E402
                           QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,  # noqa: E402
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

import common      # noqa: E402

W, H = 1440, 900
DOCK_H, DOCK_GAP = 60, 14
RESERVED = DOCK_H + 2 * DOCK_GAP       # the strip along the bottom apps keep clear of
APPS = Path(__file__).resolve().parent / "apps"
CONFIG = common.SHARED / ".desktop.json"
LOOK = {"wallpaper": "ink", "accent": "#0078d4", "wallmark": "शि", "fps": 12}
LOOK_VERSION = 2                       # 2: the apprentice's desk

# ─── palette ────────────────────────────────────────────────────────────────
# Ink for the desk, and the home page's own tints for the things on it.
INK, INK_LOW, CARD, EDGE = "#171B30", "#10132A", "#1E2340", "#2C3256"
TEXT, MUTED, MARK = "#FBF7EC", "#A9A79C", "#1D2240"
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

# (name, app, icon, tint). Pinned: the six a counter actually reaches for.
PINNED = [
    ("Shishya", "chat_app.py", "chat", "butter"),
    ("Billing", "billing_app.py", "bill", "butter"),
    ("Inbox", "inbox_app.py", "inbox", "mint"),
    ("Files", "files_app.py", "folder", "paper"),
    ("Teach", "shishya_app.py", "teach", "lav"),
    ("Make", "make_app.py", "doc", "peach"),
]
# Everything, in the order the work flows: receive, read, teach, make, money,
# and the machine itself.
ALL_APPS = PINNED + [
    ("Findings", "findings_app.py", "find", "peach"),
    ("Reports", "reports_app.py", "chart", "peach"),
    ("Training data", "training_app.py", "book", "lav"),
    ("Sheets", "sheet_app.py", "sheet", "mint"),
    ("Code", "code_app.py", "code", "paper"),
    ("VS Code", "vscode_app.py", "code", "lav"),
    ("Banking", "bank_app.py", "bank", "mint"),
    ("Credit", "credit_app.py", "card", "mint"),
    ("Work folder", ("files_app.py", str(common.WORK)), "folder", "paper"),
    ("Lessons", ("files_app.py", str(common.TRACES)), "book", "lav"),
    ("Activity", "activity_app.py", "pulse", "paper"),
    ("Browser", "browser_app.py", "globe", "paper"),
    ("Task manager", "system_app.py", "gauge", "paper"),
    ("Models", "models_app.py", "model", "paper"),
    ("Settings", "settings_app.py", "sliders", "paper"),
]

EMBEDDED = os.environ.get("SHISHYA_SCREEN") == "embedded"
WATCHING = common.SHARED / ".watching"      # touched by the host while it shows us
PLACEMENT = common.SHARED / ".screen-mode"  # "in": inside Shishya's window; "out": popped out

STATES = {"idle": "Waiting for you", "working": "Working on a job",
          "wheel": "You have the wheel", "needs": "Needs your answer"}


def cloak(hwnd, on):
    """Hide a window from the person without stopping it drawing.

    Moving it off every monitor was the first idea, and Windows simply stops
    painting a window nobody could see — the picture came back black. A
    cloaked window is what Windows uses for apps on another virtual desktop:
    it keeps rendering, takes no clicks and is not shown. Only the window's
    own process may cloak it, so the screen does this itself, on request.
    """
    if sys.platform != "win32":
        return
    flag = ctypes.c_int(1 if on else 0)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(int(hwnd), 13, ctypes.byref(flag),   # DWMWA_CLOAK
                                               ctypes.sizeof(flag))


def watched():
    """Is anybody looking? Embedded, the host touches .watching each time it
    paints this screen into the home page; nobody looking means no reason to
    animate anything. On its own on a monitor, it is always looked at."""
    if not EMBEDDED:
        return True
    try:
        return time.time() - WATCHING.stat().st_mtime < 4
    except OSError:
        return False


def read_look():
    """The desk's settings. A config from before this look named the old
    starfield as a default nobody chose; it moves to the new desk once."""
    try:
        look = {**LOOK, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        look = dict(LOOK)
    if look.get("look_version", 0) < LOOK_VERSION:
        look.update(wallpaper="ink", wallmark="शि", look_version=LOOK_VERSION)
        try:
            CONFIG.write_text(json.dumps(look, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return look


def launch(target, *args):
    """Start one of the clone's apps on this screen."""
    if not (APPS / target).exists():
        return False
    # Through the host (kit.open_app), which also decides whether the
    # browser gets the web — the one decision the sandbox cannot make.
    return kit.open_app(target, *args)


def open_entry(target):
    return launch(*target) if isinstance(target, tuple) else launch(target)


# ─── drawing ────────────────────────────────────────────────────────────────

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
    p.drawPath(_path(ICONS.get(icon, ICONS["grid"])))
    p.restore()


_paths = {}


def _path(d):
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


def paint_desk(p, offset=QPoint(0, 0), live=None):
    """The desk itself — ink, a low glow, the mark. Drawn by the screen, and
    by the dock and the start panel behind their own rounded corners, so the
    corners show the desk and not a square of something else."""
    p.save()
    p.translate(-offset)
    if live is not None:
        live.draw(p, W, H)
    else:
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, QColor(INK))
        g.setColorAt(1, QColor(INK_LOW))
        p.fillRect(0, 0, W, H, g)
        glow = QRadialGradient(W * 0.62, H * 0.42, W * 0.5)
        glow.setColorAt(0, QColor(46, 52, 98, 120))
        glow.setColorAt(1, QColor(46, 52, 98, 0))
        p.fillRect(0, 0, W, H, glow)
    p.restore()


class Facts:
    """What the cards on the desk say, read from the shop's own books."""

    def __init__(self):
        self.takings, self.bills, self.short, self.first_short = 0.0, 0, 0, None
        self.refresh()

    def refresh(self):
        try:
            import books
            today = dt.date.today().isoformat()
            takings, bills, voided = 0.0, set(), set()
            for r in books.read_sales():
                if (r.get("at") or "")[:10] != today:
                    continue
                takings += books.number(r.get("amount"))
                (voided if r.get("kind") == "void" else bills).add(r.get("bill"))
            self.takings, self.bills = takings, len(bills - voided)
            short = books.running_out()
            self.short = len(short)
            self.first_short = short[0] if short else None
        except Exception:                                   # noqa: BLE001
            pass


def font(px, weight=QFont.Normal, family="Segoe UI"):
    """Fonts by pixel, never by point: points follow the display's DPI, and
    the clone's screen is the same 1440x900 on every laptop."""
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def rupees(n):
    whole = f"{n:,.2f}"
    return "₹" + (whole[:-3] if whole.endswith(".00") else whole)


# ─── the start panel ────────────────────────────────────────────────────────

class Tile(QPushButton):
    """An app: its icon above its name."""

    def __init__(self, name, target, icon, tint, size=52):
        super().__init__()
        self.name, self.target, self.icon, self.tint, self.size = name, target, icon, tint, size
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(size + 36, size + 34)
        self.setFocusPolicy(Qt.StrongFocus)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 18))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        x = (self.width() - self.size) / 2
        paint_icon(p, QRectF(x, 6, self.size, self.size), self.icon, self.tint)
        p.setPen(QColor(TEXT))
        p.setFont(font(12))
        p.drawText(QRectF(0, self.size + 10, self.width(), 18), Qt.AlignHCenter | Qt.AlignTop,
                   self.name)
        p.end()


class Row(QPushButton):
    """A line in a list: a small icon, a name, an optional note."""

    def __init__(self, name, icon, tint, note=""):
        super().__init__()
        self.name, self.icon, self.tint, self.note = name, icon, tint, note
        self.setAccessibleName(name if not note else f"{name}, {note}")
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(40)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QColor(255, 255, 255, 22 if (self.underMouse() or self.hasFocus()) else 8)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 10, 10)
        paint_icon(p, QRectF(8, 8, 24, 24), self.icon, self.tint, radius=7)
        p.setPen(QColor(TEXT))
        p.setFont(font(13))
        text_w = self.width() - 44 - 8
        name = p.fontMetrics().elidedText(self.name, Qt.ElideMiddle, text_w)
        if self.note:
            p.drawText(QRectF(40, 4, text_w, 18), Qt.AlignLeft | Qt.AlignVCenter, name)
            p.setPen(QColor(MUTED))
            p.setFont(font(11))
            p.drawText(QRectF(40, 20, text_w, 16), Qt.AlignLeft | Qt.AlignVCenter, self.note)
        else:
            p.drawText(QRectF(40, 0, text_w, self.height()), Qt.AlignLeft | Qt.AlignVCenter, name)
        p.end()


def _ago(stamp):
    secs = time.time() - stamp
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    days = int(secs // 86400)
    return "yesterday" if days == 1 else f"{days} days ago"


FILE_ICON = {".xlsx": ("sheet", "mint"), ".xls": ("sheet", "mint"), ".csv": ("sheet", "mint"),
             ".pdf": ("doc", "peach"), ".docx": ("doc", "lav"), ".pptx": ("chart", "peach"),
             ".txt": ("doc", "paper"), ".md": ("doc", "paper")}


def recent_work(limit=4):
    found = []
    try:
        for f in common.WORK.rglob("*"):
            if f.is_file() and not f.name.startswith(".") and f.suffix != ".part":
                found.append((f.stat().st_mtime, f))
                if len(found) > 400:
                    break
    except OSError:
        pass
    return [f for _, f in sorted(found, reverse=True)[:limit]]


class StartPanel(QFrame):
    """Search, six pinned apps, recent work — and All apps one click away."""

    CHROME = True
    PW, PH, PH_ALL = 560, 384, 470

    def __init__(self, desktop):
        super().__init__(desktop, Qt.Popup | Qt.FramelessWindowHint)
        self.desktop = desktop
        self.setAccessibleName("Apps")
        self.setObjectName("startPanel")
        self.setFixedSize(self.PW, self.PH)
        self.setStyleSheet(f"""
            QLineEdit {{ background: {INK_LOW}; color: {TEXT}; border: 1px solid {EDGE};
                         border-radius: 12px; padding: 0 14px 0 6px; min-height: 40px;
                         font-size: 13px; selection-background-color: #3C3489; }}
            QLineEdit:focus {{ border-color: #6E74B8; }}
            QLabel {{ color: {MUTED}; font-size: 11px; background: transparent; }}
            QPushButton#link {{ background: transparent; color: {TEXT}; border: 0;
                                font-size: 12px; padding: 6px 10px; border-radius: 8px; }}
            QPushButton#link:hover, QPushButton#link:focus {{ background: rgba(255,255,255,0.08); }}
            QWidget#page {{ background: transparent; }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 14)
        outer.setSpacing(12)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search apps and your work")
        self.search.setAccessibleName("Search apps and your work")
        self.search.addAction(_glyph("search", MUTED), QLineEdit.LeadingPosition)
        self.search.textChanged.connect(self.on_search)
        self.search.returnPressed.connect(self.on_enter)
        outer.addWidget(self.search)

        self.page = QWidget()
        self.page.setObjectName("page")
        self.body = QVBoxLayout(self.page)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(8)
        outer.addWidget(self.page, 1)

        foot = QHBoxLayout()
        self.toggle = QPushButton("All apps")
        self.toggle.setObjectName("link")
        self.toggle.clicked.connect(lambda: self.show_page("all" if self.mode != "all" else "home"))
        foot.addWidget(self.toggle)
        foot.addStretch(1)
        power = QPushButton("Shut down")
        power.setObjectName("link")
        power.setAccessibleName("Shut down")
        power.clicked.connect(self.on_power)
        foot.addWidget(power)
        outer.addLayout(foot)
        self.mode = None
        self.first = None

    # ── pages ──
    def _clear(self):
        while self.body.count():
            item = self.body.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
            elif item.layout():
                _drop(item.layout())

    def _go(self, target):
        self.close()
        open_entry(target)

    def show_page(self, mode, query=""):
        self.mode = mode
        self._fit(self.PH_ALL if mode == "all" else self.PH)
        self._clear()
        self.first = None
        self.toggle.setText("Back" if mode != "home" else "All apps")
        if mode == "home":
            self.body.addWidget(QLabel("Pinned"))
            grid = QGridLayout()
            grid.setSpacing(4)
            for i, (name, target, icon, tint) in enumerate(PINNED):
                t = Tile(name, target, icon, tint)
                t.clicked.connect(lambda _=False, g=target: self._go(g))
                grid.addWidget(t, 0, i)
            self.body.addLayout(grid)
            files = recent_work()
            self.body.addSpacing(6)
            self.body.addWidget(QLabel("Recent in Work" if files else "Your work"))
            grid = QGridLayout()
            grid.setSpacing(8)
            if not files:
                r = Row("Open the Work folder", "folder", "paper", "Saved files appear here")
                r.clicked.connect(lambda: self._go(("files_app.py", str(common.WORK))))
                grid.addWidget(r, 0, 0, 1, 2)
            for i, f in enumerate(files):
                icon, tint = FILE_ICON.get(f.suffix.lower(), ("doc", "paper"))
                r = Row(f.name, icon, tint, _ago(f.stat().st_mtime))
                r.clicked.connect(lambda _=False, d=f.parent: self._go(("files_app.py", str(d))))
                grid.addWidget(r, i // 2, i % 2)
            self.body.addLayout(grid)
            self.body.addStretch(1)
            return
        # all apps, or what matches a search: one quiet two-column list
        q = query.lower().strip()
        apps = [a for a in ALL_APPS if not q or q in a[0].lower()]
        files = [f for f in recent_work(40) if q in f.name.lower()][:max(0, 8 - len(apps))] if q else []
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        n = 0
        # A search shows four rows at most; All apps shows every app, in
        # three quiet columns, in the order the work flows.
        cols = 2 if q else 3
        for name, target, icon, tint in (apps[:8] if q else apps):
            r = Row(name, icon, tint)
            r.clicked.connect(lambda _=False, g=target: self._go(g))
            grid.addWidget(r, n // cols, n % cols)
            self.first = self.first or (lambda g=target: self._go(g))
            n += 1
        for f in files:
            icon, tint = FILE_ICON.get(f.suffix.lower(), ("doc", "paper"))
            r = Row(f.name, icon, tint, "in Work")
            r.clicked.connect(lambda _=False, d=f.parent: self._go(("files_app.py", str(d))))
            grid.addWidget(r, n // cols, n % cols)
            self.first = self.first or (lambda d=f.parent: self._go(("files_app.py", str(d))))
            n += 1
        self.body.addLayout(grid)
        if not n:
            self.body.addWidget(QLabel("Nothing by that name."))
        self.body.addStretch(1)

    def on_search(self, text):
        self.show_page("search" if text.strip() else "home", text)

    def on_enter(self):
        if self.first:
            self.first()

    def on_power(self):
        self.close()
        self.desktop.dock.on_power()

    def _fit(self, height):
        """Grow upward from just above the dock."""
        self.setFixedSize(self.PW, height)
        x = (W - self.PW) // 2
        y = H - RESERVED - height + DOCK_GAP - 6
        self.move(self.desktop.mapToGlobal(QPoint(x, y)))
        self.update()

    def open(self):
        self.search.clear()
        self.show_page("home")
        self.show()
        self.raise_()
        self.activateWindow()
        self.search.setFocus()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # The desk behind the rounded corners, so they are corners and not
        # a square of something else (a popup cannot be see-through here).
        origin = self.desktop.mapFromGlobal(self.mapToGlobal(QPoint(0, 0)))
        paint_desk(p, origin, self.desktop.live)
        p.setPen(QPen(QColor(EDGE), 1))
        p.setBrush(QColor(CARD))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 20, 20)
        p.end()


def _glyph(name, colour, px=18):
    """One of the line icons as a QIcon, for a field's leading action."""
    from PySide6.QtGui import QIcon, QPixmap
    pm = QPixmap(px * 2, px * 2)
    pm.setDevicePixelRatio(2)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.scale(px / 24, px / 24)
    pen = QPen(QColor(colour), 2)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.drawPath(_path(ICONS[name]))
    p.end()
    return QIcon(pm)


def _drop(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _drop(item.layout())


# ─── the dock ───────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32 if sys.platform == "win32" else None
EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM) \
    if sys.platform == "win32" else None


def open_windows(desk):
    """The app windows parented into this screen, newest last. Asked of
    Windows rather than tracked: an app the panel opened, or the executor
    opened, must appear here too."""
    out = []
    if not user32:
        return out

    def each(h, _):
        if user32.GetParent(h) == desk and user32.IsWindowVisible(h):
            buf = ctypes.create_unicode_buffer(200)
            user32.GetWindowTextW(h, buf, 200)
            if buf.value:
                out.append((int(h), buf.value))
        return True
    user32.EnumChildWindows(desk, EnumProc(each), 0)
    return out


def raise_window(hwnd):
    if user32:
        user32.ShowWindow(hwnd, 9)                               # SW_RESTORE
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # top
        user32.SetFocus(hwnd)


def icon_for(title):
    t = title.lower()
    for name, _target, icon, tint in ALL_APPS:
        if name.lower() in t or t.startswith(name.lower()[:5]):
            return icon, tint
    return "grid", "paper"


class Orb(QPushButton):
    """Shishya, in the dock. Opens the start panel, and shows what the clone
    is doing without a word: still when it waits, a turning ring while it
    works, a dashed ring while you drive, a warm pulse when it needs you."""

    def __init__(self):
        super().__init__()
        self.state, self.phase = "idle", 0.0
        self.setFixedSize(44, 44)
        self.setCursor(Qt.PointingHandCursor)
        self.setAccessibleName("Apps")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._step)

    def set_state(self, state):
        self.state = state
        self.setToolTip(f"Shishya — {STATES.get(state, STATES['idle']).lower()}. Click for apps.")
        self.setAccessibleDescription(STATES.get(state, STATES["idle"]))
        moving = state in ("working", "needs")
        if moving and not self.timer.isActive():
            self.timer.start(70)
        elif not moving:
            self.timer.stop()
        self.update()

    def _step(self):
        if watched():
            self.phase = (self.phase + 0.07) % 1.0
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QRectF(self.rect()).adjusted(7, 7, -7, -7)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawEllipse(QRectF(self.rect()).adjusted(1, 1, -1, -1))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(TINT["butter"][0]))
        p.drawEllipse(c.adjusted(4, 4, -4, -4))
        ring = QRectF(c)
        if self.state == "working":
            p.setPen(QPen(QColor(EDGE), 3))
            p.drawEllipse(ring)
            pen = QPen(QColor(TINT["mint"][0]), 3)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(ring, int(-self.phase * 360 * 16), 110 * 16)
        elif self.state == "needs":
            alpha = int(150 + 105 * (0.5 + 0.5 * math.sin(self.phase * 2 * math.pi)))
            col = QColor(TINT["peach"][0])
            col.setAlpha(alpha)
            p.setPen(QPen(col, 3))
            p.drawEllipse(ring)
        elif self.state == "wheel":
            pen = QPen(QColor(TEXT), 2, Qt.DashLine)
            p.setPen(pen)
            p.drawEllipse(ring)
        else:
            p.setPen(QPen(QColor(TINT["mint"][0]), 3))
            p.drawEllipse(ring)
        p.end()


class TaskButton(QPushButton):
    def __init__(self, hwnd, title):
        super().__init__()
        self.hwnd, self.title = hwnd, title
        self.icon_, self.tint = icon_for(title)
        self.top = False
        self.setAccessibleName(title)
        self.setToolTip(title)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        f = font(13)
        self.label = title if len(title) <= 16 else title[:15] + "…"
        from PySide6.QtGui import QFontMetrics
        self.setFixedWidth(44 + QFontMetrics(f).horizontalAdvance(self.label) + 14)
        self.clicked.connect(lambda: raise_window(self.hwnd))

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 20))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 12, 12)
        paint_icon(p, QRectF(8, 8, 28, 28), self.icon_, self.tint, radius=8)
        p.setPen(QColor(TEXT))
        p.setFont(font(13))
        p.drawText(QRectF(44, 0, self.width() - 48, self.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, self.label)
        if self.top:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(TINT["mint"][0]))
            p.drawRoundedRect(QRectF(22 - 6, self.height() - 4, 12, 3), 1.5, 1.5)
        p.end()


class Dock(QWidget):
    """One floating bar: the orb, the open windows, the time."""

    CHROME = True          # the recorder ignores it: our furniture, not the task

    def __init__(self, desktop):
        super().__init__(desktop)
        self.desktop = desktop
        self.setObjectName("dock")
        self.setAccessibleName("Dock")
        # A window of its own, so it can sit ABOVE the apps' windows: they are
        # child windows of the screen, and a plain Qt widget is painted
        # underneath every child window, however it is stacked in Qt.
        self.setAttribute(Qt.WA_NativeWindow, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 16, 8)
        row.setSpacing(4)
        self.orb = Orb()
        self.orb.clicked.connect(self.on_start)
        row.addWidget(self.orb)
        self.sep1 = QFrame()
        self.sep1.setFixedSize(1, 26)
        self.sep1.setStyleSheet(f"background: {EDGE};")
        row.addWidget(self.sep1)
        self.tasks = QHBoxLayout()
        self.tasks.setSpacing(2)
        row.addLayout(self.tasks)
        self.sep2 = QFrame()
        self.sep2.setFixedSize(1, 26)
        self.sep2.setStyleSheet(f"background: {EDGE};")
        row.addWidget(self.sep2)
        self.clock = QLabel()
        self.clock.setStyleSheet(f"color: {TEXT}; font-size: 12px; padding-left: 8px;"
                                 " background: transparent;")
        self.clock.setAccessibleName("Time")
        row.addWidget(self.clock)
        self.panel = StartPanel(desktop)
        self.shown = None
        self.state = None
        tick = QTimer(self)
        tick.timeout.connect(self.tick)
        tick.start(1000)
        self.tick()

    def restyle(self, _accent):
        self.update()

    def recentre(self):
        hint = self.sizeHint()
        w = max(200, hint.width())
        self.setGeometry((W - w) // 2, H - DOCK_H - DOCK_GAP, w, DOCK_H)
        self.update()

    def tick(self):
        now = QDateTime.currentDateTime()
        self.clock.setText(now.toString("HH:mm") + "   " + now.toString("ddd d MMM"))
        try:
            state = common.STATE.read_text(encoding="utf-8").strip() or "idle"
        except OSError:
            state = "idle"
        if state != self.state:
            self.state = state
            self.orb.set_state(state)
            self.desktop.set_state(state)

        # Always on top of the apps: a window dragged down must not cover it.
        if user32:
            user32.SetWindowPos(int(self.winId()), 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

        # Rebuilt only when the list changed — a dock that rebuilds every
        # second churns the tree the executor reads, for nothing.
        mine = int(self.winId())
        windows = [w for w in open_windows(int(self.desktop.winId())) if w[0] != mine]
        if windows != self.shown:
            self.shown = windows
            _drop(self.tasks)
            for hwnd, title in windows[-6:]:
                self.tasks.addWidget(TaskButton(hwnd, title))
            self.sep2.setVisible(bool(windows))
            QTimer.singleShot(0, self.recentre)
        # which one is on top: the last child in Windows' z-order is the first found
        top = user32.GetWindow(int(self.desktop.winId()), 5) if user32 else 0   # GW_CHILD
        while top and (top == mine or not user32.IsWindowVisible(top)):
            top = user32.GetWindow(top, 2)                                    # GW_HWNDNEXT
        for i in range(self.tasks.count()):
            b = self.tasks.itemAt(i).widget()
            if isinstance(b, TaskButton) and b.top != (b.hwnd == top):
                b.top = b.hwnd == top
                b.update()

    def on_start(self):
        if self.panel.isVisible():
            self.panel.close()
        else:
            self.panel.open()

    def on_power(self):
        answer = QMessageBox.question(
            self.desktop, "Shut down the sandbox?",
            "Anything the clone has not saved to Work will be lost.",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Ok:
            # The clone cannot stop its own sandbox — it does not own its job.
            # Shutting down is a request it makes of the host, as on the Mac.
            (common.SHARED / ".shutdown-requested").write_text("1", encoding="utf-8")

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        paint_desk(p, self.pos(), self.desktop.live)
        p.setPen(QPen(QColor(EDGE), 1))
        p.setBrush(QColor(CARD))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 18, 18)
        p.end()


# ─── the screen ─────────────────────────────────────────────────────────────

CARD_X, CARD_W = 28, 248


class Desktop(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Shishya — the clone's screen")
        self.setAccessibleName("Desktop")
        self.setFixedSize(W, H)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.look = None
        self.live = None
        self.live_name = None
        self.rate = 12
        self.state = "idle"
        self.facts = Facts()
        self.cards = {}
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.dock = Dock(self)
        self.dock.recentre()
        self.wallmark = "शि"
        follow = QTimer(self)
        follow.timeout.connect(self.follow)
        follow.start(1000)
        books = QTimer(self)
        books.timeout.connect(self.reread)
        books.start(20000)
        self.follow()

    # ── where it is: inside Shishya's window, or popped out ──
    placed = None

    def place(self, mode):
        if mode == self.placed:
            return
        if self.isVisible():
            self.placed = mode          # before it is shown, do it again after
        avail = QGuiApplication.primaryScreen().availableGeometry()
        # Centred on the monitor either way: cloaked, it still has to be on a
        # monitor for Windows to keep painting it.
        self.move(avail.x() + max(0, (avail.width() - W) // 2),
                  avail.y() + max(0, (avail.height() - H) // 2))
        cloak(self.winId(), mode != "out")
        if mode == "out":
            self.raise_()
            self.activateWindow()

    # ── look ──
    def follow(self):
        if EMBEDDED:
            try:
                self.place(PLACEMENT.read_text(encoding="utf-8").strip() or "in")
            except OSError:
                self.place("in")
        look = read_look()
        if look == self.look:
            self._retime()
            return
        self.look = look
        self.wallmark = look.get("wallmark", "शि")
        chosen = look.get("wallpaper", "ink")
        import wallpaper
        if chosen in wallpaper.LIVE:
            if chosen != self.live_name:
                cls, self.rate = wallpaper.LIVE[chosen]
                self.live, self.live_name = cls(), chosen
        else:
            self.live, self.live_name = None, None
        self.fps = int(look.get("fps", 0) or 0)
        self._retime()
        self.update()
        self.dock.update()

    def reread(self):
        self.facts.refresh()
        self.update(QRect(0, 0, CARD_X + CARD_W + 8, H))

    def set_state(self, state):
        """Still while the model works: the cores are its."""
        self.state = state
        self._retime()
        self.update(QRect(0, 0, CARD_X + CARD_W + 8, H))

    def _retime(self):
        want = (self.live is not None and self.state != "working" and not self.isMinimized()
                and watched())
        if want and not self.timer.isActive():
            self.timer.start(int(1000 / (self.fps or self.rate or 12)))
        elif not want and self.timer.isActive():
            self.timer.stop()

    def step(self):
        if self.live:
            self.live.step()
            self.update()
            self.dock.update()

    # ── the cards: true things, and a door to where they come from ──
    def mousePressEvent(self, e):
        for target, rect in self.cards.items():
            if rect.contains(e.position().toPoint()):
                open_entry(target)
                return

    def _card(self, p, y, h, fill=CARD, edge=True):
        r = QRectF(CARD_X, y, CARD_W, h)
        p.setPen(QPen(QColor(EDGE), 1) if edge else Qt.NoPen)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(r, 16, 16)
        return r

    def _text(self, p, rect, text, size, colour, weight=QFont.Normal, flags=Qt.AlignLeft | Qt.AlignTop):
        p.setFont(font(size, weight))
        p.setPen(QColor(colour))
        p.drawText(rect, flags, text)

    def paint_cards(self, p):
        self.cards = {}
        now = dt.datetime.now()
        y = 28
        r = self._card(p, y, 104)
        self._text(p, r.adjusted(18, 12, -18, 0), now.strftime("%H:%M"), 40, TEXT, QFont.DemiBold)
        self._text(p, r.adjusted(18, 68, -18, 0), now.strftime("%A, %d %B").replace(" 0", " "),
                   13, MUTED)
        y += 104 + 12

        fill, ink = TINT["butter"]
        r = self._card(p, y, 96, fill, edge=False)
        self._text(p, r.adjusted(18, 12, -18, 0), "Today's takings", 12, ink)
        self._text(p, r.adjusted(18, 32, -18, 0), rupees(self.facts.takings), 26, ink, QFont.DemiBold)
        bills = self.facts.bills
        self._text(p, r.adjusted(18, 64, -18, 0),
                   "No bills yet today" if not bills else f"{bills} bill{'s' if bills != 1 else ''}",
                   12, ink)
        self.cards["billing_app.py"] = r.toRect()
        y += 96 + 12

        fill, ink = TINT["mint"]
        r = self._card(p, y, 78, fill, edge=False)
        if self.facts.short:
            first = self.facts.first_short
            left = int(first["stock"]) if first else 0
            self._text(p, r.adjusted(18, 12, -18, 0), f"Low on stock · {self.facts.short}", 12, ink)
            p.setFont(font(15, QFont.DemiBold))
            name = p.fontMetrics().elidedText(first["name"], Qt.ElideRight, CARD_W - 120) if first else ""
            self._text(p, r.adjusted(18, 32, -18, 0),
                       f"{name} · {left} left" if left > 0 else f"{name} · out", 15, ink, QFont.DemiBold)
        else:
            self._text(p, r.adjusted(18, 12, -18, 0), "Stock", 12, ink)
            self._text(p, r.adjusted(18, 32, -18, 0), "Nothing running low", 15, ink, QFont.DemiBold)
        self.cards["findings_app.py"] = r.toRect()
        y += 78 + 12

        r = self._card(p, y, 78)
        self._text(p, r.adjusted(18, 12, -18, 0), "Shishya is", 12, MUTED)
        self._text(p, r.adjusted(18, 32, -18, 0), STATES.get(self.state, STATES["idle"]).lower(),
                   15, TEXT, QFont.DemiBold)
        self.cards["activity_app.py"] = r.toRect()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        paint_desk(p, QPoint(0, 0), self.live)
        # the mark: शि, large and quiet in the corner
        if self.wallmark:
            p.setFont(font(300, QFont.DemiBold, "Nirmala UI"))
            p.setPen(QColor(MARK) if self.live is None else QColor(255, 255, 255, 18))
            p.drawText(QRect(0, 0, W - 56, H - RESERVED + 10), Qt.AlignRight | Qt.AlignBottom,
                       self.wallmark)
        self.paint_cards(p)
        p.end()


def main():
    for d in (common.WORK, common.LESSONS, common.TRAINING, common.TRACES):
        d.mkdir(parents=True, exist_ok=True)
    app = kit.application("Desktop")
    desk = Desktop()
    if EMBEDDED:
        # One window for the person: Shishya's own. The clone's screen is
        # still a real window — its apps are parented into it and the hands
        # drive it — but it is cloaked, has no frame and no taskbar button,
        # and Shishya shows it inside the home page. "Pop out" there uncloaks
        # it onto the monitor when somebody wants a real mouse on it.
        desk.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        PLACEMENT.write_text("in", encoding="utf-8")
    desk.show()
    if EMBEDDED:
        desk.place("in")
    hwnd = int(desk.winId())
    os.environ["SHISHYA_DESKTOP_HWND"] = str(hwnd)
    # Written last, once the window is real: the host waits on this file to
    # say the sandbox is up, and verifies the handle before believing it.
    tmp = common.SHARED / ".desktop.hwnd.tmp"
    tmp.write_text(str(hwnd), encoding="utf-8")
    tmp.replace(common.SHARED / ".desktop.hwnd")
    # Load the model while nobody is waiting on it yet.
    kit.background(common.warm)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
