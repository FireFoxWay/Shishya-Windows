#!/usr/bin/env python3
"""
Make a Document — say what you need, get a real file. Runs INSIDE the sandbox.

Genuine .xlsx, .docx and .pptx into Work — files that open in Excel, Word and
PowerPoint. The model returns content as JSON and Python writes the file
(vm/shell/documents.py, shared with the Mac, says why).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QHBoxLayout, QPlainTextEdit,   # noqa: E402
                               QRadioButton, QVBoxLayout)

import common      # noqa: E402
import documents   # noqa: E402


class MakeApp(kit.Window):
    def __init__(self):
        super().__init__("Make a Document", 720, 540)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(kit.label("Make a Document", role="title"))

        kinds = QHBoxLayout()
        self.kinds = QButtonGroup(self)
        for i, (name, hint) in enumerate((("Spreadsheet", ".xlsx"), ("Document", ".docx"),
                                          ("Presentation", ".pptx"))):
            b = QRadioButton(f"{name}  {hint}")
            b.setAccessibleName(name)
            b.setObjectName(name.lower())
            b.setChecked(i == 0)
            self.kinds.addButton(b, i)
            kinds.addWidget(b)
        kinds.addStretch(1)
        root.addLayout(kinds)

        self.brief = QPlainTextEdit()
        self.brief.setObjectName("brief")
        self.brief.setAccessibleName("What do you need")
        self.brief.setPlainText("A register of housing scheme applicants for Warangal district, "
                                "with application number, name, income, land holding and status.")
        self.brief.setMaximumHeight(120)
        root.addWidget(self.brief)

        self.use_training = QCheckBox("Use what's in Training Data as source")
        self.use_training.setAccessibleName("Use Training Data")
        root.addWidget(self.use_training)

        feet = QHBoxLayout()
        self.status = kit.label("", role="muted")
        feet.addWidget(self.status, 1)
        self.make = kit.button("Make it", self.on_make, primary=True)
        feet.addWidget(self.make)
        root.addLayout(feet)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setAccessibleName("Result")
        root.addWidget(self.log, 1)

    def kind(self):
        return ("Spreadsheet", "Document", "Presentation")[self.kinds.checkedId()]

    def on_make(self):
        brief = self.brief.toPlainText().strip()
        if not brief:
            return self.say("Say what you need first.")
        self.make.setEnabled(False)
        self.say("Working it out…")
        common.set_state("working")
        kind, use = self.kind(), self.use_training.isChecked()
        kit.background(lambda: self.work(kind, brief, use), self.done)

    def work(self, kind, brief, use):
        source = documents.read_training() if use else ""
        prompt = (f"{documents.ASKS[kind]}\n\nWHAT IS NEEDED:\n{brief}\n"
                  + (f"\nSOURCE MATERIAL — use these facts, do not invent competing ones:\n"
                     f"{source}\n" if source else "")
                  + "\nGive it a short, sensible filename with no extension.")
        try:
            spec = json.loads(common.ask_job("documents", prompt, schema=documents.SCHEMAS[kind]))
            path = documents.WRITERS[kind](spec)
            return f"Made {path.name}\n\nIt is in Work. Open it from Files."
        except (json.JSONDecodeError, KeyError) as e:
            return f"The model returned something unusable: {e}"
        except Exception as e:
            return f"Could not write the file: {e}"

    def done(self, message):
        self.say(str(message))
        self.make.setEnabled(True)
        common.set_state("idle")

    def say(self, text):
        self.status.setText(text.split("\n")[0][:70])
        self.log.setPlainText(text)


if __name__ == "__main__":
    kit.application("Make a Document")
    sys.exit(kit.run(MakeApp()))
