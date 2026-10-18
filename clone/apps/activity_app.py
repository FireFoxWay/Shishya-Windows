#!/usr/bin/env python3
"""
Activity — the permission ledger, seen from inside the sandbox.

Everything the clone did, and everything it was refused. The host writes the
ledger; the sandbox is granted read access to that one file and nothing else
in var/. An audit log the audited party can edit is not an audit log.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import QTimer   # noqa: E402
from PySide6.QtGui import QColor   # noqa: E402
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout   # noqa: E402

LEDGER = Path(os.environ.get("SHISHYA_LEDGER") or "/opt/shishya/var/ledger.jsonl")
COLOUR = {"deny": "#c0392b", "allow": "#1e7b45", "info": "#6b7178"}


def read(path, limit=400):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


class ActivityApp(kit.Window):
    def __init__(self):
        super().__init__("Activity", 780, 520)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        self.summary = kit.label("", role="title")
        root.addWidget(self.summary)
        self.view = QTableWidget(0, 4)
        self.view.setAccessibleName("Activity")
        self.view.setHorizontalHeaderLabels(["Time", "", "Action", "Target"])
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setColumnWidth(2, 180)
        self.view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.view.verticalHeader().hide()
        root.addWidget(self.view, 1)
        self.refresh()
        tick = QTimer(self)
        tick.timeout.connect(self.refresh)
        tick.start(3000)

    def refresh(self):
        entries = read(LEDGER)
        self.view.setRowCount(0)
        allowed = denied = 0
        for e in reversed(entries):
            verdict = e.get("verdict", "info")
            allowed += verdict == "allow"
            denied += verdict == "deny"
            r = self.view.rowCount()
            self.view.insertRow(r)
            cells = (time.strftime("%H:%M:%S", time.localtime(e.get("t", 0))), verdict.upper(),
                     e.get("action", ""), str(e.get("target", "")))
            for c, v in enumerate(cells):
                item = QTableWidgetItem(v)
                item.setForeground(QColor(COLOUR.get(verdict, "#6b7178")))
                self.view.setItem(r, c, item)
        self.summary.setText(f"{denied} refused    {allowed} allowed    "
                             f"{len(entries)} entries in total")


if __name__ == "__main__":
    kit.application("Activity")
    sys.exit(kit.run(ActivityApp()))
