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

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal   # noqa: E402
from PySide6.QtGui import QFont, QGuiApplication, QWindow               # noqa: E402
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication,   # noqa: E402
                               QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import common   # noqa: E402

# ─── look ───────────────────────────────────────────────────────────────────
# The panel's palette: near-black ink, paper white, one accent used sparingly.
# Emphasis is inversion, not colour — the same rule the panel and the GTK
# desktop follow, so the three read as one product.

ACCENT = "#0078d4"
DOCK_SPACE = 88        # the strip the clone's dock floats in (desktop.RESERVED)
INK, PAPER, RULE, MUTED = "#0b0c0e", "#fbfbfa", "#d9dcdf", "#6b7178"

STYLE = f"""
* {{ font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; color: {INK}; }}
QWidget#appBody, QWidget#appRoot {{ background: {PAPER}; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 11px; letter-spacing: 1.5px;
                          font-weight: 600; padding-top: 8px; }}
QPushButton {{ background: {PAPER}; border: 1px solid {INK}; padding: 6px 14px;
               border-radius: 0; }}
QPushButton:hover {{ background: {INK}; color: {PAPER}; }}
QPushButton:disabled {{ color: #a0a5ab; border-color: #c4c8cc; }}
QPushButton[kind="primary"] {{ background: {INK}; color: {PAPER}; }}
QPushButton[kind="primary"]:hover {{ background: {ACCENT}; border-color: {ACCENT}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {{
    background: white; border: 1px solid {RULE}; padding: 5px; border-radius: 0;
    selection-background-color: {ACCENT}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{ border: 1px solid {INK}; }}
QTableWidget, QTreeWidget, QListWidget {{ background: white; border: 1px solid {RULE};
    gridline-color: {RULE}; selection-background-color: {ACCENT};
    selection-color: white; }}
QHeaderView::section {{ background: #f0f1f2; border: 0; border-right: 1px solid {RULE};
    border-bottom: 1px solid {RULE}; padding: 4px 6px; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {RULE}; top: -1px; }}
QTabBar::tab {{ padding: 6px 16px; border: 1px solid {RULE}; background: #f0f1f2;
                margin-right: -1px; }}
QTabBar::tab:selected {{ background: white; border-bottom-color: white; }}
QProgressBar {{ border: 1px solid {RULE}; background: white; height: 14px;
                text-align: center; }}
QProgressBar::chunk {{ background: {INK}; }}
QFrame#titleBar {{ background: #1E2340; border-bottom: 1px solid #2C3256; }}
QFrame#titleBar QLabel {{ color: #FBF7EC; font-size: 12px; font-weight: 600; }}
QFrame#titleBar QPushButton {{ background: transparent; color: #FBF7EC; border: 0;
                               padding: 2px 12px; font-size: 12px; }}
QFrame#titleBar QPushButton:hover {{ background: #c42b1c; color: white; }}
QFrame#card {{ background: white; border: 1px solid {RULE}; }}
"""


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
    if sys.platform == "win32":
        import ctypes
        # Grouped under the clone in the Windows taskbar, never under Python —
        # an app of the clone should not look like one of yours.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Shishya.Clone")
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(name)
    for chosen in ("windows11", "windowsvista", "Fusion"):
        if chosen.lower() in [s.lower() for s in __import__("PySide6.QtWidgets",
                                                            fromlist=["QStyleFactory"]).QStyleFactory.keys()]:
            app.setStyle(chosen)
            break
    app.setFont(QFont("Segoe UI", 10))
    app.setStyleSheet(STYLE)
    _bridge = _Bridge()
    app._focus_on_click = FocusOnClick(app)
    app.installEventFilter(app._focus_on_click)
    app._cloak_popups = CloakPopups(app)
    app.installEventFilter(app._cloak_popups)
    Recorder.install(app, name)
    return app


# ─── windows on the clone's screen ──────────────────────────────────────────

class TitleBar(QFrame):
    """What a window on the clone's screen has instead of a Windows frame.

    A window parented into another window loses its frame — it is a child,
    not a top-level — so this draws the two things a frame gave: a title to
    grab and drag, and a way to close it.
    """

    CHROME = True

    def __init__(self, window, title):
        super().__init__(window)
        self.setObjectName("titleBar")
        self.window_ = window
        self.setFixedHeight(28)
        row = QHBoxLayout(self)
        row.setContentsMargins(12, 0, 0, 0)
        self.text = QLabel(title)
        row.addWidget(self.text, 1)
        close = QPushButton("✕")
        close.setAccessibleName("Close")
        close.setObjectName("closeWindow")
        close.setFocusPolicy(Qt.NoFocus)
        close.clicked.connect(window.close)
        row.addWidget(close)
        self._drag = None

    def mousePressEvent(self, e):
        self.window_.raise_()
        self._drag = e.globalPosition().toPoint() - self.window_.pos()

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            want = e.globalPosition().toPoint() - self._drag
            # Never dragged off the clone's screen: a window you cannot reach
            # the title of is a window you cannot close.
            want.setX(max(-self.window_.width() + 80, min(want.x(), 1440 - 80)))
            want.setY(max(0, min(want.y(), 900 - DOCK_SPACE - 28)))
            self.window_.move(want)

    def mouseReleaseEvent(self, _e):
        self._drag = None


class Window(QWidget):
    """An app window. Put the app's contents into self.body.

    On the clone's screen (SHISHYA_DESKTOP_HWND set) it parents itself into
    that window and draws its own title bar. Run on its own — while
    developing, or on Linux — it is an ordinary window with an ordinary frame.
    """

    _cascade = 0

    def __init__(self, title, width=860, height=600):
        super().__init__()
        self.setObjectName("appRoot")
        self.setWindowTitle(title)
        self.setAccessibleName(title)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.desk = int(os.environ.get("SHISHYA_DESKTOP_HWND") or 0)
        if self.desk:
            outer.addWidget(TitleBar(self, title))
            height += 28
        self.body = QWidget()
        self.body.setObjectName("appBody")
        outer.addWidget(self.body, 1)
        # The clone's screen is 1440x900 with a floating dock along the
        # bottom; nothing opens bigger than what is left of it.
        self.resize(min(width, 1400), min(height, 900 - DOCK_SPACE - 12))

    def show(self):
        if self.desk:
            self.winId()
            handle = self.windowHandle()
            handle.setParent(QWindow.fromWinId(self.desk))
            # Cascade by how many windows are already on the clone's screen,
            # so a second window does not sit exactly on the first — and keep
            # the whole window above the taskbar, where its title and its
            # buttons can be reached.
            step = _open_on(self.desk) % 6
            x, y = 40 + step * 36, 20 + step * 30
            self.resize(min(self.width(), 1440 - x - 12), min(self.height(), 900 - DOCK_SPACE - y - 8))
            self.move(x, y)
        super().show()
        self.raise_()

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
