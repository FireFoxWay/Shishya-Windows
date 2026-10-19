#!/usr/bin/env python3
"""
Shishya — the clone's screen. Runs INSIDE the sandbox.

On the Mac this was a GTK desktop on a 1440x900 Xvfb display, watched
through noVNC. On Windows it is one window, 1440x900 pixels, and every app
the clone opens parents itself into it (kit.Window). That keeps what made
the VM's display worth having:

  - one screen the panel can show and you can take over, with the clone's
    work on it and nothing of yours;
  - a fixed size, because taught procedures reference on-screen layout and a
    screen that resized with your monitor would quietly invalidate them;
  - a clear line on your own desktop between the clone's windows and yours.

The furniture is the same as before: a wallpaper, an Apps button in the
bottom-left corner, the open windows along the taskbar, what the clone is
doing and the time on the right, and Shut down at the bottom of the menu
rather than in the corner where a hand goes without looking.

    pythonw desktop.py
"""

import ctypes
import json
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
from PySide6.QtCore import QDateTime, QPoint, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QWidget)

import common      # noqa: E402

W, H = 1440, 900
TASKBAR_H = 48
APPS = Path(__file__).resolve().parent / "apps"
CONFIG = common.SHARED / ".desktop.json"
LOOK = {"wallpaper": "#10151c", "accent": "#0078d4", "icon_size": 96,
        "wallmark": "SHISHYA SANDBOX", "fps": 12}

# Ordered by how the work actually flows — a file arrives, you read it, you
# teach from it, you produce something — as on the Mac.
MENU = [
    ("Shishya — talk to it", "chat_app.py"),
    None,
    ("Billing", "billing_app.py"),
    ("Files", "files_app.py"),
    ("Inbox", "inbox_app.py"),
    None,
    ("Findings", "findings_app.py"),
    ("Reports", "reports_app.py"),
    ("Training Data", "training_app.py"),
    ("Teach a lesson", "shishya_app.py"),
    None,
    ("Make a Document", "make_app.py"),
    ("Code", "code_app.py"),
    ("Sheets", "sheet_app.py"),
    None,
    ("Banking", "bank_app.py"),
    ("Credit assistant", "credit_app.py"),
    None,
    ("Work folder", ("files_app.py", str(common.WORK))),
    ("Lessons", ("files_app.py", str(common.TRACES))),
    ("Activity", "activity_app.py"),
    ("Browser", "browser_app.py"),
    ("System", "system_app.py"),
    ("Models", "models_app.py"),
    ("Settings", "settings_app.py"),
]

EMBEDDED = os.environ.get("SHISHYA_SCREEN") == "embedded"
WATCHING = common.SHARED / ".watching"      # touched by the host while it shows us
PLACEMENT = common.SHARED / ".screen-mode"  # "in": inside Shishya's window; "out": popped out


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
    animate a wallpaper. On its own on a monitor, it is always looked at."""
    if not EMBEDDED:
        return True
    try:
        import time as _t
        return _t.time() - WATCHING.stat().st_mtime < 4
    except OSError:
        return False


PILLS = {"working": "CLONE WORKING", "wheel": "YOU HAVE THE WHEEL",
         "needs": "NEEDS YOU", "idle": "IDLE"}


def read_look():
    try:
        return {**LOOK, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(LOOK)


def launch(target, *args):
    """Start one of the clone's apps on this screen."""
    path = APPS / target
    if not path.exists():
        return False
    # Through the host (kit.open_app), which also decides whether the
    # browser gets the web — the one decision the sandbox cannot make.
    return kit.open_app(target, *args)


# ─── the windows on this screen ─────────────────────────────────────────────

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


