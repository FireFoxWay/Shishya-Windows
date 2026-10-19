"""
Training tasks for Shishya's code job, each with its answer worked out here.

Every task is: a folder of files (what the user's training folder would
hold), a request in the words a shopkeeper or a teacher would use, and a
check on what the script prints. The answer is computed from the data by
this file, never by a model, so a training example is kept only when it is
provably right.

    python make_tasks.py --n 180          writes work/tasks.jsonl and work/folders/
"""

import argparse
import json
import random
import shutil
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"

ITEMS = {
    "Pharma": ["Paracetamol 500", "Cetirizine 10", "Amoxicillin 250", "ORS Sachet", "Vitamin C",
               "Cough Syrup", "Antacid Gel", "Ibuprofen 400", "Azithromycin 500", "Zinc Tablets"],
    "Grocery": ["Basmati Rice", "Toor Dal", "Sunflower Oil", "Atta 5kg", "Sugar 1kg", "Tea 250g",
                "Salt 1kg", "Rice Crackers", "Green Tea Bags", "Instant Oatmeal"],
    "Stationery": ["Notebook A4", "Gel Pen", "Pencil Box", "Sticky Notes", "Stapler", "Geometry Set"],
    "Home & Kitchen": ["Water Bottle", "Coffee Mug Set", "Spice Rack", "Utensil Set", "Wine Glasses"],
    "Electronics": ["HDMI Cable", "Power Bank", "Bluetooth Adapter", "USB Charger", "Earphones"],
}
NAMES = ["Aarav Reddy", "Divya Sharma", "Kiran Rao", "Meera Iyer", "Rohan Gupta", "Sneha Patel",
         "Arjun Nair", "Priya Singh", "Vikram Das", "Ananya Bose", "Rahul Verma", "Kavya Menon",
         "Ishaan Kapoor", "Pooja Joshi", "Siddharth Jain", "Neha Kulkarni", "Aditya Mishra",
         "Lakshmi Pillai", "Farhan Khan", "Tanvi Desai"]
SUBJECTS = ["English", "Telugu", "Hindi", "Maths", "Science", "Social"]
DEPTS = ["Pharmacy", "Front desk", "Stores", "Delivery", "Accounts"]
MONTHS = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"]


def renderings(x):
    """The ways a correct script might print a number."""
    if isinstance(x, str):
        return [x]
    out = set()
    if float(x).is_integer():
        i = int(round(x))
        out |= {str(i), f"{i:,}", f"{i:.1f}", f"{i:.2f}", f"{i:,.2f}"}
    else:
        for d in (1, 2):
            out |= {f"{x:.{d}f}", f"{x:,.{d}f}"}
        out.add(str(round(x, 2)))
    return sorted(out)


# ─── files ──────────────────────────────────────────────────────────────────

def make_sales(rng, n):
    rows = []
    for _ in range(n):
        cat = rng.choice(list(ITEMS))
        item = rng.choice(ITEMS[cat])
        qty = rng.randint(1, 12)
        price = round(rng.uniform(8, 450), 2)
        day = rng.randint(1, 28)
        rows.append({"Date": f"2026-{rng.choice([7, 8, 9]):02d}-{day:02d}", "Item": item,
                     "Category": cat, "Qty": qty, "Price": price, "Amount": round(qty * price, 2)})
    return pd.DataFrame(rows)


def make_stock(rng, n):
    rows, seen = [], set()
    while len(rows) < n:
        cat = rng.choice(list(ITEMS))
        item = rng.choice(ITEMS[cat]) + ("" if rng.random() < .5 else f" {rng.choice(['S', 'M', 'L', 'XL', 'Pack'])}")
        if item in seen:
            continue
        seen.add(item)
        cost = round(rng.uniform(5, 300), 2)
        rows.append({"Code": f"P{1000 + len(rows)}", "Product": item, "Category": cat,
                     "Stock": rng.randint(0, 220), "Reorder": rng.randint(10, 80),
                     "Cost": cost, "Price": round(cost * rng.uniform(1.1, 1.8), 2)})
    return pd.DataFrame(rows)


def make_marks(rng, n):
    subs = rng.sample(SUBJECTS, rng.randint(3, 5))
    rows = []
    for i, name in enumerate(rng.sample(NAMES, n)):
        r = {"Roll": f"{rng.choice(['9A', '9B', '10A', '8C'])}{i + 1:02d}", "Name": name,
             "Attendance %": rng.randint(55, 99)}
        for s in subs:
            r[s] = rng.randint(28, 99)
        rows.append(r)
    return pd.DataFrame(rows), subs


