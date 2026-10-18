#!/usr/bin/env python3
"""
Shishya — the dashboard you talk to.

Everything else here is a tool you operate: you choose Training Data, you
choose Make a Document. This is the opposite. You say what you want in
your own words and it decides what to do with your material — answer from
it, build a spreadsheet, draft a document, put together a deck, or write
and run a program to work something out.

That decision is the whole point of this app. The doing was already built
and tested; what was missing was something that chooses, which is the
difference between a toolbox and a colleague.

── Why it chooses once per turn ────────────────────────────────────────────

A model this size, left to run a multi-step loop, wanders. It calls a tool,
misreads the result, calls another, and three steps later is confidently
doing the wrong job. So each turn is a single constrained choice — the same
schema-shaped generation that already produces valid spreadsheets — followed
by a known code path. Less clever, far more likely to work in front of
somebody who matters.
"""

import json
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango   # noqa: E402

import common          # noqa: E402
from codegen import RUN_TIMEOUT, DECIDE, DECIDE_SYSTEM, CODE_SYSTEM, _header_row, _describe_sheet, sheet_shape, LISTING_BUDGET, NOTE_BUDGET, describe_billing, describe_material, repair_regex, repair, usable, run_script, NEEDS_BRACKETS, repair_calls, repair_paths, strip_fences  # noqa: E402,F401
import make_app        # noqa: E402
from training_app import Library, for_retrieval, SYSTEM as ANSWER_SYSTEM   # noqa: E402


