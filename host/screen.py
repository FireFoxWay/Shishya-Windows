#!/usr/bin/env python3
"""
Shishya — the clone's screen in the panel, on Windows. Runs on the HOST.

On the Mac the clone's display was an Xvfb framebuffer inside the VM and the
panel showed it through noVNC. On Windows the clone's screen is a real
window on this desktop — 1440x900 pixels, every app of the clone parented
into it — and the panel shows it by asking Windows to paint it into a bitmap
(PrintWindow, which works whether or not the window is covered).

Input goes the other way the same way the executor's does: a click on the
picture becomes a message addressed to the clone's window under that point,
never to whatever has focus. That is what "take the wheel" means here, and
it cannot reach your own windows — each target is checked to belong to the
container before anything is posted to it.

The window itself is always there too. "Show it" brings it forward, and then
you are simply using it, with everything a real window gives you.
"""

import ctypes
import io
import time
from ctypes import wintypes

import hands
import winbox

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
user32.GetWindowDC.argtypes = [wintypes.HWND]
user32.GetWindowDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ChildWindowFromPointEx.argtypes = [wintypes.HWND, wintypes.POINT, wintypes.UINT]
user32.ChildWindowFromPointEx.restype = wintypes.HWND
user32.IsIconic.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]

PW_CLIENTONLY, PW_RENDERFULLCONTENT = 0x1, 0x2
CWP_SKIPINVISIBLE, CWP_SKIPTRANSPARENT = 0x1, 0x4


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long), ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD)]


def _grab(hwnd, client_only=True):
    """(width, height, BGRA bytes) of one window, painted by itself."""
    rect = wintypes.RECT()
    (user32.GetClientRect if client_only else user32.GetWindowRect)(hwnd, ctypes.byref(rect))
    w, h = rect.right - rect.left, rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return None
    wdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(wdc)
    bmp = gdi32.CreateCompatibleBitmap(wdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    try:
        flags = PW_RENDERFULLCONTENT | (PW_CLIENTONLY if client_only else 0)
        if not user32.PrintWindow(hwnd, mdc, flags):
            return None
        bi = BITMAPINFOHEADER(ctypes.sizeof(BITMAPINFOHEADER), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
        return w, h, buf.raw
    finally:
        gdi32.SelectObject(mdc, old)
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mdc)
        user32.ReleaseDC(hwnd, wdc)


POINTS_W = 1440          # the clone's screen, in points (clone/desktop.py W)


def _scale(desk):
    """Device pixels per point on the clone's screen — 2 when it is drawn
    for a 200% display (winvm.screen_scale). The page speaks in points."""
    rect = wintypes.RECT()
    user32.GetClientRect(desk, ctypes.byref(rect))
    return (rect.right - rect.left) / POINTS_W or 1.0


def _origin(hwnd):
    pt = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(pt))
    return pt.x, pt.y


def _popups(desk):
    """The clone's own top-level windows over its screen — menus, dialogs.
    A Qt menu is a window of its own, not a child of the app that opened it,
    and a picture without it shows a click that did nothing."""
    clone = set(winbox.container_pids())
    out = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        if h != desk and user32.IsWindowVisible(h) and hands._pid_of(h) in clone:
            out.append(h)
        return True
    user32.EnumWindows(EnumProc(each), 0)
    return list(reversed(out))                 # back to front, for painting


_watched = {"at": 0.0}


def _mark_watched():
    """Tell the clone's screen someone is looking, at most once a second —
    it animates its wallpaper only then (clone/desktop.py watched())."""
    now = time.time()
    if now - _watched["at"] > 1:
        _watched["at"] = now
        try:
            import paths
            (paths.SHARED / ".watching").touch()
        except OSError:
            pass


def capture(quality=80, max_width=None):
    """The clone's screen as JPEG bytes, or None when it is not up."""
    from PIL import Image
    desk = hands.desktop()
    if not desk:
        return None
    _mark_watched()
    if user32.IsIconic(desk):
        user32.ShowWindow(desk, 4)             # SW_SHOWNOACTIVATE: never steals focus
    got = _grab(desk)
    if not got:
        return None
    w, h, raw = got
    image = Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRA", 0, 1).convert("RGB")
    dx, dy = _origin(desk)
    for pop in _popups(desk):
        part = _grab(pop, client_only=False)
        if not part:
            continue
        pw, ph, praw = part
        r = wintypes.RECT()
        user32.GetWindowRect(pop, ctypes.byref(r))
        piece = Image.frombuffer("RGBA", (pw, ph), praw, "raw", "BGRA", 0, 1).convert("RGB")
        image.paste(piece, (r.left - dx, r.top - dy))
    if max_width and image.width > max_width:
        image = image.resize((max_width, round(image.height * max_width / image.width)))
    out = io.BytesIO()
    # Full colour resolution (4:4:4): the default halves it, and small text
    # and thin lines on a dark screen came out smeared.
    image.save(out, "JPEG", quality=quality, subsampling=0)
    return out.getvalue()


# ─── input ──────────────────────────────────────────────────────────────────

_last = {"hwnd": None, "at": 0.0}


