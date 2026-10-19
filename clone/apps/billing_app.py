#!/usr/bin/env python3
"""
Billing — the counter. Ring up a sale, hand over a bill, and the books update.
Runs INSIDE the sandbox.

Two tabs, because two different jobs: the Counter is what somebody uses two
hundred times a day and must stay uncluttered, and Bills is where you go when
something went wrong — a return, a void, a reprint. A Void button on the
counter is how yesterday's takings get cancelled by a slip.

The books are vm/shell/books.py — GST-inclusive prices, append-only sales,
corrections written as new rows — shared with the Mac. Nothing here parses
a CSV.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import kit   # noqa: E402
from PySide6.QtCore import Qt   # noqa: E402
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,   # noqa: E402
                               QLabel, QListWidget, QListWidgetItem, QPushButton,
                               QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout,
                               QWidget)

import approvals   # noqa: E402
import books       # noqa: E402
import common      # noqa: E402
import invoice     # noqa: E402

SEED = common.TRAINING / "01_20Retail_20Inventory.xlsx"


def seed_catalogue():
    """First run: stock the counter from whatever inventory exists. A billing
    app with an empty product list demonstrates a form, not a shop."""
    common.BILLING.mkdir(parents=True, exist_ok=True)
    if books.CATALOGUE.exists():
        return
    rows = []
    if SEED.exists():
        try:
            import pandas as pd
            for _, r in pd.read_excel(SEED).iterrows():
                rows.append({
                    "id": str(r.get("Product ID", "")).strip(),
                    "name": str(r.get("Product Name", "")).strip(),
                    "category": str(r.get("Category", "")).strip(),
                    "cost": f"{float(r.get('Unit Cost', 0) or 0):.2f}",
                    "price": f"{float(r.get('Retail Price', 0) or 0):.2f}",
                    "stock": str(int(float(r.get("Closing Stock", 0) or 0))),
                    "reorder": str(int(float(r.get("Reorder Point", 0) or 0))),
                    "gst": books.DEFAULT_GST,
                })
        except Exception:
            rows = []
    books.write_catalogue([r for r in rows if r["id"] and r["name"]])


class BillingApp(kit.Window):
    def __init__(self):
        super().__init__("Billing", 980, 680)
        seed_catalogue()
        self.reload_catalogue()
        self.bill = {}
        self.last_bill = None

        root = QVBoxLayout(self.body)
        root.setContentsMargins(10, 10, 10, 10)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.counter_page(), "Counter")
        self.tabs.addTab(self.bills_page(), "Bills")
        self.tabs.currentChanged.connect(lambda i: self.show_bills() if i == 1 else None)
        root.addWidget(self.tabs, 1)
        self.status = kit.label("", wrap=True, name="status")
        root.addWidget(self.status)

        self.show_results()
        self.paint_bill()
        self.greet()

    def reload_catalogue(self):
        self.catalogue = books.read_catalogue()
        self.by_id = {r["id"]: r for r in self.catalogue}

    def greet(self):
        if books.read_sales():
            self.status.setText(f"{len(self.catalogue)} products stocked · you are the {common.role()}")
            return
        self.status.setText(
            "Nothing has been billed yet. Type a product name above, click it to add it to "
            "the bill, then Save the bill. Prices include GST, the stock count goes down as "
            "you sell, and every bill can be printed or corrected from the Bills tab.")

    # ── counter ──
    def counter_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        bar = QHBoxLayout()
        self.search = kit.entry("Type a product name or code", name="productSearch",
                                accessible="Product search")
        self.search.textChanged.connect(lambda *_: self.show_results())
        self.search.returnPressed.connect(self.on_first_result)
        bar.addWidget(self.search, 1)
        self.customer = kit.entry("Customer (optional)", name="customer", accessible="Customer")
        self.customer.setFixedWidth(220)
        bar.addWidget(self.customer)
        col.addLayout(bar)

        split = QSplitter()
        self.results = QListWidget()
        self.results.setObjectName("searchResults")
        self.results.setAccessibleName("Search results")
        self.results.itemClicked.connect(lambda it: self.add_to_bill(it.data(Qt.UserRole)))
        split.addWidget(self.results)

        right = QWidget()
        rcol = QVBoxLayout(right)
        rcol.setContentsMargins(0, 0, 0, 0)
        self.lines_box = QWidget()
        self.lines = QVBoxLayout(self.lines_box)
        self.lines.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.lines_box)
        scroll.setAccessibleName("Bill")
        rcol.addWidget(scroll, 1)
        self.totals = QLabel()
        self.totals.setObjectName("total")
        self.totals.setAlignment(Qt.AlignRight)
        rcol.addWidget(self.totals)
        split.addWidget(right)
        split.setSizes([440, 500])
        col.addWidget(split, 1)

        feet = QHBoxLayout()
        feet.addStretch(1)
        for text, fn in (("Clear the bill", self.on_clear), ("Print the last bill", self.on_print)):
            feet.addWidget(kit.button(text, fn))
        feet.addWidget(kit.button("Save the bill", self.on_save, primary=True))
        col.addLayout(feet)
        return page

    def matches(self):
        want = self.search.text().strip().lower()
        if not want:
            return [r for r in self.catalogue
                    if books.number(r["stock"]) <= books.number(r["reorder"])][:40]
        return [r for r in self.catalogue
                if want in r["name"].lower() or want in r["id"].lower()][:60]

    def show_results(self):
        self.results.clear()
        self.found = self.matches()
        for r in self.found:
            stock = books.number(r["stock"])
            note = "OUT OF STOCK" if stock <= 0 else f"{stock:.0f} left"
            item = QListWidgetItem(f"{r['name']}   ₹{books.money(r['price'])}  ·  {note}  ·  "
                                   f"GST {r['gst']}%")
            item.setData(Qt.UserRole, r["id"])
            item.setData(Qt.AccessibleTextRole, f"{r['name']} {r['id']}")
            self.results.addItem(item)

    def on_first_result(self):
        if self.found:
            self.add_to_bill(self.found[0]["id"])

    def add_to_bill(self, pid):
        item = self.by_id.get(pid)
        if not item:
            return
        stock = books.number(item["stock"])
        if self.bill.get(pid, 0) + 1 > stock:
            self.status.setText(f"Only {stock:.0f} of {item['name']} left.")
            return
        self.bill[pid] = self.bill.get(pid, 0) + 1
        self.paint_bill()

    def remove_from_bill(self, pid):
        if pid in self.bill:
            self.bill[pid] -= 1
            if self.bill[pid] <= 0:
                del self.bill[pid]
        self.paint_bill()

    def paint_bill(self):
        while self.lines.count() > 1:
            w = self.lines.takeAt(0).widget()
            if w:
                w.deleteLater()
        total = tax = 0.0
        for pid, qty in self.bill.items():
            item = self.by_id[pid]
            amount = books.number(item["price"]) * qty
            total += amount
            tax += books.tax_within(item["price"], item["gst"]) * qty
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(4, 2, 4, 2)
            line.addWidget(kit.label(f"{qty} × {item['name']}", wrap=True), 1)
            line.addWidget(kit.label(f"₹{books.money(amount)}"))
            less = QPushButton("−")
            less.setAccessibleName(f"Remove one {item['name']}")
            less.clicked.connect(lambda _=False, p=pid: self.remove_from_bill(p))
            line.addWidget(less)
            self.lines.insertWidget(self.lines.count() - 1, row)
        self.totals.setText(f"<small>of which GST ₹{books.money(tax)}</small><br>"
                            f"<b style='font-size:16px'>Total  ₹{books.money(total)}</b>")
        self.totals.setAccessibleName(f"Total {books.money(total)}")

    def on_clear(self):
        self.bill = {}
        self.paint_bill()
        self.status.setText("Bill cleared.")

    def on_save(self):
        if not self.bill:
            self.status.setText("Nothing on the bill yet.")
            return
        number = books.new_bill_number()
        who = self.customer.text().strip()
        if who:
            books.remember_customer(who)
        rows = [books.line(number, "sale", self.by_id[pid], qty, who)
                for pid, qty in self.bill.items()]
        books.record(rows)
        for pid, qty in self.bill.items():
            item = self.by_id[pid]
            item["stock"] = str(int(books.number(item["stock"]) - qty))
        books.write_catalogue(self.catalogue)
        total = sum(books.number(r["amount"]) for r in rows)
        path = invoice.write(number, rows, who)
        self.last_bill = number
        self.bill = {}
        self.customer.clear()
        self.paint_bill()
        self.show_results()
        self.status.setText(f"Saved {number} — ₹{books.money(total)}. Bill written to "
                            f"{path.parent.name}/{path.name}.")

    def on_print(self):
        number = self.last_bill or (books.bills(1)[0]["bill"] if books.bills(1) else None)
        if not number:
            self.status.setText("Nothing has been billed yet.")
            return
        path = invoice.write(number, books.bill_rows(number))
        if not path:
            self.status.setText(f"Nothing to print for {number}.")
            return
        kit.open_app("files_app.py", path.parent)
        self.status.setText(f"{number} is ready to print — {path.name} in Work/Bills.")

    # ── bills ──
    def bills_page(self):
        page = QWidget()
        col = QVBoxLayout(page)
        self.bill_box = QWidget()
        self.bill_list = QVBoxLayout(self.bill_box)
        self.bill_list.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.bill_box)
        scroll.setAccessibleName("Recent bills")
        col.addWidget(scroll)
        return page

    def show_bills(self):
        # Anything the head approved since the last look, performed now.
        for request in self.approved_voids():
            count, message = books.void(request["target"])
            self._mark_done(request["id"])
            self.reload_catalogue()
            self.status.setText(f"Head approved: {message}")

        while self.bill_list.count() > 1:
            w = self.bill_list.takeAt(0).widget()
            if w:
                w.deleteLater()
        recent = books.bills(30)
        if not recent:
            self.bill_list.insertWidget(0, kit.label("No bills yet. Ring one up on the Counter."))
            return
        head = common.may("void")
        for entry in recent:
            row = QWidget()
            line = QHBoxLayout(row)
            line.setContentsMargins(2, 2, 2, 2)
            mark = "  ·  VOIDED" if entry["void"] else ""
            line.addWidget(kit.label(
                f"{entry['bill']}  ·  {entry['at'][:16]}  ·  ₹{books.money(entry['total'])}"
                f"{'  ·  ' + entry['customer'] if entry['customer'] else ''}{mark}", wrap=True), 1)
            back = kit.button("Return an item", lambda n=entry["bill"]: self.returns_for(n))
            back.setAccessibleName(f"Return from {entry['bill']}")
            back.setEnabled(not entry["void"])
            line.addWidget(back)
            pr = kit.button("Print", lambda n=entry["bill"]: self.print_one(n))
            pr.setAccessibleName(f"Print {entry['bill']}")
            line.addWidget(pr)
            # Voiding is the head's. A clerk is not simply refused — being
            # blocked with no way to ask is how people work around software.
            kill = kit.button("Void" if head else "Ask to void",
                              (lambda n=entry["bill"]: self.void_one(n)) if head else
                              (lambda n=entry["bill"], e=entry: self.ask_to_void(n, e)))
            kill.setAccessibleName(f"{'Void' if head else 'Ask to void'} {entry['bill']}")
            kill.setEnabled(not entry["void"])
            if not head:
                kill.setToolTip("Sends a request to the head")
            line.addWidget(kill)
            self.bill_list.insertWidget(self.bill_list.count() - 1, row)

    def _mark_done(self, request_id):
        rows = approvals._read()
        for r in rows:
            if r.get("id") == request_id:
                r["note"] = "done"
        approvals._write(rows)

    def print_one(self, number):
        path = invoice.write(number, books.bill_rows(number))
        self.status.setText(f"{path.name} written to Work/Bills." if path
                            else f"Nothing to print for {number}.")

    def ask_to_void(self, number, entry):
        waiting = [r for r in approvals.pending()
                   if r.get("what") == "void" and r.get("target") == number]
        if waiting:
            self.status.setText(f"Already asked — {number} is waiting for the head to decide.")
            return
        approvals.ask("void", f"Void {number}, ₹{books.money(entry['total'])}"
                              + (f" for {entry['customer']}" if entry["customer"] else ""),
                      target=number)
        self.status.setText(f"Asked the head to void {number}. The bill still stands until "
                            f"they decide.")
        self.show_bills()

    def approved_voids(self):
        return [r for r in approvals.recent(50)
                if r.get("what") == "void" and r.get("state") == "approved"
                and r.get("note") != "done"]

    def void_one(self, number):
        if not common.may("void"):
            self.status.setText("Only the head can void a bill.")
            return
        count, message = books.void(number)
        self.reload_catalogue()
        self.status.setText(message)
        self.show_bills()
        self.show_results()
        if count:
            invoice.write(number, books.bill_rows(number))

    def returns_for(self, number):
        """One dialog, one item, one quantity. Returns are rare and fiddly; a
        wrong one is a cash refund that never happened."""
        rows = [r for r in books.bill_rows(number) if r.get("kind") == "sale"]
        if not rows:
            self.status.setText(f"Nothing on {number} to return.")
            return
        d = QDialog(self)
        d.setWindowTitle(f"Return from {number}")
        col = QVBoxLayout(d)
        pick = QComboBox()
        pick.setAccessibleName("Item to return")
        for r in rows:
            pick.addItem(f"{r['name']} ({books.number(r['qty']):.0f} sold)", r["id"])
        col.addWidget(pick)
        qty = QSpinBox()
        qty.setRange(1, 999)
        qty.setAccessibleName("How many")
        col.addWidget(qty)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Take it back")
        buttons.accepted.connect(d.accept)
        buttons.rejected.connect(d.reject)
        col.addWidget(buttons)
        if d.exec():
            count, message = books.take_back(number, pick.currentData(), qty.value())
            self.reload_catalogue()
            self.status.setText(message)
            self.show_bills()
            self.show_results()


if __name__ == "__main__":
    kit.application("Billing")
    sys.exit(kit.run(BillingApp()))
