#!/usr/bin/env python3
"""
Shishya — the checks Findings runs over the material, without a window.

Split out of findings_app.py so the GTK window and the Windows build's Qt
window run the same six checks and read their verdicts the same way.

── Why each check is a generated program ───────────────────────────────────

The model is unreliable at arithmetic across rows and exact at writing code
that does the arithmetic. So a check is a short, bounded brief turned into a
program, run, and reported with the program attached. Every finding is
therefore checkable by the person being told about it.
"""

import subprocess
import tempfile
from pathlib import Path

import common


RUN_TIMEOUT = 90


# Each check is a title, a brief, and why a human should care. The briefs are
# written to be answerable by a program rather than by judgement.
PROTOCOL = (
    "\n\nFirst line of output must be exactly 'FINDINGS: n' where n is how "
    "many problems were found — 0 if none. Then the details, one per line, "
    "each readable by someone who has never seen the file: name the column "
    "and the values in plain text, not as Python tuples or dict reprs.\n\n"
    "Never print more than 10 detail lines. A finding is only useful if it is "
    "short and someone can act on it — a check that reported 8,254 outliers "
    "told the reader nothing at all. If more than 10 things qualify, report "
    "the 10 that matter most and say how many there were in total."
)


CHECKS = [
    ("The same name written two ways",
     "IMPORTANT: where columns repeat as a family — names differing only by a "
     "trailing number, such as 'Purchased From 1' through 'Purchased From 10' "
     "— stack them into ONE series and treat it as a single column. The same "
     "supplier is written one way in one column and another way in the next, "
     "so grouping each column separately finds nothing. "
     "Then, for each text column or stacked family, group values by their "
     "lowercased, whitespace-"
     "stripped form and report only groups where two or more different "
     "spellings occur AND each spelling appears in at least 5 rows. Rank by "
     "the total rows affected, largest first, and report at most 8. Print the "
     "column, the spellings, and the row count of each. Ignore columns where "
     "values are shorter than 4 characters — those are codes and sizes, not "
     "names." + PROTOCOL,
     "The same supplier or manufacturer counted twice splits every total that "
     "involves it."),

    ("Columns nobody fills in",
     "For every column, count rows that are empty, None, zero, 'N/A' or blank. "
     "Report columns above 80%, ranked worst first, at most 10, with the "
     "percentage." + PROTOCOL,
     "A column nobody fills is a broken process or a field that should go."),

    ("Figures that look like typing mistakes",
     "For each numeric column, take only the non-zero values. Skip the column "
     "entirely if it has fewer than 30 non-zero values or if its "
     "interquartile range is zero. Report values more than 20 times the "
     "median, at most 3 per column and at most 10 overall, ranked by how far "
     "out they are, each with a label from the first text column." + PROTOCOL,
     "One misplaced decimal in a price distorts every figure computed from it."),

    ("Identifiers that are not unique",
     "Consider only columns where more than 80 percent of values are distinct "
     "— a genuine identifier, not a size or a category. In those, report "
     "values appearing in more than one row, at most 10, ranked by count." + PROTOCOL,
     "A repeated identifier means two records that should be one."),

    ("Stock that sold and then stopped",
     "If column headers include dates, treat them as a time series per row. "
     "Find rows with total activity above 10 in the earlier half and exactly "
     "zero in the most recent quarter. Rank by how much they used to sell, "
     "largest first, and report at most 10 with a label and the earlier "
     "total. If there are no date columns, say so." + PROTOCOL,
     "Something that sold well and then stopped is either a supply problem or "
     "money asleep on a shelf."),

    ("Value sitting in things that never move",
     "If there is a quantity-on-hand column and a price or cost column, "
     "consider only rows whose dated activity columns are all zero. Print the "
     "total quantity times price for those rows, then the ten largest "
     "individually with a label. If the columns do not exist, say so." + PROTOCOL,
     "The one number that says how much working capital is asleep."),
]


def check_duplicate_names():
    """Values that are the same name written two ways.

    Repeated column families are stacked before grouping. The same supplier
    appears as "KK ENTERPRISES" in one column and "Kk Enterprises" in the
    next, so grouping each column on its own finds nothing at all — which is
    exactly what happened.
    """
    import re
    from collections import Counter, defaultdict
    from openpyxl import load_workbook

    lines = []
    total = 0
    for path in sorted(common.TRAINING.iterdir()):
        if path.suffix.lower() not in (".xlsx", ".xlsm"):
            continue
        try:
            wb = load_workbook(path, read_only=True, data_only=True)
        except Exception:
            continue
        for ws in wb.worksheets:
            rows = ws.iter_rows(values_only=True)
            try:
                header = [str(c) if c is not None else "" for c in next(rows)]
            except StopIteration:
                continue

            # Columns sharing a stem, minus a trailing number, are one series.
            family = defaultdict(list)
            for i, name in enumerate(header):
                family[re.sub(r"\s*\d+$", "", name).strip() or f"col{i}"].append(i)

            counts = defaultdict(Counter)
            for row in rows:
                for stem, idxs in family.items():
                    for i in idxs:
                        if i >= len(row):
                            continue
                        value = row[i]
                        if not isinstance(value, str):
                            continue
                        value = value.strip()
                        # Short values are sizes and codes, not names.
                        if len(value) < 4 or value.upper() == "N/A":
                            continue
                        counts[stem][value] += 1
            wb_name = path.name
            for stem, tally in counts.items():
                grouped = defaultdict(list)
                for value, n in tally.items():
                    grouped[value.lower()].append((value, n))
                for variants in grouped.values():
                    if len(variants) < 2:
                        continue
                    if not all(n >= 5 for _, n in variants):
                        continue
                    total += 1
                    variants.sort(key=lambda v: -v[1])
                    shown = "  vs  ".join(f"{v} ({n} rows)" for v, n in variants)
                    lines.append((sum(n for _, n in variants),
                                  f"{stem} — {shown}"))
        wb.close()

    lines.sort(reverse=True)
    out = [f"FINDINGS: {total}"]
    out += [text for _, text in lines[:10]]
    if total > 10:
        out.append(f"...and {total - 10} more")
    return "\n".join(out)


BUILTIN = {"The same name written two ways": check_duplicate_names}


def run(code):
    with tempfile.TemporaryDirectory() as tmp:
        script = Path(tmp) / "check.py"
        script.write_text(code, encoding="utf-8")
        try:
            p = common.run_python(script, cwd=Path.home(), timeout=RUN_TIMEOUT)
            return (p.stdout or "").strip(), (p.stderr or "").strip()
        except subprocess.TimeoutExpired:
            return "", f"still running after {RUN_TIMEOUT}s"


def read_verdict(out):
    """How many problems a check found, read from its own first line.

    Inferring this from prose failed immediately: a check that printed "none
    found" once per column produced a wall of nothing that was reported as a
    finding. The script is now asked to say the number itself.
    """
    text = (out or "").strip()
    if not text:
        return "failed"
    first = text.splitlines()[0].strip().lower()
    if first.startswith("findings:"):
        try:
            return "found" if int(first.split(":", 1)[1].strip().split()[0]) > 0 else "nothing"
        except (ValueError, IndexError):
            pass
    # Older wording, and a fallback for a script that ignored the instruction.
    if first in ("none found", "not applicable", "none"):
        return "nothing"
    return "found"


def esc(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