class ChatApp(Gtk.Window):
    def __init__(self):
        super().__init__(title="Shishya")
        self.set_default_size(880, 760)
        self.connect("destroy", Gtk.main_quit)
        self.library = None
        self.busy = False
        self.history = []

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.add(root)

        bar = Gtk.Box(spacing=10, margin=12)
        title = Gtk.Label(xalign=0)
        title.set_markup("<b>Shishya</b>")
        bar.pack_start(title, False, False, 0)
        self.subtitle = Gtk.Label(xalign=0)
        self.subtitle.set_opacity(.65)
        bar.pack_start(self.subtitle, True, True, 0)
        add = Gtk.Button(label="Add sources")
        add.get_accessible().set_name("Add sources")
        add.connect("clicked", self.on_add_sources)
        bar.pack_end(add, False, False, 0)

        reload_btn = Gtk.Button(label="Reread")
        reload_btn.get_accessible().set_name("Reread")
        reload_btn.connect("clicked", lambda _b: self.read_material())
        bar.pack_end(reload_btn, False, False, 0)
        root.pack_start(bar, False, False, 0)

        # ── conversation ──
        self.thread = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                              margin=14)
        scroll = Gtk.ScrolledWindow()
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroll.add(self.thread)
        self.scroll = scroll
        root.pack_start(scroll, True, True, 0)

        # ── say something ──
        row = Gtk.Box(spacing=8, margin=12)
        self.entry = Gtk.Entry(
            placeholder_text="Tell me what you need — in your own words")
        self.entry.get_accessible().set_name("Message")
        self.entry.connect("activate", self.on_send)
        row.pack_start(self.entry, True, True, 0)
        self.send = Gtk.Button(label="Send")
        self.send.get_accessible().set_name("Send")
        self.send.connect("clicked", self.on_send)
        row.pack_end(self.send, False, False, 0)
        root.pack_start(row, False, False, 0)

        # Drop on the whole window rather than a strip: people aim at the
        # conversation, and a target two pixels wide reads as broken.
        self.drag_dest_set(Gtk.DestDefaults.ALL, [], Gdk.DragAction.COPY)
        self.drag_dest_add_uri_targets()
        self.connect("drag-data-received", self.on_drop)

        # Files also arrive from the control panel, so the folder is watched
        # rather than waiting to be told. Whoever put the file there should
        # not have to remember to announce it.
        self._seen = self.material_fingerprint()
        GLib.timeout_add_seconds(3, self.watch_material)

        self.read_material()
        self.say("shishya",
                 "I've read everything in your Training Data folder. Tell me what "
                 "you need and I'll work out how to make it — an answer, a "
                 "spreadsheet, a document, a deck, or a program if the answer has "
                 "to be counted out of the data.")

    # ── material ────────────────────────────────────────────────────────────

    def read_material(self):
        self.library = Library()
        names = []
        common.TRAINING.mkdir(parents=True, exist_ok=True)
        for p in sorted(common.TRAINING.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                self.library.add(p)
                names.append(p.name)
        self.files = names
        self.subtitle.set_text(
            f"{len(names)} documents · {len(self.library.chunks)} pieces"
            if names else "no material yet — put files in Training Data")

    def material_fingerprint(self):
        try:
            return {p.name: p.stat().st_mtime for p in common.TRAINING.iterdir()
                    if p.is_file() and not p.name.startswith(".")}
        except OSError:
            return {}

    def watch_material(self):
        now = self.material_fingerprint()
        if now != self._seen:
            added = sorted(set(now) - set(self._seen))
            self._seen = now
            self.read_material()
            if added:
                self.say("shishya", self.describe_added(added))
        return True

    def describe_added(self, added):
        names = ", ".join(added)
        return (f"I've read {names}. That's {len(self.files)} documents now — "
                f"ask me anything about them.")

    def on_add_sources(self, _btn):
        chooser = Gtk.FileChooserDialog(
            title="Add sources", transient_for=self, action=Gtk.FileChooserAction.OPEN)
        chooser.add_buttons("Cancel", Gtk.ResponseType.CANCEL, "Add", Gtk.ResponseType.OK)
        chooser.set_select_multiple(True)
        if chooser.run() == Gtk.ResponseType.OK:
            self.take(chooser.get_filenames())
        chooser.destroy()

    def on_drop(self, _w, _ctx, _x, _y, data, _info, _time):
        paths = []
        for uri in data.get_uris():
            p = uri[7:] if uri.startswith("file://") else uri
            paths.append(GLib.uri_unescape_string(p, None) or p)
        self.take(paths)

    def take(self, paths):
        """Copy files in and read them.

        Copied rather than referenced: material has to sit inside the sandbox
        for the clone to reach it at all, and a source that vanishes because
        somebody moved the original is worse than one that takes a little
        disk.
        """
        import shutil
        common.TRAINING.mkdir(parents=True, exist_ok=True)
        added = []
        for raw in paths:
            src = Path(raw)
            if not src.is_file():
                continue
            target = common.TRAINING / src.name
            if src.resolve() != target.resolve():
                shutil.copy2(src, target)
            added.append(src.name)
        if not added:
            return
        self._seen = self.material_fingerprint()
        self.read_material()
        self.say("shishya", self.describe_added(added))

    # ── conversation view ───────────────────────────────────────────────────

    def say(self, who, text, kind=""):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        label = Gtk.Label(xalign=0)
        label.set_markup(f"<small><b>{'You' if who == 'you' else 'Shishya'}</b></small>")
        label.set_opacity(.55)
        box.pack_start(label, False, False, 0)

        body = Gtk.Label(xalign=0, label=text)
        # Named so the panel can read replies back without mistaking the
        # user's own message — every bubble is a label otherwise.
        body.get_accessible().set_name("reply" if who != "you" else "yours")
        body.set_line_wrap(True)
        body.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        body.set_selectable(True)
        body.set_max_width_chars(88)
        if kind == "doing":
            body.set_opacity(.7)
        box.pack_start(body, False, False, 0)

        if who == "you":
            box.set_halign(Gtk.Align.END)
        self.thread.pack_start(box, False, False, 0)
        self.thread.show_all()
        GLib.idle_add(self._to_bottom)
        return body

    def _to_bottom(self):
        adj = self.scroll.get_vadjustment()
        adj.set_value(adj.get_upper())
        return False

    # ── the turn ────────────────────────────────────────────────────────────

    def on_send(self, _w):
        if self.busy:
            return
        text = self.entry.get_text().strip()
        if not text:
            return
        self.entry.set_text("")
        self.say("you", text)
        self.busy = True
        self.send.set_sensitive(False)
        common.set_state("working")
        self.working = self.say("shishya", "Thinking about how to do that…", "doing")
        threading.Thread(target=self.work, args=(text,), daemon=True).start()

    def work(self, request):
        try:
            plan = self.decide(request)
        except Exception as e:
            return GLib.idle_add(self.finish, f"I couldn't work out how to do that: {e}")

        GLib.idle_add(self.update, plan.get("because", "Working on it…"))
        action = plan.get("action", "answer")
        brief = plan.get("brief") or request

        try:
            if action == "clarify":
                reply = brief
            elif action == "code":
                reply = self.by_code(brief)
            elif action in ("spreadsheet", "document", "deck"):
                reply = self.by_document(action, brief)
            else:
                reply = self.by_answer(brief)
        except Exception as e:
            reply = f"That didn't work: {type(e).__name__}: {e}"

        GLib.idle_add(self.finish, reply)

    # ── the obvious cases, decided without asking ───────────────────────────
    # The model is good at reading a request and bad at holding a six-way
    # choice steady. Asked twice whether "can a student with 68% attendance
    # sit the exam" was a question, it said clarify once and spreadsheet
    # once — a question it answers well, routed to a refusal and then to a
    # file. So the shapes that are unambiguous in English are settled in
    # English, and the model is asked only about the rest.

    # The second line is money vocabulary. "Find the product contributing good
    # sales with a good margin" contains no counting word at all, so it fell
    # through to the model's six-way choice — the one thing it holds badly —
    # for a question that is arithmetic across 17,011 rows and nothing else.
    # These are the words a pharmacy actually uses to ask for a number.
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

    def shortcut(self, request):
        """A settled action, or None to let the model choose."""
        q = request.lower().strip()
        wants_file = any(v in q for v in self.MAKING)

        # Counting beats everything: it is the one thing to never do by eye.
        if any(w in q for w in self.COUNTING) and not wants_file:
            return {"action": "code",
                    "because": "That needs counting across the data, so I'll write "
                               "a program to do it exactly.",
                    "brief": request}

        if not wants_file and (q.endswith("?") or q.startswith(self.ASKING)):
            return {"action": "answer",
                    "because": "Let me check your documents.",
                    "brief": request}
        return None

    def decide(self, request):
        settled = self.shortcut(request)
        if settled:
            return settled
        recent = "\n".join(f"- {h}" for h in self.history[-3:])
        prompt = (f"The user's documents are: {', '.join(self.files) or 'none yet'}\n"
                  + (f"Recently:\n{recent}\n" if recent else "")
                  + f"\nRequest: {request}")
        # Every ask here names its job, so the model chosen in the Models
        # app is the one that answers. Without a job name common.ask falls
        # back to the small default, and this window — the front door, the
        # one a judge actually uses — quietly ran all four of its jobs on a
        # 5GB reasoning model while the Models screen showed the 14GB one
        # the owner had picked. Every other app already did this.
        return json.loads(common.ask_job("answers", prompt, system=DECIDE_SYSTEM,
                                         schema=DECIDE, budget=1024))

    # ── the four ways of doing it ───────────────────────────────────────────

    def by_answer(self, brief):
        # Search in English, answer in the language it was asked in. The
        # index is terms; a question in another script matches nothing it
        # should and something it should not.
        query, translated = for_retrieval(brief)
        found = self.library.search(query, k=4)
        if not found:
            return "I can't find anything about that in your material."
        passages = "\n\n".join(f"[from {s}]\n{t}" for s, t in found)
        # The ORIGINAL question, always — the translation was for finding the
        # documents, and the reply must follow the words the person used.
        answer = common.ask_job("answers", f"PASSAGES:\n{passages}\n\nQUESTION: {brief}",
                                system=ANSWER_SYSTEM)
        sources = sorted({s.split(" — ")[0] for s, _ in found})
        self.history.append(f"answered: {brief}")
        return f"{answer.strip()}\n\nRead from: {', '.join(sources)}"

    def by_document(self, action, brief):
        kind = {"spreadsheet": "Spreadsheet", "document": "Document",
                "deck": "Presentation"}[action]
        found = self.library.search(brief, k=10)
        passages = "\n\n".join(f"[from {s}]\n{t}" for s, t in found)
        prompt = (f"{make_app.ASKS[kind]}\n\nWHAT IS NEEDED:\n{brief}\n\n"
                  f"SOURCE MATERIAL — build from these facts and invent no "
                  f"others:\n{passages}\n\nGive it a short filename, no extension.")
        spec = json.loads(common.ask_job("documents", prompt,
                                         schema=make_app.SCHEMAS[kind], budget=4096))
        path = make_app.WRITERS[kind](spec)
        self.history.append(f"made {path.name}")
        return (f"Made {path.name} — it's in your Work folder.\n"
                f"Built from: {', '.join(sorted({s.split(' — ')[0] for s, _ in found}))}")

    def by_code(self, brief):
        """Counting, totalling and ranking go through a program.

        The model is unreliable doing arithmetic across rows by eye — it
        misses rows and occasionally invents a figure. Code that reads the
        file is exact, and the code is on screen to be checked.

        It gets one attempt to fix its own mistakes. The slips are the kind a
        person makes and spots instantly: `idxmin` written without its
        brackets, so pandas was handed the method instead of the number and
        died with an unhashable DataFrame. The reasoning was right and one
        character was wrong. Showing it the traceback is what a person would
        do, and it is far more likely to work than any amount of instruction
        about brackets in advance.
        """
        listing = describe_material()
        code = repair(common.ask_job(
            "code", f"{listing}\n\nWrite a Python script that: {brief}",
            system=CODE_SYSTEM, budget=6144))
        if not usable(code):
            return "I couldn't write a program for that. Try narrowing it down."

        out, err = run_script(code)
        attempts = 1

        if err and not out:
            GLib.idle_add(self.update,
                          "The program hit an error — reading it and trying again.")
            fixed = repair(common.ask_job(
                "code",
                f"{listing}\n\nThis script was meant to: {brief}\n\n"
                f"It failed. Here it is:\n\n{code}\n\n"
                f"The error:\n{err[-1500:]}\n\n"
                f"Return the corrected script, complete, and nothing else.",
                system=CODE_SYSTEM, budget=6144))
            if usable(fixed):
                out2, err2 = run_script(fixed)
                attempts = 2
                if out2:
                    code, out, err = fixed, out2, err2

        self.history.append(f"computed: {brief}")
        note = "" if attempts == 1 else "\n(the first attempt failed; this is the corrected one)"

        if err and not out:
            return (f"I wrote a program twice and it still failed:\n\n{code}\n\n{err}")
        return (f"I worked it out with a program:\n\n{out}\n\n"
                f"— here is what I ran, so you can check it —{note}\n\n{code}")

    # ── finishing ───────────────────────────────────────────────────────────

    def update(self, text):
        self.working.set_text(text)
        return False

    def finish(self, reply):
        self.say("shishya", reply)
        self.busy = False
        self.send.set_sensitive(True)
        common.set_state("idle")
        self.entry.grab_focus()
        return False



if __name__ == "__main__":
    ChatApp().show_all()
    Gtk.main()
