#!/usr/bin/env python3
"""
Findings — what is wrong with your data, without being asked. Runs INSIDE the sandbox.

Six bounded checks, each a program — written or generated — run, and
reported with the program attached, so every finding is checkable by the
person told about it. The checks are vm/shell/checks.py, shared with the Mac.
"""

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QProgressBar, QScrollArea,   # noqa: E402
                               QToolButton, QVBoxLayout, QWidget)

import checks      # noqa: E402
import codegen     # noqa: E402
import common      # noqa: E402

STRIPE = {"found": "#d4541f", "nothing": "#2b8a3e", "failed": "#73737a"}


class FindingsApp(kit.Window):
    def __init__(self):
        super().__init__("Findings", 880, 700)
        self.running = False
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        bar = QHBoxLayout()
        bar.addWidget(kit.label("Findings", role="title"))
        self.status = kit.label("Looks through your spreadsheets for things nobody asked about.",
                                role="muted")
        bar.addWidget(self.status, 1)
        self.go = kit.button("Look through my data", self.on_go, primary=True)
        bar.addWidget(self.go)
        root.addLayout(bar)
        self.progress = QProgressBar()
        self.progress.setRange(0, len(checks.CHECKS))
        self.progress.setValue(0)
        root.addWidget(self.progress)
        self.cards = QWidget()
        self.list = QVBoxLayout(self.cards)
        self.list.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.cards)
        root.addWidget(scroll, 1)

    def on_go(self):
        if self.running:
            return
        self.running = True
        self.go.setEnabled(False)
        while self.list.count() > 1:
            w = self.list.takeAt(0).widget()
            if w:
                w.deleteLater()
        common.set_state("working")
        kit.background(self.work, self.finish)

    def work(self):
        listing = codegen.describe_material()
        found = 0
        for i, (title, brief, why) in enumerate(checks.CHECKS, 1):
            kit.ui(self.progress.setValue, i - 1)
            kit.ui(self.status.setText, f"Checking: {title.lower()}")
            builtin = checks.BUILTIN.get(title)
            try:
                if builtin:
                    code, out, err = "(built in, not generated)", builtin(), ""
                else:
                    code = codegen.repair(common.ask(f"{listing}\n\nWrite a Python script that: {brief}",
                                                     system=codegen.CODE_SYSTEM, budget=5120,
                                                     job="code"))
                    out, err = ("", "no code") if not codegen.usable(code) else checks.run(code)
            except Exception as e:
                code, out, err = "", "", f"{type(e).__name__}: {e}"
            verdict = checks.read_verdict(out)
            if verdict == "found" and out:
                found += 1
            kit.ui(self.card, title, why, verdict if out or verdict == "nothing" else "failed",
                   out, code, err)
        return found

    def card(self, title, why, verdict, out, code, err):
        box = QFrame()
        box.setObjectName("card")
        box.setStyleSheet(f"QFrame#card {{ border-left: 4px solid {STRIPE[verdict]}; }}")
        col = QVBoxLayout(box)
        if verdict == "nothing":
            col.addWidget(kit.label(f"{title} — nothing found"))
        elif verdict == "failed":
            last = (err or "").strip().splitlines()
            col.addWidget(kit.label(f"{title} — could not check: "
                                    f"{last[-1][:90] if last else 'no output'}", wrap=True))
        else:
            col.addWidget(kit.label(f"<b>{html.escape(title)}</b>"))
            col.addWidget(kit.label(why, role="muted", wrap=True))
            result = kit.label(html.escape(out.strip()[:2500]), wrap=True)
            result.setStyleSheet("font-family: Consolas, monospace; font-size: 12px;")
            col.addWidget(result)
            # Folded away but present: a finding you cannot check is just an
            # assertion, and this is the difference.
            toggle = QToolButton()
            toggle.setText("Show the program that found this")
            toggle.setAccessibleName("Show the program")
            toggle.setCheckable(True)
            prog = kit.label(html.escape(code.strip()), wrap=True)
            prog.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #555;")
            prog.setVisible(False)
            toggle.toggled.connect(prog.setVisible)
            col.addWidget(toggle)
            col.addWidget(prog)
        self.list.insertWidget(self.list.count() - 1, box)

    def finish(self, found):
        self.progress.setValue(len(checks.CHECKS))
        found = found if isinstance(found, int) else 0
        self.status.setText(f"{found} thing{'s' if found != 1 else ''} worth a look."
                            if found else "Nothing stood out. That is a good result.")
        self.go.setEnabled(True)
        self.running = False
        common.set_state("idle")


if __name__ == "__main__":
    kit.application("Findings")
    sys.exit(kit.run(FindingsApp()))
