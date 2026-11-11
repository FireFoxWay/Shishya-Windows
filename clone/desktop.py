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
                           QPainter, QPen, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,  # noqa: E402
                               QMessageBox, QPushButton, QVBoxLayout, QWidget)

import common      # noqa: E402

W, H = 1440, 900
DOCK_H, DOCK_GAP = 60, 14
RESERVED = DOCK_H + 2 * DOCK_GAP       # the strip along the bottom apps keep clear of
APPS = Path(__file__).resolve().parent / "apps"
CONFIG = common.SHARED / ".desktop.json"
LOOK = {"wallpaper": "ink", "accent": kit.ACCENT, "wallmark": "शि", "fps": 12}
LOOK_VERSION = 3                       # 3: Ink & Marigold (DESIGN.md)

# ─── palette ────────────────────────────────────────────────────────────────
# Ink for the desk, and the home page's own tints for the things on it.
INK, INK_LOW, CARD, EDGE = "#14162B", "#0B0C1D", "#1C1F3A", "#2A2E52"
TEXT, MUTED = kit.DESK_TEXT, kit.DESK_MUTED
MARIGOLD = kit.ACCENT
# The wallpaper's glows: (x, y, radius — all as shares of the width or
# height — colour, strength). Indigo high right, teal low left, a little
# marigold behind the mark, violet off the top.
GLOWS = ((0.80, 0.14, 0.62, (75, 80, 224), 0.36), (0.08, 0.98, 0.56, (18, 165, 148), 0.24),
         (0.90, 1.02, 0.42, (245, 182, 58), 0.17), (0.36, -0.12, 0.46, (138, 79, 216), 0.18))
# The tints and the line icons are kit's: the apps' title bars use them too.
TINT, ICONS, paint_icon, _path = kit.TINT, kit.ICONS, kit.paint_icon, kit.icon_path

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

# VS Code only where this copy of Shishya was built with it (windows/build.ps1).
if (Path(__file__).resolve().parent.parent / "tools" / "vscode" / "Code.exe").exists():
    ALL_APPS.insert(next(i for i, a in enumerate(ALL_APPS) if a[1] == "code_app.py") + 1,
                    ("VS Code", "vscode_app.py", "code", "lav"))

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
        if look.get("look_version", 0) < 2:
            look.update(wallpaper="ink", wallmark="शि")
        look.update(accent=kit.ACCENT, look_version=LOOK_VERSION)      # marigold is the default now
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

_desk = {}
BASE = [None]          # a plain colour chosen in Settings, or None for ink


