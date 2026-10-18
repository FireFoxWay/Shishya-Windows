#!/usr/bin/env python3
"""
Browser — the web, when you have deliberately allowed it. Runs INSIDE the sandbox.

The claim was never "this can never reach the internet". It is "it cannot
unless you say so, and when you do, it is in the log". On Windows that rule
is held by the token, not by a firewall: this window is started with the
internetClient capability only while browsing is allowed on the panel, and a
process cannot add a capability to itself. Opened while it is not allowed,
this says so and offers nothing else — and the page would not load anyway.

Qt WebEngine is the browser engine, as Falkon was on the Mac. Its own
sandbox is off because the AppContainer is the sandbox.
"""

import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import QUrl   # noqa: E402
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout   # noqa: E402

import common   # noqa: E402

STATE = common.SHARED / ".browsing"


def allowed():
    try:
        return STATE.read_text(encoding="utf-8").strip() == "on"
    except OSError:
        return False


class BrowserApp(kit.Window):
    def __init__(self):
        super().__init__("Browser", 1100, 720)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(8, 8, 8, 8)
        row = QHBoxLayout()
        self.address = kit.entry("Address, or a search", name="address", accessible="Address")
        self.address.returnPressed.connect(self.on_open)
        row.addWidget(self.address, 1)
        self.go = kit.button("Open", self.on_open, primary=True)
        row.addWidget(self.go)
        root.addLayout(row)
        self.status = kit.label("", wrap=True, name="status")
        root.addWidget(self.status)
        self.view = None
        if allowed():
            from PySide6.QtWebEngineWidgets import QWebEngineView
            self.view = QWebEngineView()
            self.view.setAccessibleName("Page")
            self.view.urlChanged.connect(lambda u: self.address.setText(u.toString()))
            self.view.titleChanged.connect(lambda t: self.status.setText(t))
            root.addWidget(self.view, 1)
            self.status.setText("Browsing is allowed. Type an address and it opens here, "
                                "inside the sandbox.")
        else:
            self.address.setEnabled(False)
            self.go.setEnabled(False)
            self.status.setText(
                "Browsing is switched off. Press ALLOW BROWSING on the control panel to turn "
                "it on — this window will reopen with the web. Every change is written to "
                "the ledger, and the sandbox cannot switch it on for itself.")
            root.addStretch(1)

    def on_open(self):
        if self.view is None:
            return
        where = self.address.text().strip()
        if not where:
            return
        if "." not in where.split("/")[0] and not where.startswith(("http", "about:")):
            where = "https://duckduckgo.com/?q=" + urllib.parse.quote(where)
        elif not where.startswith(("http://", "https://", "about:")):
            where = "https://" + where
        self.view.load(QUrl(where))
        self.status.setText(f"Opening {where}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        print("on" if allowed() else "off")
        raise SystemExit(0)
    kit.application("Browser")
    sys.exit(kit.run(BrowserApp()))
