#!/usr/bin/env python3
"""
Inbox — files sent in from the machine outside. Runs INSIDE the sandbox.

Drop a file on the panel and it lands here. This is the only way in: the
sandbox cannot reach out and take a file off your machine, so everything that
arrives was handed over deliberately. Nothing is opened on arrival; it waits
for you to say what it is for — keep it as work, or teach from it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import QTimer   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QTableWidget, QTableWidgetItem,   # noqa: E402
                               QVBoxLayout)

import common   # noqa: E402

INBOX = common.SHARED / "inbox"


class InboxApp(kit.Window):
    def __init__(self):
        super().__init__("Inbox", 640, 460)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(kit.label("Inbox", role="title"))
        self.note = kit.label("", role="muted")
        root.addWidget(self.note)
        self.view = QTableWidget(0, 2)
        self.view.setObjectName("incoming")
        self.view.setAccessibleName("Incoming files")
        self.view.setHorizontalHeaderLabels(["File", "Size"])
        self.view.setColumnWidth(0, 420)
        self.view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.view.setSelectionBehavior(QTableWidget.SelectRows)
        self.view.verticalHeader().hide()
        root.addWidget(self.view, 1)
        feet = QHBoxLayout()
        feet.addStretch(1)
        feet.addWidget(kit.button("Teach from this", lambda: self.move_to(common.TRAINING,
                                                                          "Training Data")))
        feet.addWidget(kit.button("Keep as work", lambda: self.move_to(common.WORK, "Work")))
        feet.addWidget(kit.button("Open", self.on_open))
        root.addLayout(feet)
        self.refresh()
        tick = QTimer(self)
        tick.timeout.connect(self.refresh)
        tick.start(2000)

    def picked(self):
        rows = self.view.selectionModel().selectedRows()
        return INBOX / self.view.item(rows[0].row(), 0).text() if rows else None

    def refresh(self):
        INBOX.mkdir(parents=True, exist_ok=True)
        # .part files are uploads still in flight on the host side.
        files = sorted(p for p in INBOX.iterdir() if p.is_file()
                       and not p.name.startswith(".") and p.suffix != ".part")
        picked = self.picked()
        self.view.setRowCount(0)
        for p in files:
            r = self.view.rowCount()
            self.view.insertRow(r)
            self.view.setItem(r, 0, QTableWidgetItem(p.name))
            self.view.setItem(r, 1, QTableWidgetItem(kit.human(p.stat().st_size)))
            if picked == p:
                self.view.selectRow(r)
        self.note.setText(f"{len(files)} file{'s' if len(files) != 1 else ''} sent from the host"
                          if files else "Nothing waiting. Drop a file on the control panel.")

    def on_open(self):
        p = self.picked()
        if p:
            kit.open_app("files_app.py", INBOX)

    def move_to(self, target, label):
        p = self.picked()
        if not p:
            return
        target.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(target / p.name))
        self.refresh()
        self.note.setText(f"{p.name} → {label}")


if __name__ == "__main__":
    kit.application("Inbox")
    sys.exit(kit.run(InboxApp()))