def desk_picture(scale=2, base=None):
    """The still desk, drawn once: ink, four slow glows — and a grain of noise.

    A dark gradient has only a handful of shades to run through, and drawn
    smoothly they show as bands. A point or two of noise per pixel breaks
    the bands up; it is how every dark gradient that looks smooth is made.
    Worked out at one pixel per point and enlarged: a glow loses nothing by it.
    """
    key = (scale, base)
    if key in _desk:
        return _desk[key]
    from PySide6.QtGui import QImage, QPixmap
    top = QColor(base or INK)
    low = QColor(base).darker(190) if base else QColor(INK_LOW)
    try:
        import numpy as np
        y, x = np.mgrid[0:H, 0:W].astype(np.float32)
        t = (y / (H - 1))[..., None]
        a0 = np.array([top.red(), top.green(), top.blue()], np.float32)
        a1 = np.array([low.red(), low.green(), low.blue()], np.float32)
        img = a0 + (a1 - a0) * t
        for gx, gy, gr, colour, strength in GLOWS:
            d = np.sqrt((x - W * gx) ** 2 + (y - H * gy) ** 2) / (W * gr)
            a = (np.clip(1 - d, 0, 1) ** 2 * strength)[..., None]
            img = img * (1 - a) + np.array(colour, np.float32) * a
        img += np.random.default_rng(7).uniform(-1.8, 1.8, (H, W, 1)).astype(np.float32)
        rgb = np.clip(np.rint(img), 0, 255).astype(np.uint8)
        rgba = np.dstack([rgb, np.full((H, W, 1), 255, np.uint8)])
        picture = QImage(rgba.tobytes(), W, H, W * 4, QImage.Format_RGBA8888).copy()
    except Exception:                                   # noqa: BLE001 — banded beats blank
        picture = QImage(W, H, QImage.Format_RGB32)
        q = QPainter(picture)
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0, top)
        g.setColorAt(1, low)
        q.fillRect(0, 0, W, H, g)
        for gx, gy, gr, colour, strength in GLOWS:
            glow = QRadialGradient(W * gx, H * gy, W * gr)
            glow.setColorAt(0, QColor(*colour, int(255 * strength)))
            glow.setColorAt(1, QColor(*colour, 0))
            q.fillRect(0, 0, W, H, glow)
        q.end()
    if scale != 1:
        picture = picture.scaled(W * scale, H * scale, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    pm = QPixmap.fromImage(picture)
    pm.setDevicePixelRatio(scale)
    _desk[key] = pm
    return pm


def paint_desk(p, offset=QPoint(0, 0), live=None):
    """The desk itself. Drawn by the screen, and by the dock and the start
    panel behind their own rounded corners, so the corners show the desk and
    not a square of something else."""
    p.save()
    p.translate(-offset)
    if live is not None:
        live.draw(p, W, H)
    else:
        p.drawPixmap(0, 0, desk_picture(2 if p.device().devicePixelRatioF() > 1 else 1, BASE[0]))
    p.restore()


def glass(p, rect, radius=20, strong=False):
    """A sheet of dark glass on the desk: the dock and the panel (strong), or
    a card (a breath of white)."""
    p.setPen(QPen(QColor(255, 255, 255, 30), 1))
    p.setBrush(QColor(22, 24, 48, 208) if strong else QColor(255, 255, 255, 17))
    p.drawRoundedRect(QRectF(rect).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)


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


def font(px, weight=QFont.Normal, family=None):
    """Fonts by pixel, never by point: points follow the display's DPI, and
    the clone's screen is the same 1440x900 on every laptop."""
    f = QFont()
    f.setFamilies([family] if family else
                  ["Segoe UI Variable Display" if px >= 18 else "Segoe UI Variable Text",
                   "Segoe UI", "Nirmala UI"])
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
        hot = self.underMouse() or self.hasFocus()
        if hot:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 22))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        x = (self.width() - self.size) / 2
        paint_icon(p, QRectF(x, 7, self.size, self.size), self.icon, self.tint)
        p.setPen(QColor(TEXT))
        p.setFont(font(12, QFont.Medium))
        p.drawText(QRectF(0, self.size + 12, self.width(), 18), Qt.AlignHCenter | Qt.AlignTop,
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
        hot = self.underMouse() or self.hasFocus()
        p.setPen(QPen(QColor(255, 255, 255, 26 if hot else 0), 1))
        p.setBrush(QColor(255, 255, 255, 26 if hot else 11))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
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
        super().__init__(desktop, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.desktop = desktop
        self.setAccessibleName("Apps")
        self.setObjectName("startPanel")
        self.setFixedSize(self.PW, self.PH)
        self.setStyleSheet(f"""
            QLineEdit {{ background: rgba(255,255,255,0.07); color: {TEXT};
                         border: 1px solid rgba(255,255,255,0.14); border-radius: 14px;
                         padding: 0 14px 0 6px; min-height: 44px; font-size: 14px;
                         selection-background-color: {MARIGOLD}; selection-color: {INK}; }}
            QLineEdit:hover {{ border-color: rgba(255,255,255,0.24); }}
            QLineEdit:focus {{ border-color: {MARIGOLD}; background: rgba(255,255,255,0.10); }}
            QLabel {{ color: {MUTED}; font-size: 11px; font-weight: 600; letter-spacing: 0.6px;
                      background: transparent; }}
            QPushButton#link {{ background: transparent; color: {TEXT}; border: 0;
                                font-size: 12px; font-weight: 500; padding: 7px 12px;
                                border-radius: 9px; }}
            QPushButton#link:hover, QPushButton#link:focus {{ background: rgba(255,255,255,0.10); }}
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
        glass(p, self.rect(), 24, strong=True)
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
    """The app windows on this screen, oldest first, as (handle, title,
    minimised). Asked of Windows rather than tracked: an app the panel
    opened, or the executor opened, must appear here too."""
    return kit.desk_windows(desk)


icon_for = kit.icon_for


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
        c = QRectF(self.rect()).adjusted(5, 5, -5, -5)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 26))
            p.drawEllipse(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(MARIGOLD))
        p.drawEllipse(c.adjusted(3, 3, -3, -3))
        p.setPen(QColor(INK))
        p.setFont(font(15, QFont.Bold, "Nirmala UI"))
        p.drawText(c.adjusted(0, -1, 0, -1), Qt.AlignCenter, "शि")
        ring = QRectF(c)
        p.setBrush(Qt.NoBrush)
        if self.state == "working":
            pen = QPen(QColor(TEXT), 2.5)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(ring, int(-self.phase * 360 * 16), 110 * 16)
        elif self.state == "needs":
            alpha = int(150 + 105 * (0.5 + 0.5 * math.sin(self.phase * 2 * math.pi)))
            col = QColor(TINT["peach"][0])
            col.setAlpha(alpha)
            p.setPen(QPen(col, 2.5))
            p.drawEllipse(ring)
        elif self.state == "wheel":
            p.setPen(QPen(QColor(TEXT), 2, Qt.DashLine))
            p.drawEllipse(ring)
        p.end()


# The window each pinned app opens, by its title: how the dock knows a pinned
# app is already open.
PIN_TITLES = {"chat_app.py": "Shishya", "billing_app.py": "Billing", "inbox_app.py": "Inbox",
              "files_app.py": "Files", "shishya_app.py": "Teach a lesson",
              "make_app.py": "Make a Document"}


class PinButton(QPushButton):
    """A pinned app, in the dock. One click opens it; once it is open the
    same button is its window's: forward, put away, back again."""

    def __init__(self, name, target, icon, tint):
        super().__init__()
        self.name, self.target, self.icon_, self.tint = name, target, icon, tint
        self.title = PIN_TITLES.get(target, name)
        self.hwnd, self.hidden, self.top = 0, False, False
        self.setAccessibleName(name)
        self.setToolTip(name)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(44, 44)
        self.clicked.connect(self.on_click)

    def on_click(self):
        if not self.hwnd:
            open_entry(self.target)
        elif self.top and not self.hidden:
            kit.minimise_window(self.hwnd)
        else:
            kit.restore_window(self.hwnd)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)
        if self.hidden:
            p.setOpacity(0.5)
        paint_icon(p, QRectF(6, 4, 32, 32), self.icon_, self.tint, radius=10)
        p.setOpacity(1.0)
        if self.hwnd:                    # open: a mark under it, marigold when it is in front
            front = self.top and not self.hidden
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(MARIGOLD) if front else QColor(255, 255, 255, 110))
            wide = 14 if front else 4
            p.drawRoundedRect(QRectF(22 - wide / 2, self.height() - 5, wide, 3), 1.5, 1.5)
        p.end()


class TaskButton(QPushButton):
    """An open window, in the dock. Click to bring it forward; click the one
    already in front to put it away; click one that is put away to bring it
    back."""

    def __init__(self, hwnd, title, hidden=False):
        super().__init__()
        self.hwnd, self.title, self.hidden = hwnd, title, hidden
        self.icon_, self.tint = icon_for(title)
        self.top = False
        self.setAccessibleName(title)
        self.setToolTip(title)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(44)
        f = font(13)
        self.label = title if len(title) <= 16 else title[:15] + "…"
        from PySide6.QtGui import QFontMetrics
        self.setFixedWidth(46 + QFontMetrics(f).horizontalAdvance(self.label) + 16)
        self.clicked.connect(self.on_click)

    def on_click(self):
        if self.top and not self.hidden:
            kit.minimise_window(self.hwnd)
        else:
            kit.restore_window(self.hwnd)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self.underMouse() or self.hasFocus():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 24))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 13, 13)
        if self.hidden:
            p.setOpacity(0.5)          # put away: still open, out of sight
        paint_icon(p, QRectF(6, 4, 32, 32), self.icon_, self.tint, radius=10)
        p.setPen(QColor(TEXT))
        p.setFont(font(13, QFont.Medium))
        p.drawText(QRectF(46, 0, self.width() - 50, self.height() - 4),
                   Qt.AlignLeft | Qt.AlignVCenter, self.label)
        p.setOpacity(1.0)
        if self.top and not self.hidden:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(MARIGOLD))
            p.drawRoundedRect(QRectF(22 - 7, self.height() - 5, 14, 3), 1.5, 1.5)
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
        self.sep1.setStyleSheet("background: rgba(255,255,255,0.14);")
        row.addWidget(self.sep1)
        # The six a counter reaches for, always one click away — the start
        # panel is for everything else.
        self.pins = [PinButton(*entry) for entry in PINNED]
        for pin in self.pins:
            row.addWidget(pin)
        self.tasks = QHBoxLayout()
        self.tasks.setSpacing(2)
        row.addLayout(self.tasks)
        self.sep2 = QFrame()
        self.sep2.setFixedSize(1, 26)
        self.sep2.setStyleSheet("background: rgba(255,255,255,0.14);")
        row.addWidget(self.sep2)
        self.clock = QLabel()
        self.clock.setStyleSheet(f"color: {TEXT}; font-size: 13px; padding-left: 10px;"
                                 " background: transparent;")
        self.clock.setTextFormat(Qt.RichText)
        self.clock.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
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
        self.clock.setText(f"<b>{now.toString('HH:mm')}</b><br>"
                           f"<span style='color:{MUTED}; font-size:11px'>{now.toString('ddd d MMM')}</span>")
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
            # A pinned app's window belongs to its pin; the rest get a button.
            claimed = set()
            for pin in self.pins:
                match = next((w for w in windows if w[1] == pin.title and w[0] not in claimed), None)
                pin.hwnd, pin.hidden = (match[0], match[2]) if match else (0, False)
                if match:
                    claimed.add(match[0])
                pin.update()
            for hwnd, title, hidden in [w for w in windows if w[0] not in claimed][-5:]:
                self.tasks.addWidget(TaskButton(hwnd, title, hidden))
            QTimer.singleShot(0, self.recentre)
        # which one is on top: the last child in Windows' z-order is the first found
        top = user32.GetWindow(int(self.desktop.winId()), 5) if user32 else 0   # GW_CHILD
        while top and (top == mine or not user32.IsWindowVisible(top)):
            top = user32.GetWindow(top, 2)                                    # GW_HWNDNEXT
        buttons = [self.tasks.itemAt(i).widget() for i in range(self.tasks.count())] + self.pins
        for b in buttons:
            if isinstance(b, (TaskButton, PinButton)) and b.top != bool(b.hwnd and b.hwnd == top):
                b.top = bool(b.hwnd and b.hwnd == top)
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
        glass(p, self.rect(), 22, strong=True)
        p.end()


