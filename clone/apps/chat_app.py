#!/usr/bin/env python3
"""
Shishya — the dashboard you talk to. Runs INSIDE the sandbox.

Everything else here is a tool you operate. This is the opposite: you say
what you want in your own words and it decides what to do with your material
— answer from it, build a spreadsheet, draft a document, put together a
deck, or write and run a program to work something out.

The Qt window for the Windows clone. The deciding and the doing are the same
code the Mac's GTK chat runs (vm/shell: library, documents, codegen); see
vm/shell/chat_app.py for why each turn is ONE constrained choice followed by
a known code path rather than a loop.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt, QTimer   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QScrollArea, QVBoxLayout, QWidget)   # noqa: E402

import codegen     # noqa: E402
import common      # noqa: E402
import documents   # noqa: E402
from library import SYSTEM as ANSWER_SYSTEM, Library, for_retrieval   # noqa: E402

GREETING = ("I've read everything in your Training Data folder. Tell me what you need "
            "and I'll work out how to make it — an answer, a spreadsheet, a document, "
            "a deck, or a program if the answer has to be counted out of the data.")

# The shapes that are unambiguous in English are settled in English; the model
# is asked only about the rest (vm/shell/chat_app.py has the whole argument).
COUNTING = ("how many", "how much", "count ", "total ", "sum ", "average",
            "how often", "per category", "each category", "breakdown",
            "most ", "least ", "highest", "lowest", "rank", "top ",
            "margin", "profit", "contribut", "revenue", "turnover",
            "sales value", "best ", "worst ", "growth", "moving",
            "best sell", "top sell", "slowest", "fastest")
ASKING = ("can ", "could ", "is ", "are ", "does ", "do ", "did ", "should ",
          "what ", "which ", "who ", "when ", "why ", "where ", "how ")
MAKING = ("make", "build", "create", "draft", "write", "produce", "prepare",
          "give me", "put together")


def shortcut(request):
    q = request.lower().strip()
    wants_file = any(v in q for v in MAKING)
    if any(w in q for w in COUNTING) and not wants_file:
        return {"action": "code", "brief": request,
                "because": "That needs counting across the data, so I'll write a "
                           "program to do it exactly."}
    if not wants_file and (q.endswith("?") or q.startswith(ASKING)):
        return {"action": "answer", "because": "Let me check your documents.",
                "brief": request}
    return None


class ChatApp(kit.Window):
    def __init__(self):
        super().__init__("Shishya", 880, 700)
        self.library = Library()
        self.files = []
        self.busy = False
        self.history = []

        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        bar = QHBoxLayout()
        bar.addWidget(kit.label("Shishya", role="title"))
        self.subtitle = kit.label("", role="muted")
        bar.addWidget(self.subtitle, 1)
        bar.addWidget(kit.button("Reread", self.read_material))
        bar.addWidget(kit.button("Add sources", self.on_add_sources))
        root.addLayout(bar)

        self.thread = QWidget()
        self.lines = QVBoxLayout(self.thread)
        self.lines.addStretch(1)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.thread)
        root.addWidget(self.scroll, 1)

        # What the panel's Ask reads back: the newest thing said, on a control
        # with a name the hands know (host/hands.py read_chat).
        self.last = kit.label("", name="lastReply")
        self.last.setMaximumHeight(1)
        root.addWidget(self.last)

        row = QHBoxLayout()
        self.entry = kit.entry("Tell me what you need — in your own words", name="message",
                               accessible="Message")
        self.entry.returnPressed.connect(self.on_send)
        row.addWidget(self.entry, 1)
        self.send = kit.button("Send", self.on_send, primary=True, name="send")
        row.addWidget(self.send)
        root.addLayout(row)

        self.setAcceptDrops(True)
        self._seen = self.fingerprint()
        watch = QTimer(self)
        watch.timeout.connect(self.watch)
        watch.start(3000)
        self.read_material()
        self.say("shishya", GREETING)

    # ── material ──
    def read_material(self):
        self.library = Library()
        common.TRAINING.mkdir(parents=True, exist_ok=True)
        self.files = []
        for p in sorted(common.TRAINING.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                self.library.add(p)
                self.files.append(p.name)
        self.subtitle.setText(f"{len(self.files)} documents · {len(self.library.chunks)} pieces"
                              if self.files else "no material yet — put files in Training Data")

    def fingerprint(self):
        try:
            return {p.name: p.stat().st_mtime for p in common.TRAINING.iterdir()
                    if p.is_file() and not p.name.startswith(".")}
        except OSError:
            return {}

    def watch(self):
        now = self.fingerprint()
        if now != self._seen:
            added = sorted(set(now) - set(self._seen))
            self._seen = now
            self.read_material()
            if added:
                self.say("shishya", f"I've read {', '.join(added)}. That's {len(self.files)} "
                                    f"documents now — ask me anything about them.")

    def on_add_sources(self):
        self.take(kit.open_files(self, "Add sources", common.SHARED / "inbox", many=True))

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        self.take([Path(u.toLocalFile()) for u in e.mimeData().urls()])

    def take(self, paths):
        import shutil
        common.TRAINING.mkdir(parents=True, exist_ok=True)
        added = []
        for src in paths:
            if Path(src).is_file():
                target = common.TRAINING / Path(src).name
                if Path(src).resolve() != target.resolve():
                    shutil.copy2(src, target)
                added.append(Path(src).name)
        if added:
            self._seen = self.fingerprint()
            self.read_material()
            self.say("shishya", f"I've read {', '.join(added)}. That's {len(self.files)} "
                                f"documents now — ask me anything about them.")

    # ── the conversation ──
    def say(self, who, text, doing=False):
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        head = kit.label("YOU" if who == "you" else "SHISHYA", role="section")
        body = kit.label(text, wrap=True)
        body.setAccessibleName("yours" if who == "you" else "reply")
        if doing:
            body.setProperty("role", "muted")
        if who == "you":
            col.setAlignment(Qt.AlignRight)
            head.setAlignment(Qt.AlignRight)
            body.setAlignment(Qt.AlignRight)
        col.addWidget(head)
        col.addWidget(body)
        self.lines.insertWidget(self.lines.count() - 1, box)
        if who != "you":
            self.last.setText(text)
            self.last.setAccessibleName(text[:4000])
        QTimer.singleShot(50, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()))
        return body

    def on_send(self):
        if self.busy:
            return
        text = self.entry.text().strip()
        if not text:
            return
        self.entry.clear()
        self.say("you", text)
        self.busy = True
        self.send.setEnabled(False)
        common.set_state("working")
        self.working = self.say("shishya", "Thinking about how to do that…", doing=True)
        kit.background(lambda: self.work(text), self.finish)

    def update_working(self, text):
        self.working.setText(text)
        self.last.setAccessibleName(text)

    def work(self, request):
        try:
            plan = shortcut(request) or self.decide(request)
        except Exception as e:
            return f"I couldn't work out how to do that: {e}"
        kit.ui(self.update_working, plan.get("because", "Working on it…"))
        action, brief = plan.get("action", "answer"), plan.get("brief") or request
        try:
            if action == "clarify":
                return brief
            if action == "code":
                return self.by_code(brief)
            if action in ("spreadsheet", "document", "deck"):
                return self.by_document(action, brief)
            return self.by_answer(brief)
        except Exception as e:
            return f"That didn't work: {type(e).__name__}: {e}"

    def decide(self, request):
        recent = "\n".join(f"- {h}" for h in self.history[-3:])
        prompt = (f"The user's documents are: {', '.join(self.files) or 'none yet'}\n"
                  + (f"Recently:\n{recent}\n" if recent else "") + f"\nRequest: {request}")
        return json.loads(common.ask_job("answers", prompt, system=codegen.DECIDE_SYSTEM,
                                         schema=codegen.DECIDE, budget=1024))

    def by_answer(self, brief):
        query, _ = for_retrieval(brief)
        found = self.library.search(query, k=4)
        if not found:
            return "I can't find anything about that in your material."
        passages = "\n\n".join(f"[from {s}]\n{t}" for s, t in found)
        answer = common.ask_job("answers", f"PASSAGES:\n{passages}\n\nQUESTION: {brief}",
                                system=ANSWER_SYSTEM)
        self.history.append(f"answered: {brief}")
        sources = sorted({s.split(' — ')[0] for s, _ in found})
        return f"{answer.strip()}\n\nRead from: {', '.join(sources)}"

    def by_document(self, action, brief):
        kind = {"spreadsheet": "Spreadsheet", "document": "Document", "deck": "Presentation"}[action]
        found = self.library.search(brief, k=10)
        passages = "\n\n".join(f"[from {s}]\n{t}" for s, t in found)
        prompt = (f"{documents.ASKS[kind]}\n\nWHAT IS NEEDED:\n{brief}\n\n"
                  f"SOURCE MATERIAL — build from these facts and invent no others:\n"
                  f"{passages}\n\nGive it a short filename, no extension.")
        spec = json.loads(common.ask_job("documents", prompt, schema=documents.SCHEMAS[kind],
                                         budget=4096))
        path = documents.WRITERS[kind](spec)
        self.history.append(f"made {path.name}")
        return (f"Made {path.name} — it's in your Work folder.\n"
                f"Built from: {', '.join(sorted({s.split(' — ')[0] for s, _ in found}))}")

    def by_code(self, brief):
        listing = codegen.describe_material()
        code = codegen.repair(common.ask_job("code", f"{listing}\n\nWrite a Python script that: {brief}",
                                             system=codegen.CODE_SYSTEM, budget=6144))
        if not codegen.usable(code):
            return "I couldn't write a program for that. Try narrowing it down."
        out, err = codegen.run_script(code)
        attempts = 1
        if err and not out:
            kit.ui(self.update_working, "The program hit an error — reading it and trying again.")
            fixed = codegen.repair(common.ask_job(
                "code", f"{listing}\n\nThis script was meant to: {brief}\n\nIt failed. Here it is:"
                        f"\n\n{code}\n\nThe error:\n{err[-1500:]}\n\nReturn the corrected "
                        f"script, complete, and nothing else.",
                system=codegen.CODE_SYSTEM, budget=6144))
            if codegen.usable(fixed):
                out2, err2 = codegen.run_script(fixed)
                attempts = 2
                if out2:
                    code, out, err = fixed, out2, err2
        self.history.append(f"computed: {brief}")
        if err and not out:
            return f"I wrote a program twice and it still failed:\n\n{code}\n\n{err}"
        note = "" if attempts == 1 else "\n(the first attempt failed; this is the corrected one)"
        return (f"I worked it out with a program:\n\n{out}\n\n— here is what I ran, so you "
                f"can check it —{note}\n\n{code}")

    def finish(self, reply):
        self.say("shishya", str(reply))
        self.busy = False
        self.send.setEnabled(True)
        common.set_state("idle")
        self.entry.setFocus()


if __name__ == "__main__":
    kit.application("Shishya")
    sys.exit(kit.run(ChatApp()))
