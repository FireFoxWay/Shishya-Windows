#!/usr/bin/env python3
"""
Shishya — teach a lesson, read what was learned, change it. Runs INSIDE the sandbox.

The procedure is the whole right-hand side and everything else is a button.
The point being made: this is what it learned, in words, and you may change
them.

How teaching works on Windows. Teach me writes traces/.recording; every app
on the clone's screen sees it and records its own steps (kit.Recorder). I'm
done removes it, merges the apps' parts into one trace, and asks the HOST to
work out the procedure — synthesis needs the model at full speed, and the
sandbox asks for it rather than doing it, exactly as before.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import QTimer   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QListWidget, QPlainTextEdit, QSplitter,   # noqa: E402
                               QVBoxLayout)

import common   # noqa: E402

FLAG = common.TRACES / ".recording"


def render(proc):
    lines = [f"# {{{p['name']}}} = {p.get('example', '')}" for p in proc.get("parameters", [])]
    if lines:
        lines.append("")
    for s in proc.get("steps", []):
        lines.append(f"{s['n']}. {s['text']}")
    for w in proc.get("warnings", []):
        lines.append(f"\n! {w}")
    return "\n".join(lines)


class ShishyaApp(kit.Window):
    # Its own buttons are not part of any lesson: pressing "I'm done" is not
    # a step of the job being taught.
    CHROME = True

    def __init__(self):
        super().__init__("Teach a lesson", 880, 620)
        self.recording = None
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        bar = QHBoxLayout()
        self.what = kit.entry("What are you about to teach me?", name="lessonName",
                              accessible="Lesson name")
        bar.addWidget(self.what, 1)
        self.teach = kit.button("Teach me", self.on_teach, primary=True, name="teachMe")
        bar.addWidget(self.teach)
        root.addLayout(bar)
        self.status = kit.label("Name the job, press Teach me, then do it once — in any app "
                                "on this screen.", role="muted", wrap=True, name="status")
        root.addWidget(self.status)

        split = QSplitter()
        self.lessons = QListWidget()
        self.lessons.setAccessibleName("Lessons")
        self.lessons.currentRowChanged.connect(self.on_pick)
        split.addWidget(self.lessons)
        self.text = QPlainTextEdit()
        self.text.setAccessibleName("Procedure")
        split.addWidget(self.text)
        split.setSizes([240, 600])
        root.addWidget(split, 1)

        feet = QHBoxLayout()
        feet.addWidget(kit.label("Run lessons from the control panel — Lessons, Plan, then "
                                 "Run it.", role="muted"), 1)
        feet.addWidget(kit.button("Save changes", self.on_save))
        root.addLayout(feet)
        self.reload()

    # ── recording ──
    def on_teach(self):
        if self.recording:
            run, label = self.recording
            FLAG.unlink(missing_ok=True)
            self.recording = None
            self.teach.setText("Teach me")
            self.status.setText("Got it. Working out what you did…")
            common.set_state("working")
            # A moment for every app to notice and flush its last step.
            QTimer.singleShot(1500, lambda: self.finish(run, label))
            return
        label = self.what.text().strip() or "untitled"
        run = time.strftime("%Y%m%d-%H%M%S")
        (common.TRACES / run / "steps").mkdir(parents=True, exist_ok=True)
        FLAG.write_text(json.dumps({"run": run, "label": label, "started": time.time()}),
                        encoding="utf-8")
        self.recording = (run, label)
        self.teach.setText("I'm done")
        self.status.setText("Watching. Do the job once, then press I'm done.")
        common.set_state("wheel")

    def finish(self, run, label):
        folder = common.TRACES / run
        steps = kit.merge_trace(folder, label)
        if not steps:
            self.after("Nothing was recorded — did you work in an app on the clone's screen?")
            return
        (folder / ".synth-requested").write_text(str(time.time()), encoding="utf-8")
        self.status.setText(f"{steps} steps recorded. Asking the host to work out the procedure…")
        self.waiting = (folder, time.time())
        self.poll = QTimer(self)
        self.poll.timeout.connect(self.check_synth)
        self.poll.start(1500)

    def check_synth(self):
        folder, began = self.waiting
        if (folder / "procedure.json").exists():
            self.poll.stop()
            self.after("Learned it.")
        elif (folder / ".synth-error").exists():
            self.poll.stop()
            self.after((folder / ".synth-error").read_text(encoding="utf-8")[:300])
        elif time.time() - began > 900:
            self.poll.stop()
            self.after("The host did not answer in fifteen minutes — is the panel running?")

    def after(self, message):
        self.status.setText(message)
        common.set_state("idle")
        self.reload()

    # ── lessons ──
    def reload(self):
        self.lessons.clear()
        self.found = []
        common.TRACES.mkdir(parents=True, exist_ok=True)
        for f in sorted(common.TRACES.glob("*/procedure.json"), reverse=True):
            try:
                proc = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self.found.append((f, proc))
            self.lessons.addItem(proc.get("title", f.parent.name))

    def on_pick(self, row):
        if 0 <= row < len(self.found):
            self.text.setPlainText(render(self.found[row][1]))

    def on_save(self):
        row = self.lessons.currentRow()
        if not 0 <= row < len(self.found):
            return
        path, proc = self.found[row]
        lines = [l.strip() for l in self.text.toPlainText().splitlines()
                 if l.strip() and not l.strip().startswith(("#", "!"))]
        # Steps are re-read from the text, so an edit here really is the
        # procedure — not a note attached to one.
        proc["steps"] = [{"n": i, "text": l.split(". ", 1)[1] if l.split(". ", 1)[0].isdigit()
                          else l, "target": {}, "verify": ""} for i, l in enumerate(lines, 1)]
        proc["edited_by_hand"] = True
        path.write_text(json.dumps(proc, indent=2, ensure_ascii=False), encoding="utf-8")
        self.status.setText("Saved. That is what I will do.")


if __name__ == "__main__":
    kit.application("Teach a lesson")
    sys.exit(kit.run(ShishyaApp()))
