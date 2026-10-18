#!/usr/bin/env python3
"""
CSMA — the credit score maintaining assistant. Runs INSIDE the sandbox.

Reads the accounts entered in Banking and says what those numbers say about
the five things a credit score is made of. It does not predict a score — no
formula outside a bureau can, and one that produced a number here would be
believed. It recommends no product and gives no financial advice.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget   # noqa: E402

import common   # noqa: E402
import money    # noqa: E402

DISCLAIMER = ("This is not a credit score and not a prediction of one. Only a bureau computes "
              "your score, from data this machine has never seen. Everything below is "
              "arithmetic on the figures you entered, plus the published breakdown of what a "
              "score is made of. It is not financial advice.")


class CreditApp(kit.Window):
    def __init__(self):
        super().__init__("Credit Assistant", 760, 660)
        common.SHARED.mkdir(parents=True, exist_ok=True)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(16, 14, 16, 14)
        root.addWidget(kit.label("Credit assistant", role="title"))
        self.headline = kit.label("", name="headline")
        root.addWidget(self.headline)
        root.addWidget(kit.label(DISCLAIMER, role="muted", wrap=True))
        self.inner = QWidget()
        self.col = QVBoxLayout(self.inner)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.inner)
        root.addWidget(scroll, 1)
        root.addWidget(kit.button("Read my accounts again", self.refresh))
        self.refresh()

    def line(self, text, dim=False):
        self.col.addWidget(kit.label(text, role="muted" if dim else None, wrap=True))

    def section(self, title):
        self.col.addWidget(kit.label(f"<b>{title}</b>"))

    def refresh(self):
        while self.col.count():
            w = self.col.takeAt(0).widget()
            if w:
                w.deleteLater()
        use = money.utilisation()
        self.headline.setText("Card utilisation: —  (no card recorded)" if use is None else
                              f"Card utilisation: <b>{use}%</b>  ·  the usual guidance is under 30%")
        self.section("What your own numbers say")
        notes = money.standing()
        if not notes:
            self.line("Nothing to report. Add your accounts in Banking first.", dim=True)
        for level, text in notes:
            self.line(("!  " if level == "watch" else "·  ") + text)
        self.section("What a score is made of")
        for name, weight, what in money.FACTORS:
            self.line(f"{weight}%   {name} — {what}")
        self.section("Falling due in the next fortnight")
        soon = money.due_soon(14)
        if not soon:
            self.line("Nothing. Payment history is the largest single factor, so an empty "
                      "list here is the good outcome.", dim=True)
        for r in soon:
            when = "today" if r["in_days"] == 0 else f"in {r['in_days']} day(s)"
            self.line(f"·  {r['what']} — ₹{r['amount']:,.2f}, {when}")
        self.section("What this app will not do")
        self.line("Connect to a bank, or ask for a password, a PIN or an OTP. There is no field "
                  "here that would take one, and the sandbox has no network to send one over.",
                  dim=True)
        self.line("Tell you what to buy, borrow or invest in. That needs somebody licensed to "
                  "give it, and this is not that.", dim=True)
        self.col.addStretch(1)


if __name__ == "__main__":
    kit.application("Credit Assistant")
    sys.exit(kit.run(CreditApp()))
