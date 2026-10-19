#!/usr/bin/env python3
"""
Settings — make the clone's screen yours. Runs INSIDE the sandbox.

Wallpaper, accent colour and the wallpaper text, written to a file the
screen re-reads every second — so changes apply live, without restarting the
screen and closing whatever the clone was in the middle of.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt   # noqa: E402
from PySide6.QtGui import QColor, QPainter   # noqa: E402
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout   # noqa: E402

import common   # noqa: E402

CONFIG = common.SHARED / ".desktop.json"
DEFAULTS = {"wallpaper": "ink", "accent": "#0078d4", "icon_size": 96,
            "wallmark": "SHISHYA SANDBOX"}
WALLPAPERS = [("Ink", "ink"), ("Galaxy", "galaxy"), ("Matrix", "matrix"), ("Slate", "#10151c"),
              ("Indigo", "#141a2e"), ("Forest", "#101c17"), ("Plum", "#1b1220"),
              ("Graphite", "#161616")]
ACCENTS = [("Blue", "#0078d4"), ("Teal", "#0f8b8d"), ("Marigold", "#c9821a"),
           ("Rose", "#b4436c"), ("Violet", "#6f5bd1")]


def load():
    try:
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    except (OSError, ValueError):
        return dict(DEFAULTS)


class Swatch(QPushButton):
    """A small rendering of the choice itself — the live wallpapers have no
    single colour, so their swatch is a tiny frame of the real thing."""

    previews = {}

    def __init__(self, heading, name, value):
        super().__init__()
        self.value = value
        self.setFixedSize(66, 40)
        self.setToolTip(name)
        self.setAccessibleName(f"{heading} {name}")

    def paintEvent(self, _e):
        p = QPainter(self)
        if self.value in ("galaxy", "matrix"):
            import wallpaper
            if self.value not in Swatch.previews:
                Swatch.previews[self.value] = wallpaper.LIVE[self.value][0]()
            Swatch.previews[self.value].draw(p, self.width(), self.height())
        elif self.value == "ink":
            p.fillRect(self.rect(), QColor("#171B30"))
        else:
            p.fillRect(self.rect(), QColor(self.value))
        p.setPen(QColor("#0b0c0e"))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()


class SettingsApp(kit.Window):
    def __init__(self):
        super().__init__("Settings", 520, 420)
        self.config = load()
        root = QVBoxLayout(self.body)
        root.setContentsMargins(16, 14, 16, 14)
        root.addWidget(kit.label("Settings", role="title"))
        for heading, options, key in (("Wallpaper", WALLPAPERS, "wallpaper"),
                                      ("Accent", ACCENTS, "accent")):
            root.addWidget(kit.label(heading.upper(), role="section"))
            row = QHBoxLayout()
            for name, value in options:
                s = Swatch(heading, name, value)
                s.clicked.connect(lambda _=False, k=key, v=value: self.pick(k, v))
                row.addWidget(s)
            row.addStretch(1)
            root.addLayout(row)
        root.addWidget(kit.label("WALLPAPER TEXT", role="section"))
        self.mark = kit.entry("", name="wallpaperText", accessible="Wallpaper text")
        self.mark.setText(self.config["wallmark"])
        self.mark.textChanged.connect(lambda t: self.pick("wallmark", t))
        root.addWidget(self.mark)
        self.note = kit.label("Changes apply to the clone's screen within a second.", role="muted")
        root.addWidget(self.note)
        root.addStretch(1)
        root.addWidget(kit.button("Back to defaults", self.reset), alignment=Qt.AlignLeft)

    def pick(self, key, value):
        self.config[key] = value
        CONFIG.write_text(json.dumps(self.config, indent=2), encoding="utf-8")

    def reset(self):
        self.config = dict(DEFAULTS)
        self.mark.setText(self.config["wallmark"])
        CONFIG.write_text(json.dumps(self.config, indent=2), encoding="utf-8")
        self.note.setText("Back to defaults.")


if __name__ == "__main__":
    kit.application("Settings")
    sys.exit(kit.run(SettingsApp()))
