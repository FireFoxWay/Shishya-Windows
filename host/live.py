#!/usr/bin/env python3
"""
Shishya — the clone's screen, live, inside Shishya's own window (Windows).

The picture in host/screen.py is a screenshot: Windows paints the clone's
window into a bitmap, it is compressed, sent to the page and drawn — three
or four times a second at best, which is why the screen inside Shishya felt
laggy while the same screen popped out was perfectly smooth.

This is the way Alt-Tab and the taskbar's previews show other windows: a
DWM thumbnail. Windows' compositor draws the clone's window straight into a
rectangle of Shishya's window, on the GPU, every frame, at any scale — the
same frames you would see popped out. The clone's window stays cloaked and
untouched; nothing is captured or copied by this process. Its menus and
dialogs are windows of their own, so each gets a thumbnail too, laid over
the screen where it would be.

The page says where the screen goes (its rectangle, in page pixels) and
whether it is showing; a thread here keeps the thumbnails matching. Input is
unchanged: clicks on that rectangle still go to the clone through
host/screen.py, checked against the container every time.
"""

import ctypes
import os
import threading
import time
from ctypes import wintypes

import hands
import screen

user32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi

DWM_TNP_RECTDESTINATION = 0x1
DWM_TNP_OPACITY = 0x4
DWM_TNP_VISIBLE = 0x8
DWM_TNP_SOURCECLIENTAREAONLY = 0x10


class _Props(ctypes.Structure):
    _fields_ = [("dwFlags", wintypes.DWORD), ("rcDestination", wintypes.RECT),
                ("rcSource", wintypes.RECT), ("opacity", ctypes.c_ubyte),
                ("fVisible", wintypes.BOOL), ("fSourceClientAreaOnly", wintypes.BOOL)]


dwm.DwmRegisterThumbnail.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.POINTER(ctypes.c_void_p)]
dwm.DwmUnregisterThumbnail.argtypes = [ctypes.c_void_p]
dwm.DwmUpdateThumbnailProperties.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Props)]

_lock = threading.Lock()
_want = {"rect": None, "dpr": 1.0, "visible": False}
_thumbs = {}            # source hwnd -> (thumbnail handle, last destination)
_thread = {"t": None}


_host = {"hwnd": None}


def _host_window():
    """Shishya's own main window — a thumbnail can only be drawn into a
    top-level window of the process that asks for it."""
    h = _host["hwnd"]
    if h and user32.IsWindow(h):
        return h
    found = []
    me = os.getpid()
    Enum = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def each(h, _):
        if user32.IsWindowVisible(h) and hands._pid_of(h) == me:
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(h, buf, 64)
            if buf.value == "Shishya":
                found.append(h)
                return False
        return True
    user32.EnumWindows(Enum(each), 0)
    _host["hwnd"] = found[0] if found else None
    return _host["hwnd"]


def _register(dest, src):
    th = ctypes.c_void_p()
    if dwm.DwmRegisterThumbnail(dest, src, ctypes.byref(th)) != 0:
        return None
    return th


def _place(th, rect, client_only):
    p = _Props()
    p.dwFlags = (DWM_TNP_RECTDESTINATION | DWM_TNP_VISIBLE | DWM_TNP_OPACITY
                 | DWM_TNP_SOURCECLIENTAREAONLY)
    p.rcDestination = wintypes.RECT(*rect)
    p.opacity, p.fVisible, p.fSourceClientAreaOnly = 255, True, bool(client_only)
    dwm.DwmUpdateThumbnailProperties(th, ctypes.byref(p))


def _drop(src):
    th, _ = _thumbs.pop(src)
    dwm.DwmUnregisterThumbnail(th)


def _drop_all():
    for src in list(_thumbs):
        _drop(src)


def _frame():
    """One pass: the screen's thumbnail where the page wants it, and one
    for each of the clone's menus and dialogs, in front, where they are."""
    with _lock:
        want = dict(_want)
    desk = hands.desktop()
    dest = _host_window() if want["visible"] and want["rect"] and desk else None
    if not dest:
        _drop_all()
        return False
    k = want["dpr"]
    x, y, w, h = (round(v * k) for v in want["rect"])
    if w <= 0 or h <= 0:
        _drop_all()
        return False

    # Device pixels of the clone's screen per device pixel of the picture.
    src_rect = wintypes.RECT()
    user32.GetClientRect(desk, ctypes.byref(src_rect))
    sw = src_rect.right or 1
    scale = w / sw
    ox, oy = screen._origin(desk)

    layers = [(desk, (x, y, x + w, y + h), True)]
    for pop in screen._popups(desk):            # back to front
        r = wintypes.RECT()
        user32.GetWindowRect(pop, ctypes.byref(r))
        layers.append((pop, (x + round((r.left - ox) * scale), y + round((r.top - oy) * scale),
                             x + round((r.right - ox) * scale), y + round((r.bottom - oy) * scale)),
                       False))

    seen = set()
    for src, rect, client_only in layers:
        seen.add(src)
        have = _thumbs.get(src)
        if have and have[1] == rect:
            continue
        if not have:
            th = _register(dest, src)
            if th is None:
                if src == desk:
                    _drop_all()
                    return False
                continue
            # A new menu must be drawn over everything registered before it:
            # thumbnails stack in the order they were registered.
            have = (th, None)
        _place(have[0], rect, client_only)
        _thumbs[src] = (have[0], rect)
    for src in [s for s in _thumbs if s not in seen]:
        _drop(src)
    screen._mark_watched()                       # the wallpaper animates while seen
    return True


def _run():
    while True:
        try:
            showing = _frame()
        except Exception:                        # noqa: BLE001 — never take the window down
            _drop_all()
            showing = False
        time.sleep(0.03 if showing else 0.25)


def set_view(rect=None, dpr=1.0, visible=False):
    """Where the page wants the screen: rect is (x, y, width, height) in page
    pixels, dpr its devicePixelRatio. Returns whether the live view is on —
    when it is not, the page falls back to the picture."""
    with _lock:
        _want.update(rect=tuple(rect) if rect else None, dpr=float(dpr or 1.0),
                     visible=bool(visible))
    if not _thread["t"]:
        _thread["t"] = threading.Thread(target=_run, daemon=True, name="live-screen")
        _thread["t"].start()
    if not visible:
        return {"live": False}
    # Answer with whether it can work, so the page knows at once.
    desk = hands.desktop()
    dest = _host_window()
    if not (desk and dest):
        return {"live": False}
    probe = _register(dest, desk)
    if probe is None:
        return {"live": False}
    dwm.DwmUnregisterThumbnail(probe)
    return {"live": True}