# ─── the screen ─────────────────────────────────────────────────────────────

CARD_X, CARD_W = 28, 264


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
        BASE[0] = chosen if str(chosen).startswith("#") and QColor(chosen).isValid() else None
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

    def _card(self, p, y, h, fill=None):
        """A card: tinted when it carries a fill, dark glass when it does not."""
        r = QRectF(CARD_X, y, CARD_W, h)
        if fill:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(fill))
            p.drawRoundedRect(r, 20, 20)
        else:
            glass(p, r, 20)
        return r

    def _text(self, p, rect, text, size, colour, weight=QFont.Normal, flags=Qt.AlignLeft | Qt.AlignTop):
        f = font(size, weight)
        if size <= 11:
            f.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)
        p.setFont(f)
        p.setPen(QColor(colour))
        p.drawText(rect, flags, text)

    def _badge(self, p, card, icon, ink):
        """The card's kind, top right: its line icon on a wash of white."""
        r = QRectF(card.right() - 52, card.y() + 16, 36, 36)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 105))
        p.drawRoundedRect(r, 11, 11)
        p.save()
        p.translate(r.x() + 8, r.y() + 8)
        p.scale(20 / 24, 20 / 24)
        pen = QPen(QColor(ink), 1.9)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(_path(ICONS[icon]))
        p.restore()

    def paint_cards(self, p):
        self.cards = {}
        now = dt.datetime.now()
        y = 28
        r = self._card(p, y, 122)
        self._text(p, r.adjusted(20, 12, -20, 0), now.strftime("%H:%M"), 50, TEXT, QFont.DemiBold)
        self._text(p, r.adjusted(22, 82, -20, 0), now.strftime("%A, %d %B").replace(" 0", " "),
                   13, MUTED)
        y += 122 + 12

        fill, ink = TINT["butter"]
        r = self._card(p, y, 112, fill)
        self._badge(p, r, "bill", ink)
        self._text(p, r.adjusted(20, 16, -60, 0), "TODAY'S TAKINGS", 11, ink, QFont.DemiBold)
        self._text(p, r.adjusted(20, 36, -20, 0), rupees(self.facts.takings), 32, ink, QFont.DemiBold)
        bills = self.facts.bills
        self._text(p, r.adjusted(20, 80, -20, 0),
                   "No bills yet today" if not bills else f"{bills} bill{'s' if bills != 1 else ''} today",
                   12, ink)
        self.cards["billing_app.py"] = r.toRect()
        y += 112 + 12

        fill, ink = TINT["mint"]
        r = self._card(p, y, 96, fill)
        self._badge(p, r, "inbox", ink)
        if self.facts.short:
            first = self.facts.first_short
            left = int(first["stock"]) if first else 0
            self._text(p, r.adjusted(20, 16, -60, 0), f"LOW ON STOCK · {self.facts.short}", 11, ink,
                       QFont.DemiBold)
            p.setFont(font(17, QFont.DemiBold))
            name = p.fontMetrics().elidedText(first["name"], Qt.ElideRight, CARD_W - 44) if first else ""
            self._text(p, r.adjusted(20, 40, -20, 0), name, 17, ink, QFont.DemiBold)
            self._text(p, r.adjusted(20, 66, -20, 0), f"{left} left" if left > 0 else "out of stock", 12, ink)
        else:
            self._text(p, r.adjusted(20, 16, -60, 0), "STOCK", 11, ink, QFont.DemiBold)
            self._text(p, r.adjusted(20, 40, -20, 0), "Nothing running low", 17, ink, QFont.DemiBold)
        self.cards["findings_app.py"] = r.toRect()
        y += 96 + 12

        r = self._card(p, y, 84)
        dot = {"idle": TINT["mint"][0], "working": MARIGOLD, "needs": TINT["peach"][0]}.get(self.state, TEXT)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(dot))
        p.drawEllipse(QRectF(r.x() + 20, r.y() + 20, 8, 8))
        self._text(p, r.adjusted(36, 14, -20, 0), "SHISHYA IS", 11, MUTED, QFont.DemiBold)
        self._text(p, r.adjusted(20, 40, -20, 0), STATES.get(self.state, STATES["idle"]).lower(),
                   17, TEXT, QFont.DemiBold)
        self.cards["activity_app.py"] = r.toRect()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        paint_desk(p, QPoint(0, 0), self.live)
        # the mark: शि, large and quiet in the corner
        if self.wallmark:
            p.setFont(font(300, QFont.DemiBold, "Nirmala UI"))
            p.setPen(QColor(255, 255, 255, 13 if self.live is None else 18))
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