def make_expenses(rng):
    rows = [{"Month": m, "Department": d, "Amount": round(rng.uniform(800, 25000), 2)}
            for m in rng.sample(MONTHS, rng.randint(3, 6)) for d in DEPTS]
    return pd.DataFrame(rows)


def write(df, folder, name, rng, sheet=None, title=False):
    path = folder / name
    if name.endswith(".csv"):
        df.to_csv(path, index=False)
    else:
        with pd.ExcelWriter(path, engine="openpyxl") as xw:
            # Real sheets often open with a title and a note above the
            # columns; the model has to find the header, not assume row 1.
            start = rng.randint(2, 4) if title else 0
            df.to_excel(xw, sheet_name=sheet or "Sheet1", index=False, startrow=start)
            if title:
                ws = xw.sheets[sheet or "Sheet1"]
                ws.cell(row=1, column=1, value=f"{name.split('.')[0].replace('_', ' ').upper()} — prepared by the office")
    return path


# ─── tasks ──────────────────────────────────────────────────────────────────

def pick(rng, *phrasings):
    return rng.choice(phrasings)


def sales_tasks(rng, df, f):
    by_cat = df.groupby("Category")["Amount"].sum()
    by_item_qty = df.groupby("Item")["Qty"].sum()
    top = by_cat.idxmax()
    cat = rng.choice(sorted(df["Category"].unique()))
    month = rng.choice(sorted(df["Date"].str[:7].unique()))
    return [
        (pick(rng, f"total sales amount in {f}", f"how much did we sell in total according to {f}",
              f"add up the Amount column of {f}"), renderings(round(df["Amount"].sum(), 2))),
        (pick(rng, f"which category earned the most in {f}", f"top selling category by amount in {f}"),
         [top]),
        (pick(rng, f"how many {cat} sales are there in {f}", f"count the rows for category {cat} in {f}"),
         renderings(int((df["Category"] == cat).sum()))),
        (pick(rng, f"total quantity sold of each item in {f}, highest first",
              f"units sold per item in {f}"), [by_item_qty.idxmax()] + renderings(int(by_item_qty.max()))[:1]),
        (pick(rng, f"sales total for {month} from {f}", f"how much was sold in {month} in {f}"),
         renderings(round(df[df["Date"].str.startswith(month)]["Amount"].sum(), 2))),
        (pick(rng, f"average bill amount in {f}", f"mean of the Amount column in {f}"),
         renderings(round(df["Amount"].mean(), 2))),
        (pick(rng, f"how many different items were sold in {f}", f"count distinct items in {f}"),
         renderings(int(df["Item"].nunique()))),
    ]


def stock_tasks(rng, df, f):
    low = df[df["Stock"] <= df["Reorder"]]
    value = round((df["Stock"] * df["Cost"]).sum(), 2)
    cat = rng.choice(sorted(df["Category"].unique()))
    margin = ((df["Price"] - df["Cost"]) / df["Price"]).idxmax()
    return [
        (pick(rng, f"how many products are at or below their reorder level in {f}",
              f"count items that need reordering in {f}"), renderings(len(low))),
        (pick(rng, f"total value of stock at cost in {f}", f"stock value (stock times cost) in {f}"),
         renderings(value)),
        (pick(rng, f"how many products are out of stock in {f}", f"count products with zero stock in {f}"),
         renderings(int((df["Stock"] == 0).sum()))),
        (pick(rng, f"how many {cat} products are listed in {f}", f"count the {cat} items in {f}"),
         renderings(int((df["Category"] == cat).sum()))),
        (pick(rng, f"which product has the highest margin in {f}", f"product with the best profit margin in {f}"),
         [df.loc[margin, "Product"]]),
        (pick(rng, f"how many products are there in {f}", f"count the products in {f}"), renderings(len(df))),
    ]


