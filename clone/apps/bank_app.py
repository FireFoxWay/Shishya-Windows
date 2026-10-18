#!/usr/bin/env python3
"""
Banking — your accounts and what goes out of them every month. Runs INSIDE the sandbox.

It does not connect to a bank and there is no field here that would take a
password, a PIN or an OTP — the sandbox has no network to send one over, so
such a field would be a lie as well as a hazard. Every figure is one you
typed in yourself. What it is for: seeing the total. The arithmetic is
vm/shell/money.py, shared with the Mac.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtWidgets import (QHBoxLayout, QTableWidget, QTableWidgetItem, QTabWidget,   # noqa: E402
                               QVBoxLayout, QWidget)

import common   # noqa: E402
import money    # noqa: E402

KINDS = ["current", "savings", "card", "loan", "cash"]
DUES = ["emi", "bill", "rent", "insurance", "subscription", "other"]


def rupees(n):
    return f"₹{float(n or 0):,.2f}"


class Editor(QWidget):
    """A table you can add rows to and delete rows from, saved as a whole —
    a partial write of somebody's accounts is worse than no write."""

    def __init__(self, columns, kinds, load, save, on_change):
        super().__init__()
        self.columns, self.kinds = columns, kinds
        self.load, self.save, self.on_change = load, save, on_change
        col = QVBoxLayout(self)
        self.view = QTableWidget(0, len(columns))
        self.view.setAccessibleName("rows")
        self.view.setHorizontalHeaderLabels([c.title() for c in columns])
        self.view.horizontalHeader().setStretchLastSection(True)
        self.view.itemChanged.connect(lambda *_: self.commit())
        col.addWidget(self.view, 1)
        bar = QHBoxLayout()
        bar.addWidget(kit.button("Add a row", self.on_add))
        bar.addWidget(kit.button("Delete the selected row", self.on_del))
        bar.addStretch(1)
        col.addLayout(bar)
        self.reload()

    def reload(self):
        self.view.blockSignals(True)
        self.view.setRowCount(0)
        for r in self.load():
            self._append([str(r.get(c, "")) for c in self.columns])
        self.view.blockSignals(False)

    def _append(self, values):
        r = self.view.rowCount()
        self.view.insertRow(r)
        for c, v in enumerate(values):
            self.view.setItem(r, c, QTableWidgetItem(v))

    def rows(self):
        return [{c: (self.view.item(r, i).text() if self.view.item(r, i) else "")
                 for i, c in enumerate(self.columns)} for r in range(self.view.rowCount())]

    def commit(self):
        self.save(self.rows())
        self.on_change()

    def on_add(self):
        blank = [""] * len(self.columns)
        blank[0] = f"R{self.view.rowCount() + 1}"
        if "kind" in self.columns:
            blank[self.columns.index("kind")] = self.kinds[0]
        self.view.blockSignals(True)
        self._append(blank)
        self.view.blockSignals(False)
        self.commit()

    def on_del(self):
        rows = sorted({i.row() for i in self.view.selectedIndexes()}, reverse=True)
        for r in rows:
            self.view.removeRow(r)
        if rows:
            self.commit()


class BankApp(kit.Window):
    def __init__(self):
        super().__init__("Banking", 900, 620)
        common.SHARED.mkdir(parents=True, exist_ok=True)
        root = QVBoxLayout(self.body)
        root.setContentsMargins(14, 12, 14, 12)
        root.addWidget(kit.label("Banking", role="title"))
        self.summary = kit.label("", name="summary", wrap=True)
        root.addWidget(self.summary)
        root.addWidget(kit.label("Figures you enter yourself. This app has no connection to any "
                                 "bank and no field that will take a password, a PIN or an OTP "
                                 "— the sandbox has no network to send one over.",
                                 role="muted", wrap=True))
        tabs = QTabWidget()
        tabs.addTab(Editor(money.ACCOUNT_COLUMNS, KINDS, money.accounts, money.save_accounts,
                           self.refresh), "Accounts")
        tabs.addTab(Editor(money.COMMITMENT_COLUMNS, DUES, money.commitments,
                           money.save_commitments, self.refresh), "Every month")
        root.addWidget(tabs, 1)
        self.refresh()

    def refresh(self):
        p = money.position()
        use = money.utilisation()
        soon = money.due_soon(7)
        bits = [f"Have {rupees(p['have'])}", f"owe {rupees(p['owe'])}", f"net {rupees(p['net'])}",
                f"{rupees(money.monthly())} goes out every month"]
        if use is not None:
            bits.append(f"cards at {use}% of their limit")
        if soon:
            bits.append(f"{len(soon)} due within the week")
        self.summary.setText(" · ".join(bits))


if __name__ == "__main__":
    kit.application("Banking")
    sys.exit(kit.run(BankApp()))
