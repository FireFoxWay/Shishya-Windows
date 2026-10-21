#!/usr/bin/env python3
"""
Files — browse what the clone has. Runs INSIDE the sandbox.

    pythonw files_app.py [folder]

Opening is handled explicitly by extension, never by asking Windows to
"open whatever this is" — the clone should not have a general open verb, and
every route out of this window is one we chose. Spreadsheets go to Sheets;
everything else readable is shown as text. An unknown type is shown, not
launched.
"""

import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt, QTimer   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QTableWidget,   # noqa: E402
                               QTableWidgetItem, QVBoxLayout, QWidget)

import common   # noqa: E402

PLACES = [("Work", common.WORK), ("Inbox", common.SHARED / "inbox"),
          ("Training Data", common.TRAINING), ("Lessons", common.TRACES),
          ("Bills", common.WORK / "Bills"), ("Books", common.BILLING)]
SHEETS = {".xlsx", ".xlsm", ".csv"}
READABLE = {".pdf", ".docx", ".pptx", ".odt", ".ods", ".doc", ".xls", ".ppt", ".rtf"}
TEXTY = {".txt", ".md", ".json", ".log", ".csv", ".tsv", ".xml", ".html", ".py", ".jsonl"}


class Viewer(kit.Window):
    """Read-only text: enough to check what a file says, without giving the
    sandbox an editor it has no use for."""

    def __init__(self, title, body):
        super().__init__(title, 760, 560)
        col = QVBoxLayout(self.body)
        col.setContentsMargins(0, 0, 0, 0)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setAccessibleName(title)
        text.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
        text.setPlainText(body)
        col.addWidget(text)


class FilesApp(kit.Window):
    def __init__(self, start=None):
        super().__init__("Files", 880, 580)
        self.here = Path(start) if start else common.WORK
        self.history = []
        self.viewers = []

        root = QVBoxLayout(self.body)
        root.setContentsMargins(10, 10, 10, 10)
        bar = QHBoxLayout()
        self.back = kit.button("Back", self.on_back)
        bar.addWidget(self.back)
        self.where = kit.label("", name="location")
        bar.addWidget(self.where, 1)
        bar.addWidget(kit.button("Refresh", self.load))
        root.addLayout(bar)

        split = QHBoxLayout()
        places = QWidget()
        pcol = QVBoxLayout(places)
        pcol.setContentsMargins(0, 0, 0, 0)
        for name, path in PLACES:
            pcol.addWidget(kit.button(name, lambda p=path: self.go(p)))
        pcol.addStretch(1)
        places.setFixedWidth(150)
        split.addWidget(places)

        self.view = QTableWidget(0, 3)
        self.view.setObjectName("files")
        self.view.setAccessibleName("Files")
        self.view.setHorizontalHeaderLabels(["Name", "Size", "Changed"])
        self.view.setColumnWidth(0, 380)
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.setEditTriggers(QTableWidget.NoEditTriggers)
        self.view.setSelectionBehavior(QTableWidget.SelectRows)
        self.view.verticalHeader().hide()
        self.view.cellDoubleClicked.connect(lambda r, _c: self.open(self.path_at(r)))
        split.addWidget(self.view, 1)
        root.addLayout(split, 1)

        feet = QHBoxLayout()
        self.note = kit.label("", role="muted")
        feet.addWidget(self.note, 1)
        feet.addWidget(kit.button("Copy to Work", self.on_copy))
        feet.addWidget(kit.button("Open", self.on_open, primary=True))
        root.addLayout(feet)

        self.load()
        tick = QTimer(self)
        tick.timeout.connect(self.load)
        tick.start(4000)

    def go(self, path):
        path = Path(path)
        if path != self.here:
            self.history.append(self.here)
        self.here = path
        self.load()

    def on_back(self):
        if self.history:
            self.here = self.history.pop()
            self.load()

    def path_at(self, row):
        item = self.view.item(row, 0)
        return Path(item.data(Qt.UserRole)) if item else None

    def selected(self):
        rows = self.view.selectionModel().selectedRows()
        return self.path_at(rows[0].row()) if rows else None

    def load(self):
        self.here.mkdir(parents=True, exist_ok=True)
        picked = self.selected()
        try:
            entries = sorted(self.here.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError as e:
            self.note.setText(str(e))
            return
        shown = [p for p in entries if not p.name.startswith(".")]
        self.view.setRowCount(0)
        for p in shown:
            try:
                st = p.stat()
            except OSError:
                continue
            r = self.view.rowCount()
            self.view.insertRow(r)
            name = QTableWidgetItem(f"{p.name}\\" if p.is_dir() else p.name)
            name.setData(Qt.UserRole, str(p))
            self.view.setItem(r, 0, name)
            self.view.setItem(r, 1, QTableWidgetItem("" if p.is_dir() else kit.human(st.st_size)))
            self.view.setItem(r, 2, QTableWidgetItem(time.strftime("%d %b %H:%M",
                                                                   time.localtime(st.st_mtime))))
            if picked and p == picked:
                self.view.selectRow(r)
        try:
            shown_at = "shared\\" + str(self.here.relative_to(common.SHARED))
        except ValueError:
            shown_at = str(self.here)
        self.where.setText(shown_at)
        self.back.setEnabled(bool(self.history))
        if not picked:
            self.note.setText("This folder is empty." if not shown else
                              f"{len(shown)} item{'s' if len(shown) != 1 else ''}")

    def on_open(self):
        p = self.selected()
        if p:
            self.open(p)

    def open(self, path):
        if path is None:
            return
        if path.is_dir():
            return self.go(path)
        suffix = path.suffix.lower()
        if suffix in SHEETS:
            kit.open_app("sheet_app.py", path)
            self.note.setText(f"opening {path.name}…")
        elif suffix in READABLE:
            text, how = common.extract(path)
            self.show_viewer(f"{path.name} ({how})", text or f"Nothing readable: {how}")
        elif suffix in TEXTY or path.stat().st_size < 400_000:
            try:
                body = path.read_text(encoding="utf-8", errors="replace")[:400_000]
            except OSError as e:
                body = f"Could not read this file: {e}"
            self.show_viewer(path.name, body)
        else:
            self.note.setText(f"Nothing here opens {suffix or 'this'} — take it from the "
                              f"panel if you need it.")

    def show_viewer(self, title, body):
        v = Viewer(title, body)
        v.show()
        self.viewers.append(v)
        self.note.setText(f"showing {title}")

    def on_copy(self):
        source = self.selected()
        if not source or source.is_dir() or source.parent == common.WORK:
            return
        common.WORK.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, common.WORK / source.name)
        self.note.setText(f"copied {source.name} to Work")


if __name__ == "__main__":
    kit.application("Files")
    sys.exit(kit.run(FilesApp(sys.argv[1] if len(sys.argv) > 1 else None)))
