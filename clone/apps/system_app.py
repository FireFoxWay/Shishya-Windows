#!/usr/bin/env python3
"""
System — what the sandbox is using, and what you are giving it. Runs INSIDE the sandbox.

On the Mac the numbers came from the VM's /proc. Here the sandbox is not a
machine of its own, so the honest numbers are the machine's — cores and
memory as Windows reports them — plus the one limit that is the sandbox's:
the job's memory ceiling. Reading them costs almost nothing; a monitor that
loads the machine it is monitoring is telling you about itself.
"""

import ctypes
import json
import shutil
import sys
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt, QTimer   # noqa: E402
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QProgressBar, QSlider,   # noqa: E402
                               QVBoxLayout, QWidget)

import common   # noqa: E402

LOOK = common.SHARED / ".desktop.json"


class FILETIME(ctypes.Structure):
    _fields_ = [("lo", wintypes.DWORD), ("hi", wintypes.DWORD)]


def cpu_times():
    idle, kernel, user = FILETIME(), FILETIME(), FILETIME()
    ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    v = lambda f: (f.hi << 32) | f.lo   # noqa: E731
    return v(idle), v(kernel) + v(user)


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def memory():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return m.ullTotalPhys - m.ullAvailPhys, m.ullTotalPhys


def meter(name):
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, 6, 0, 0)
    row = QHBoxLayout()
    row.addWidget(kit.label(name), 1)
    value = kit.label("", role="muted")
    row.addWidget(value)
    col.addLayout(row)
    bar = QProgressBar()
    bar.setAccessibleName(name)
    bar.setRange(0, 1000)
    bar.setTextVisible(False)
    col.addWidget(bar)
    return box, bar, value


class SystemApp(kit.Window):
    def __init__(self):
        super().__init__("System", 620, 600)
        self.last = cpu_times()
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(kit.label("System", role="title"))
        root.addWidget(kit.label("RIGHT NOW", role="section"))
        for attr, name in (("cpu", "Processor"), ("mem", "Memory"), ("disk", "Disk")):
            box, bar, value = meter(name)
            setattr(self, attr, (bar, value))
            root.addWidget(box)
        self.note = kit.label("", role="muted", wrap=True)
        root.addWidget(self.note)

        root.addWidget(kit.label("WHAT THE DESKTOP MAY SPEND", role="section"))
        self.live = QCheckBox("Animate the wallpaper")
        self.live.setAccessibleName("Animate the wallpaper")
        self.live.toggled.connect(self.on_live)
        root.addWidget(self.live)
        root.addWidget(kit.label("The live wallpapers cost a few percent of one core. They "
                                 "already stop on their own while the AI is working; turn this "
                                 "off to stop them entirely.", role="muted", wrap=True))
        root.addWidget(kit.label("Frames per second", role="muted"))
        self.fps = QSlider(Qt.Horizontal)
        self.fps.setRange(4, 24)
        self.fps.setAccessibleName("Frames per second")
        self.fps.valueChanged.connect(self.on_fps)
        root.addWidget(self.fps)

        root.addWidget(kit.label("THE SANDBOX'S SHARE OF THE MACHINE", role="section"))
        root.addWidget(kit.label(
            "The clone runs in a Windows AppContainer, inside one job capped at 8 GB of memory. "
            "It has no network unless you allow it from the panel, and can open no file outside "
            "shared\\. None of that is something the clone can change from in here.", wrap=True))
        root.addStretch(1)
        self.load_look()
        self.refresh()
        tick = QTimer(self)
        tick.timeout.connect(self.refresh)
        tick.start(2000)

    def load_look(self):
        try:
            self.look = json.loads(LOOK.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.look = {}
        self.live.blockSignals(True)
        self.live.setChecked(self.look.get("wallpaper") in ("galaxy", "matrix"))
        self.live.blockSignals(False)
        self.fps.blockSignals(True)
        self.fps.setValue(int(self.look.get("fps", 12)))
        self.fps.blockSignals(False)

    def save_look(self):
        LOOK.write_text(json.dumps(self.look, indent=2), encoding="utf-8")

    def on_live(self, on):
        if on:
            self.look["wallpaper"] = self.look.get("last_live", "galaxy")
        else:
            if self.look.get("wallpaper") in ("galaxy", "matrix"):
                self.look["last_live"] = self.look["wallpaper"]
            self.look["wallpaper"] = "#10151c"
        self.save_look()

    def on_fps(self, value):
        self.look["fps"] = int(value)
        self.save_look()

    def refresh(self):
        idle, total = cpu_times()
        d_idle, d_total = idle - self.last[0], total - self.last[1]
        self.last = (idle, total)
        use = 1 - d_idle / d_total if d_total else 0.0
        self.cpu[0].setValue(int(use * 1000))
        self.cpu[1].setText(f"{use * 100:.0f}%")
        used, total_mem = memory()
        self.mem[0].setValue(int(1000 * used / total_mem) if total_mem else 0)
        self.mem[1].setText(f"{used / 1e9:.1f} of {total_mem / 1e9:.1f} GB")
        try:
            usage = shutil.disk_usage(str(common.SHARED))
            self.disk[0].setValue(int(1000 * usage.used / usage.total))
            self.disk[1].setText(f"{usage.used / 1e9:.0f} of {usage.total / 1e9:.0f} GB")
        except OSError:
            self.disk[1].setText("—")
        try:
            state = common.STATE.read_text(encoding="utf-8").strip() or "idle"
        except OSError:
            state = "idle"
        self.note.setText(
            "The AI is working — the wallpaper has stopped animating so the cores go to it."
            if state == "working" else
            "Something is busy. If it is not the AI, check what is running." if use > 0.7 else
            "Idle. The model runs outside the sandbox, so it does not show up here until "
            "a script runs.")


if __name__ == "__main__":
    kit.application("System")
    sys.exit(kit.run(SystemApp()))
