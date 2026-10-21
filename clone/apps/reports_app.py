#!/usr/bin/env python3
"""
Reports — hand over performance files, get back charts and findings.
Runs INSIDE the sandbox.

The engine is vm/reporter.py, shared with the panel's Make-a-report button
and with the Mac: one report generator, several front doors. The report's
shape is written code; the model makes one bounded decision per table.

This is also where a run is scheduled — the window someone is already in
when they think "and I want this every evening". The panel's scheduler
re-reads the same file within the minute.
"""

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt   # noqa: E402
from PySide6.QtGui import QPixmap   # noqa: E402
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel,   # noqa: E402
                               QScrollArea, QSplitter, QVBoxLayout, QWidget)

import common     # noqa: E402
import reporter   # noqa: E402

CHARTABLE = {".xlsx", ".xlsm", ".csv", ".tsv", ".docx"}
REPORTS = common.WORK / "Reports"
SCHEDULES = common.SHARED / ".schedules.json"
AT = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
WHAT = [("audit.py", "Shop audit — takings, profit of the day, month, stock"),
        ("alerts.py", "Alert check — what needs attention, without asking"),
        ("backup.py", "Books backup — a dated copy of the shop's books"),
        ("reporter.py", "Report from the files in Work and Inbox")]


def read_schedules():
    try:
        found = json.loads(SCHEDULES.read_text(encoding="utf-8"))
        return found if isinstance(found, list) else []
    except (OSError, ValueError):
        return []


def write_schedules(items):
    tmp = SCHEDULES.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(SCHEDULES)


