#!/usr/bin/env python3
"""
Training Data — drop in documents, then ask about them. Runs INSIDE the sandbox.

Read, split, indexed; then a question in plain language gets an answer drawn
only from what was dropped in, with the documents it used named underneath.
Asked to make something instead — "create a comparison table" — it hands the
job to the same writers Make a Document uses. Retrieval and writing are
vm/shell/library.py and documents.py, shared with the Mac.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QPlainTextEdit, QTableWidget,   # noqa: E402
                               QTableWidgetItem, QVBoxLayout)

import common      # noqa: E402
import documents   # noqa: E402
from library import SYSTEM, Library, wants_a_file   # noqa: E402


class TrainingApp(kit.Window):
    def __init__(self):
        super().__init__("Training Data", 860, 640)
        self.library = Library()

        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        head = QHBoxLayout()
        head.addWidget(kit.label("Training Data", role="title"))
        self.count = kit.label("nothing yet", role="muted")
        head.addWidget(self.count, 1)
        head.addWidget(kit.button("Add documents", self.on_add))
        root.addLayout(head)

        self.docs = QTableWidget(0, 3)
        self.docs.setObjectName("documents")
        self.docs.setAccessibleName("Documents")
        self.docs.setHorizontalHeaderLabels(["Document", "Pieces", "How it was read"])
        self.docs.horizontalHeader().setStretchLastSection(True)
        self.docs.setColumnWidth(0, 320)
        self.docs.setMaximumHeight(200)
        self.docs.setEditTriggers(QTableWidget.NoEditTriggers)
        root.addWidget(self.docs)
        root.addWidget(kit.label("Drop files anywhere on this window — text, PDF, "
                                 "spreadsheets, documents", role="muted"))

        ask = QHBoxLayout()
        self.entry = kit.entry("Ask something about these documents", name="question",
                               accessible="Question")
        self.entry.returnPressed.connect(self.on_ask)
        ask.addWidget(self.entry, 1)
        self.askbtn = kit.button("Ask", self.on_ask, primary=True, name="ask")
        ask.addWidget(self.askbtn)
        root.addLayout(ask)

        self.answer = QPlainTextEdit()
        self.answer.setObjectName("answer")
        self.answer.setAccessibleName("Answer")
        self.answer.setReadOnly(True)
        root.addWidget(self.answer, 1)

        self.setAcceptDrops(True)
        common.TRAINING.mkdir(parents=True, exist_ok=True)
        for p in sorted(common.TRAINING.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                self.ingest(p)

    def on_add(self):
        for p in kit.open_files(self, "Add documents", common.SHARED / "inbox", many=True):
            self.ingest(self._bring(p))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            self.ingest(self._bring(Path(u.toLocalFile())))

    def _bring(self, path):
        """Material has to sit inside the sandbox to be read at all."""
        target = common.TRAINING / path.name
        if path.is_file() and path.resolve() != target.resolve():
            shutil.copy2(path, target)
        return target

    def ingest(self, path):
        if not path.is_file():
            return
        pieces, how = self.library.add(path)
        r = self.docs.rowCount()
        self.docs.insertRow(r)
        for c, v in enumerate((path.name, str(pieces), how)):
            self.docs.setItem(r, c, QTableWidgetItem(v))
        n = self.docs.rowCount()
        self.count.setText(f"{n} document{'s' if n != 1 else ''}, "
                           f"{len(self.library.chunks)} pieces indexed")

    def on_ask(self):
        question = self.entry.text().strip()
        if not question:
            return
        if not self.library.chunks:
            return self.show_text("Add some documents first — I only answer from what is here.")
        kind = wants_a_file(question)
        found = self.library.search(question, k=10 if kind else 4)
        if not found:
            return self.show_text("Nothing in these documents looks related to that.")
        self.askbtn.setEnabled(False)
        self.show_text(f"Building the {kind.lower()}…" if kind else "Reading…")
        common.set_state("working")
        passages = "\n\n".join(f"[from {s}]\n{t}" for s, t in found)
        sources = "\n".join(f"  · {s}" for s in sorted({s.split(' — ')[0] for s, _ in found}))

        def work():
            if kind:
                return self.build(kind, question, passages, sources)
            try:
                reply = common.ask_job("answers", f"PASSAGES:\n{passages}\n\nQUESTION: {question}",
                                       system=SYSTEM)
            except RuntimeError as e:
                reply = str(e)
            return f"{reply.strip()}\n\nRead from:\n{sources}"
        kit.background(work, self.done)

    def build(self, kind, question, passages, sources):
        prompt = (f"{documents.ASKS[kind]}\n\nWHAT IS NEEDED:\n{question}\n\n"
                  f"SOURCE MATERIAL — build this from the facts below and do not invent "
                  f"competing ones:\n{passages}\n\nGive it a short, sensible filename with "
                  f"no extension.")
        try:
            spec = json.loads(common.ask_job("answers", prompt, schema=documents.SCHEMAS[kind]))
            path = documents.WRITERS[kind](spec)
        except (json.JSONDecodeError, KeyError) as e:
            return f"The model returned something I could not turn into a file: {e}"
        except Exception as e:
            return f"Could not write the file: {e}"
        return f"Made {path.name}\n\nIt is in Work — open Files.\n\nBuilt from:\n{sources}"

    def done(self, text):
        self.show_text(str(text))
        self.askbtn.setEnabled(True)
        common.set_state("idle")

    def show_text(self, text):
        self.answer.setPlainText(text)
        self.answer.setAccessibleName(text[:4000] or "Answer")


if __name__ == "__main__":
    kit.application("Training Data")
    sys.exit(kit.run(TrainingApp()))