def _target(x, y):
    """The clone's window under a point on its screen (screen-relative to the
    clone's own 0,0), and that point in screen coordinates."""
    desk = hands.desktop()
    if not desk:
        return None, None
    dx, dy = _origin(desk)
    k = _scale(desk)
    x, y = x * k, y * k
    sx, sy = dx + int(x), dy + int(y)
    # Popups first: they sit on top of everything on the clone's screen.
    for pop in reversed(_popups(desk)):
        r = wintypes.RECT()
        user32.GetWindowRect(pop, ctypes.byref(r))
        if r.left <= sx < r.right and r.top <= sy < r.bottom:
            return pop, (sx, sy)
    child = user32.ChildWindowFromPointEx(desk, wintypes.POINT(int(x), int(y)),
                                          CWP_SKIPINVISIBLE | CWP_SKIPTRANSPARENT)
    return (child or desk), (sx, sy)


def click(x, y):
    hwnd, at = _target(x, y)
    if not hwnd:
        return {"ok": False, "detail": "the clone's screen is not up"}
    hands._post_click(hwnd, *at)              # _own() inside: clone windows only
    _last.update(hwnd=hwnd, at=time.time())
    return {"ok": True}


# The whole mouse, not only a click: press, drag, release, double-click, the
# right button for context menus, and the wheel for scrolling a list. A drag
# keeps going to the window it started on, as a real mouse capture does —
# otherwise dragging a window's title bar would hand the move to whatever
# the pointer passed over.
BUTTONS = {"left": (0x0201, 0x0202, 0x0203, 0x0001), "right": (0x0204, 0x0205, 0x0206, 0x0002),
           "middle": (0x0207, 0x0208, 0x0209, 0x0010)}
WM_MOUSEWHEEL = 0x020A
_drag = {"hwnd": None, "button": None}


def _lparam(hwnd, sx, sy):
    pt = wintypes.POINT(int(sx), int(sy))
    user32.ScreenToClient(hwnd, ctypes.byref(pt))
    return ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF)


def mouse(kind, x, y, button="left", delta=0):
    desk = hands.desktop()
    if not desk:
        return {"ok": False, "detail": "the clone's screen is not up"}
    down, up, dbl, flag = BUTTONS.get(button, BUTTONS["left"])
    if kind in ("move", "up") and _drag["hwnd"]:
        hwnd = _drag["hwnd"]
        dx, dy = _origin(desk)
        k = _scale(desk)
        at = (dx + int(x * k), dy + int(y * k))
    else:
        hwnd, at = _target(x, y)
    if not hwnd:
        return {"ok": False}
    hands._own(hwnd)                          # clone windows only, every time
    post = user32.PostMessageW
    if kind == "wheel":
        # The wheel's position is in screen coordinates, not the window's.
        lp = ((at[1] & 0xFFFF) << 16) | (at[0] & 0xFFFF)
        post(hwnd, WM_MOUSEWHEEL, (int(delta) & 0xFFFF) << 16, lp)
        return {"ok": True}
    lp = _lparam(hwnd, *at)
    if kind == "down":
        _drag.update(hwnd=hwnd, button=button)
        post(hwnd, 0x0200, 0, lp)
        post(hwnd, down, flag, lp)
    elif kind == "move":
        post(hwnd, 0x0200, flag if _drag["hwnd"] else 0, lp)
    elif kind == "up":
        post(hwnd, up, 0, lp)
        _drag.update(hwnd=None, button=None)
    elif kind == "double":
        post(hwnd, dbl, flag, lp)
        post(hwnd, up, 0, lp)
    _last.update(hwnd=hwnd, at=time.time())
    return {"ok": True}


def key(text=None, name=None):
    hwnd = _last["hwnd"] or hands.desktop()
    if not hwnd:
        return {"ok": False, "detail": "click on the clone's screen first"}
    if name:
        if name not in hands.VK:
            return {"ok": False, "detail": f"{name} is not forwarded"}
        hands.post_key(hwnd, name)
    elif text:
        hands.post_text(hwnd, text, delay=0)
    return {"ok": True}


# Where the clone's screen is shown. Normally inside Shishya's own window
# (the home page paints it); "out" uncloaks the real window onto the monitor
# for somebody who wants a real mouse and every key combination on it. The
# screen cloaks and uncloaks itself — Windows lets only a window's own
# process do that — so the host asks, through shared/, like everything else.

def _placement():
    import paths
    return paths.SHARED / ".screen-mode"


def popped():
    try:
        return _placement().read_text(encoding="utf-8").strip() == "out"
    except OSError:
        return False


def show():
    """Pop the clone's real window out onto the monitor."""
    desk = hands.desktop()
    if not desk:
        return {"shown": False, "detail": "the clone's screen is not up"}
    _placement().write_text("out", encoding="utf-8")
    time.sleep(1.2)                       # it checks once a second
    user32.SetForegroundWindow(desk)
    return {"shown": True}


def dock():
    """Put it back inside Shishya's window."""
    _placement().write_text("in", encoding="utf-8")
    return {"docked": True}