def marks_tasks(rng, df, subs, f):
    s = rng.choice(subs)
    cut = rng.choice([40, 50, 60, 75, 80])
    df = df.copy()
    df["Total"] = df[subs].sum(axis=1)
    return [
        (pick(rng, f"how many students are in {f}", f"count the students in {f}"), renderings(len(df))),
        (pick(rng, f"average {s} mark in {f}", f"class average for {s} in {f}"),
         renderings(round(df[s].mean(), 2))),
        (pick(rng, f"who has the highest total marks in {f}", f"top student by total in {f}"),
         [df.loc[df["Total"].idxmax(), "Name"]]),
        (pick(rng, f"how many students scored below {cut} in {s} in {f}",
              f"count students under {cut} in {s} in {f}"), renderings(int((df[s] < cut).sum()))),
        (pick(rng, f"how many students have attendance under 75% in {f}",
              f"count students below 75 percent attendance in {f}"),
         renderings(int((df["Attendance %"] < 75).sum()))),
        (pick(rng, f"name the student with the lowest {s} mark in {f}"), [df.loc[df[s].idxmin(), "Name"]]),
    ]


def expense_tasks(rng, df, f):
    d = rng.choice(DEPTS)
    by_dept = df.groupby("Department")["Amount"].sum()
    return [
        (pick(rng, f"total expenses in {f}", f"add up all the expenses in {f}"),
         renderings(round(df["Amount"].sum(), 2))),
        (pick(rng, f"which department spent the most in {f}"), [by_dept.idxmax()]),
        (pick(rng, f"how much did {d} spend in {f}", f"total spending of {d} in {f}"),
         renderings(round(by_dept[d], 2))),
    ]


def plain_tasks(rng):
    n = rng.randint(3, 19)
    a, b = rng.randint(100, 9999), rng.randint(2, 99)
    return [
        ("print hello world", ["hello world"]),
        (f"print the multiplication table of {n} up to 10", renderings(n * 10)),
        (f"what is {a} times {b}", renderings(a * b)),
        (f"what is 18% GST on Rs {a}", renderings(round(a * 0.18, 2))),
        (f"price including 12% GST for an item costing {a}", renderings(round(a * 1.12, 2))),
        ("print today's date", []),
    ]


def build(n_folders, seed=7):
    rng = random.Random(seed)
    if WORK.exists():
        shutil.rmtree(WORK / "folders", ignore_errors=True)
    tasks = []
    for k in range(n_folders):
        fid = f"f{k:04d}"
        folder = WORK / "folders" / fid / "shared" / "training"
        folder.mkdir(parents=True, exist_ok=True)
        (folder.parent / "work").mkdir(exist_ok=True)
        kinds = rng.sample(["sales", "stock", "marks", "expenses"], rng.randint(1, 3))
        found = []
        for kind in kinds:
            title = rng.random() < .35
            if kind == "sales":
                name = rng.choice(["sales.csv", "sales_aug.xlsx", "daily_sales.csv", "bills.xlsx"])
                df = make_sales(rng, rng.randint(25, 220))
                write(df, folder, name, rng, sheet="Sales", title=title and name.endswith("xlsx"))
                found += sales_tasks(rng, df, name)
            elif kind == "stock":
                name = rng.choice(["stock.xlsx", "inventory.csv", "catalogue.csv", "store_stock.xlsx"])
                df = make_stock(rng, rng.randint(15, 120))
                write(df, folder, name, rng, sheet="Stock", title=title and name.endswith("xlsx"))
                found += stock_tasks(rng, df, name)
            elif kind == "marks":
                name = rng.choice(["marks.csv", "class_results.xlsx", "term1.csv", "exam_marks.xlsx"])
                df, subs = make_marks(rng, rng.randint(6, 20))
                write(df, folder, name, rng, sheet="Marks", title=title and name.endswith("xlsx"))
                found += marks_tasks(rng, df, subs, name)
            else:
                name = rng.choice(["expenses.xlsx", "spending.csv", "monthly_costs.xlsx"])
                df = make_expenses(rng)
                write(df, folder, name, rng, sheet="Expenses", title=title and name.endswith("xlsx"))
                found += expense_tasks(rng, df, name)
        if rng.random() < .25:
            found += plain_tasks(rng)
        for brief, expect in rng.sample(found, min(len(found), rng.randint(3, 6))):
            tasks.append({"id": f"{fid}-{len(tasks)}", "folder": fid, "brief": brief, "expect": expect})
    (WORK / "tasks.jsonl").write_text("\n".join(json.dumps(t) for t in tasks), encoding="utf-8")
    return tasks


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=160, help="folders; each yields 3 to 6 tasks")
    args = ap.parse_args()
    t = build(args.n)
    print(f"{len(t)} tasks across {args.n} folders in {WORK}")