class Taskbar(QWidget):
    CHROME = True          # the recorder ignores it: our furniture, not the task

    def __init__(self, desktop):
        super().__init__(desktop)
        self.desktop = desktop
        self.setObjectName("taskbar")
        self.setAccessibleName("Taskbar")
        self.setGeometry(0, H - TASKBAR_H, W, TASKBAR_H)
        self.setAttribute(Qt.WA_StyledBackground, True)
        # A window of its own, so it can sit ABOVE the apps' windows: they are
        # child windows of the screen, and a plain Qt widget is painted
        # underneath every child window, however it is stacked in Qt.
        self.setAttribute(Qt.WA_NativeWindow, True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 12, 0)
        row.setSpacing(6)

        self.start = QPushButton("▦  APPS")
        self.start.setAccessibleName("Apps")
        self.start.setObjectName("apps")
        self.start.clicked.connect(self.on_start)
        row.addWidget(self.start)

        self.tasks = QHBoxLayout()
        self.tasks.setSpacing(6)
        row.addLayout(self.tasks, 1)

        self.clock = QLabel()
        self.clock.setObjectName("clock")
        row.addWidget(self.clock)
        self.pill = QLabel("IDLE")
        self.pill.setObjectName("pill")
        self.pill.setAccessibleName("Clone state")
        row.addWidget(self.pill)
        self.shown = None
        self.state = None
        self.restyle(LOOK["accent"])

        tick = QTimer(self)
        tick.timeout.connect(self.tick)
        tick.start(1000)
        self.tick()

    def restyle(self, accent):
        self.accent = accent
        self.setStyleSheet(f"""
            QWidget#taskbar {{ background: #0b0c0e; border-top: 1px solid #2a2e33; }}
            QPushButton {{ background: transparent; color: #e9ebee; border: 0;
                           padding: 0 18px; min-height: {TASKBAR_H}px;
                           font-size: 11px; letter-spacing: 1.5px; }}
            QPushButton:hover {{ background: #e9ebee; color: #0b0c0e; }}
            QPushButton[task="1"] {{ border-bottom: 2px solid {accent}; color: #c9ced4;
                                     padding: 0 14px; }}
            QLabel#clock {{ color: #9aa0a7; font-size: 11px; letter-spacing: 1.4px;
                            padding: 0 14px; }}
            QLabel#pill {{ border: 1px solid #4a4f55; color: #8b9199; padding: 3px 10px;
                           font-size: 10px; letter-spacing: 1.6px; }}
            QLabel#pill[state="working"] {{ background: {accent}; border-color: {accent};
                                           color: white; }}
            QLabel#pill[state="wheel"] {{ border: 1px dashed #e9ebee; color: #e9ebee; }}
            QLabel#pill[state="needs"] {{ border: 2px dashed #e9ebee; color: #e9ebee; }}
        """)

    def tick(self):
        self.clock.setText(QDateTime.currentDateTime().toString("HH:mm   ddd dd MMM").upper())
        try:
            state = common.STATE.read_text(encoding="utf-8").strip() or "idle"
        except OSError:
            state = "idle"
        if state != self.state:
            self.state = state
            self.pill.setText(PILLS.get(state, "IDLE"))
            self.pill.setProperty("state", state)
            self.pill.style().unpolish(self.pill)
            self.pill.style().polish(self.pill)
            self.desktop.set_busy(state == "working")

        # Always on top of the apps: a window dragged down must not cover it.
        if user32:
            user32.SetWindowPos(int(self.winId()), 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)

        # Rebuilt only when the list changed — a taskbar that repaints every
        # second churns the tree the executor reads, for nothing.
        mine = int(self.winId())
        windows = [w for w in open_windows(int(self.desktop.winId())) if w[0] != mine]
        if windows != self.shown:
            self.shown = windows
            while self.tasks.count():
                item = self.tasks.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for hwnd, title in windows[-8:]:
                b = QPushButton(title if len(title) <= 24 else title[:23] + "…")
                b.setProperty("task", "1")
                b.setAccessibleName(title)
                b.clicked.connect(lambda _=False, h=hwnd: raise_window(h))
                self.tasks.addWidget(b)
            self.tasks.addStretch(1)

    def on_start(self):
        menu = QMenu(self)
        menu.setAccessibleName("Apps")
        menu.setStyleSheet("""
            QMenu { background: #0b0c0e; color: #e9ebee; border: 1px solid #2a2e33;
                    padding: 6px 0; font-size: 13px; }
            QMenu::item { padding: 7px 28px 7px 18px; }
            QMenu::item:selected { background: #e9ebee; color: #0b0c0e; }
            QMenu::separator { height: 1px; background: #2a2e33; margin: 5px 0; }
        """)
        for item in MENU:
            if item is None:
                menu.addSeparator()
                continue
            text, target = item
            act = menu.addAction(text)
            if isinstance(target, tuple):
                act.triggered.connect(lambda _=False, t=target: launch(*t))
            else:
                act.triggered.connect(lambda _=False, t=target: launch(t))
        office = common.libreoffice()
        if office:
            menu.addSeparator()
            menu.addAction("LibreOffice (own window)").triggered.connect(
                lambda: subprocess.Popen([office], creationflags=common.NO_WINDOW))
        menu.addSeparator()
        menu.addAction("Shut down").triggered.connect(self.on_power)
        size = menu.sizeHint()
        menu.exec(self.mapToGlobal(QPoint(0, -size.height())))

    def on_power(self):
        answer = QMessageBox.question(
            self.desktop, "Shut down the sandbox?",
            "Anything the clone has not saved to Work will be lost.",
            QMessageBox.Ok | QMessageBox.Cancel, QMessageBox.Cancel)
        if answer == QMessageBox.Ok:
            # The clone cannot stop its own sandbox — it does not own its job.
            # Shutting down is a request it makes of the host, as on the Mac.
            (common.SHARED / ".shutdown-requested").write_text("1", encoding="utf-8")


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
        self.busy = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.step)
        self.taskbar = Taskbar(self)
        self.wallmark = ""
        follow = QTimer(self)
        follow.timeout.connect(self.follow)
        follow.start(1000)
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
        self.wallmark = look.get("wallmark", "")
        self.taskbar.restyle(look.get("accent", LOOK["accent"]))
        chosen = look.get("wallpaper", "")
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

    def set_busy(self, busy):
        """Still while the model works: the cores are its."""
        self.busy = busy
        self._retime()

    def _retime(self):
        want = self.live is not None and not self.busy and not self.isMinimized() and watched()
        if want and not self.timer.isActive():
            self.timer.start(int(1000 / (self.fps or self.rate or 12)))
        elif not want and self.timer.isActive():
            self.timer.stop()

    def step(self):
        if self.live:
            self.live.step()
            self.update(0, 0, W, H - TASKBAR_H)

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.live:
            self.live.draw(p, W, H - TASKBAR_H)
        else:
            colour = (self.look or LOOK).get("wallpaper", "#10151c")
            p.fillRect(0, 0, W, H, QColor(colour if colour.startswith("#") else "#04060d"))
        p.setPen(QColor("#7c828a"))
        f = QFont("Segoe UI", 8)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 3)
        p.setFont(f)
        p.drawText(self.rect().adjusted(0, 0, -18, -TASKBAR_H - 14),
                   Qt.AlignRight | Qt.AlignBottom, self.wallmark.upper())
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