class ReportsApp(kit.Window):
    def __init__(self):
        super().__init__("Reports", 960, 660)
        self.busy = False
        self.checks = {}
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)

        bar = QHBoxLayout()
        self.title_box = kit.entry("What is this report called?", name="reportTitle",
                                   accessible="Report title")
        bar.addWidget(self.title_box, 1)
        self.go = kit.button("Make the report", self.on_go, primary=True)
        bar.addWidget(self.go)
        root.addLayout(bar)
        self.status = kit.label("Tick the files, name the report, press Make the report.",
                                role="muted", name="status")
        root.addWidget(self.status)

        split = QSplitter()
        self.files = QWidget()
        self.files_col = QVBoxLayout(self.files)
        left = QScrollArea()
        left.setWidgetResizable(True)
        left.setWidget(self.files)
        split.addWidget(left)
        self.shown = QWidget()
        self.shown_col = QVBoxLayout(self.shown)
        self.shown_col.addStretch(1)
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setWidget(self.shown)
        split.addWidget(right)
        split.setSizes([280, 640])
        root.addWidget(split, 1)

        when = QHBoxLayout()
        when.addWidget(QLabel("Every"))
        self.days = QComboBox()
        self.days.setAccessibleName("Which days")
        self.days.addItem("day", "daily")
        self.days.addItem("weekday", "weekdays")
        when.addWidget(self.days)
        when.addWidget(QLabel("at"))
        self.at = kit.entry("18:00", name="timeOfDay", accessible="Time of day")
        self.at.setText("18:00")
        self.at.setFixedWidth(70)
        when.addWidget(self.at)
        self.what = QComboBox()
        self.what.setAccessibleName("What to run")
        for runner, text in WHAT:
            self.what.addItem(text, runner)
        when.addWidget(self.what, 1)
        when.addWidget(kit.button("Schedule it", self.on_schedule))
        when.addWidget(kit.button("Turn it off", self.on_unschedule))
        root.addLayout(when)
        self.scheduled = kit.label("", role="muted", wrap=True, name="scheduled")
        root.addWidget(self.scheduled)

        self.reload_files()
        self.show_schedules()

    def show_schedules(self):
        items = [i for i in read_schedules() if i.get("enabled", True)]
        if not items:
            self.scheduled.setText("Nothing is scheduled — it runs only when you press "
                                   "Make the report.")
            return
        self.scheduled.setText("Scheduled:  " + "   ·   ".join(
            f"{i.get('label')} every {'weekday' if i.get('days') == 'weekdays' else 'day'} "
            f"at {i.get('at')}" for i in items))

    def on_schedule(self):
        at = self.at.text().strip()
        if not AT.match(at):
            self.status.setText("Give the time as HH:MM on a 24-hour clock — 18:00.")
            return
        runner = self.what.currentData()
        label = dict(WHAT)[runner].split("—")[0].strip()
        items = [i for i in read_schedules() if i.get("runner") != runner]
        items.append({"runner": runner, "label": label, "at": at,
                      "days": self.days.currentData(), "enabled": True, "last": ""})
        write_schedules(items)
        self.show_schedules()
        every = "weekday" if self.days.currentData() == "weekdays" else "day"
        self.status.setText(f"{label} will run by itself at {at}, every {every}. The results "
                            f"appear in the panel, and the files land in the job's folder.")

    def on_unschedule(self):
        runner = self.what.currentData()
        write_schedules([i for i in read_schedules() if i.get("runner") != runner])
        self.show_schedules()
        self.status.setText("Turned off. It will only run when you ask.")

    def reload_files(self):
        while self.files_col.count():
            w = self.files_col.takeAt(0).widget()
            if w:
                w.deleteLater()
        self.checks = {}
        for folder, ticked in ((common.WORK, True), (common.SHARED / "inbox", True),
                               (common.TRAINING, False)):
            files = sorted(p for p in folder.glob("*") if p.is_file()
                           and p.suffix.lower() in CHARTABLE and not p.name.startswith("."))
            if not files:
                continue
            self.files_col.addWidget(kit.label(folder.name.upper(), role="section"))
            for p in files:
                c = QCheckBox(p.name)
                c.setChecked(ticked)
                c.setAccessibleName(p.name)
                self.files_col.addWidget(c)
                self.checks[p] = c
        self.files_col.addStretch(1)

    def on_go(self):
        if self.busy:
            return
        picked = [p for p, c in self.checks.items() if c.isChecked()]
        if not picked:
            self.status.setText("Nothing is ticked — pick at least one file.")
            return
        self.busy = True
        self.go.setEnabled(False)
        while self.shown_col.count() > 1:
            w = self.shown_col.takeAt(0).widget()
            if w:
                w.deleteLater()
        common.set_state("working")
        title = self.title_box.text().strip() or "Report"
        kit.background(lambda: self.make(picked, title), self.done)

    def make(self, picked, title):
        out = REPORTS / time.strftime("%Y%m%d-%H%M%S")
        out.mkdir(parents=True, exist_ok=True)
        sections, findings, skipped = [], [], []
        for path in picked:
            kit.ui(self.status.setText, f"Reading {path.name}…")
            try:
                tables = reporter.tables_from(path)
            except Exception as e:
                skipped.append(f"{path.name} ({type(e).__name__})")
                continue
            if not tables:
                skipped.append(path.name)
                continue
            for name, frame in tables:
                kit.ui(self.status.setText, f"Charting {name}…")
                roles = reporter.by_model(name, frame) or reporter.by_heuristic(frame)
                charts = []
                try:
                    reporter.chart_table(name, frame, roles, out, charts, findings)
                except Exception:
                    pass
                if charts:
                    sections.append((name, charts))
                else:
                    skipped.append(name)
        if not sections:
            return (None, [], "Nothing chartable in those files — I need a table with "
                              "numbers in it.", [])
        (out / "report.html").write_text(
            reporter.html_report(title, sections, findings, skipped,
                                 "Made by Shishya on this machine, from the Reports app."),
            encoding="utf-8")
        pngs = sorted(out.glob("*.png"))
        return (out, findings + [f"(not charted: {s})" for s in skipped],
                f"Done — report.html and {len(pngs)} chart(s) in Work/Reports/{out.name}.", pngs)

    def done(self, result):
        self.busy = False
        self.go.setEnabled(True)
        common.set_state("idle")
        if not isinstance(result, tuple):
            self.status.setText(str(result))
            return
        out, findings, message, pngs = result
        self.status.setText(message)
        at = 0
        if findings:
            lab = kit.label("\n".join(f"• {f}" for f in findings[:10]), wrap=True, name="findings")
            self.shown_col.insertWidget(at, lab)
            at += 1
        for png in pngs:
            pic = QLabel()
            pic.setPixmap(QPixmap(str(png)).scaledToWidth(600, Qt.SmoothTransformation))
            self.shown_col.insertWidget(at, pic)
            at += 1
        if out is not None:
            self.shown_col.insertWidget(at, kit.button(
                "Open the folder", lambda: kit.open_app("files_app.py", out)))


if __name__ == "__main__":
    kit.application("Reports")
    sys.exit(kit.run(ReportsApp()))
