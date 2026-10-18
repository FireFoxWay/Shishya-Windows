#!/usr/bin/env python3
"""
Shishya — reading a folder of documents and answering only from it.

Split out of training_app.py so the same retrieval serves the Training Data
window, the chat, and the Windows build's Qt apps without any of them
importing a toolkit the others do not have. Nothing in here draws anything.

── Why retrieval is keyword-based rather than embeddings ───────────────────

An embedding model would retrieve better. It would also be a second model to
pull, hold in memory beside the 8B and the VM, and explain. Scored term
overlap with rarity weighting is a few dozen lines, needs nothing extra, and
on a folder of tens of documents — which is what this is for — it is good
enough that the model's reading is the bottleneck, not the retrieval.

The rule that matters more than either: the answer must come from the
documents. Asked something the documents do not cover, it says so.
"""

import math
import re
from collections import Counter
from pathlib import Path

import common


STOP = set("""a an the and or but if then than that this these those of in on at to for
from by with without into over under is are was were be been being it its as no not
do does did can could should would will shall may might must have has had i you he she
they we what which who whom when where how why""".split())


def terms(text):
    """Words worth matching on, with plurals folded to the singular.

    Without this, "which supplier gives us the HDMI cables" missed every HDMI
    Cable row: the sheet says "Cable" and the question said "cables", so only
    one term landed and the row filter discarded them all. Crude — it would
    fold "bus" to "bu" if not for the length guard — but the alternative is a
    stemmer, and the failure it prevents is worse than the ones it causes.
    """
    out = []
    for w in re.findall(r"[a-z0-9]+", text.lower()):
        if w in STOP or len(w) < 2:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return out


LATIN = re.compile(r"[A-Za-z]")


def for_retrieval(question):
    """The question in English when it was not asked in English.

    The index is terms, weighted by rarity. A Telugu question shares no
    tokens at all with an English attendance policy, so it does not merely
    fail to find it — it finds whatever else happens to contain the one
    thing both scripts agree on. Asked in Telugu whether a student with 68%
    attendance may sit the exam, retrieval returned four passages of a
    pharmacy inventory, because "68" appears in it. That is the §08 failure
    again, and answering confidently from the wrong document is worse than
    finding nothing.

    So the question is translated for the search only. The reply is still
    written from the original, in the language it was asked in — the
    translation never reaches the person and is never shown as their words.
    """
    letters = len(LATIN.findall(question))
    body = len(question.replace(" ", ""))
    if body == 0 or letters >= max(3, body * 0.4):
        return question, None          # already English enough to search with
    try:
        english = common.ask_job(
            "answers",
            "Translate this question into English. Reply with the translation "
            f"and nothing else.\n\n{question}",
            budget=600, timeout=180).strip()
    except Exception:
        return question, None          # a failed translation must not lose the question
    # The longest line, not the first: the reply is sometimes preceded by a
    # short preamble, and taking line one turned a Telugu question into
    # "A student has" — which still found the right policy, by luck, on the
    # strength of one word. Luck is not a retrieval strategy.
    lines = [l.strip(' "\'') for l in english.splitlines() if l.strip()]
    english = max(lines, key=len) if lines else ""
    return (english or question), (english or None)


class Library:
    """Chunks plus an inverted index, and — for spreadsheets — a row index.

    The row index exists because prose chunking is wrong for tables. A 1000
    row sheet cut into overlapping 1400-character windows gives the model
    fragments of many unrelated rows at once, and it blends them: asked for
    the HDMI Cable it confidently returned a product id belonging to Golf
    Tees, with a supplier and reorder point that were never in the same row
    as each other.

    So table rows are kept whole and searched as rows. A question that names
    something in the table gets the actual matching lines, with their header,
    and nothing else — there is nothing adjacent for the model to blend in.
    """

    def __init__(self):
        self.chunks = []          # (source, text)
        self.freqs = []           # Counter per chunk
        self.doc_count = Counter()
        self.tables = []          # (source, sheet, header, [row strings])

    def add(self, path):
        text, how = common.extract(path)

        # A sheet arrives as "## Sheet: name" followed by pipe-separated rows.
        if "## Sheet:" in text:
            self._add_table(Path(path).name, text)

        pieces = common.chunk(text)
        for piece in pieces:
            counts = Counter(terms(piece))
            self.chunks.append((Path(path).name, piece))
            self.freqs.append(counts)
            for term in counts:
                self.doc_count[term] += 1
        return len(pieces), how

    def _add_table(self, source, text):
        for block in text.split("## Sheet:"):
            block = block.strip()
            if not block:
                continue
            lines = [l for l in block.splitlines() if l.strip()]
            if len(lines) < 2:
                continue
            sheet, header, rows = lines[0].strip(), lines[1], lines[2:]
            self.tables.append((source, sheet, header, rows))

    # ── searching ───────────────────────────────────────────────────────────

    def search(self, query, k=4):
        rows = self.search_rows(query)
        chunks = self.search_chunks(query, k)
        # Matching rows first: they are exact, and the model reads what comes
        # first most carefully. Prose chunks still follow, because the answer
        # often needs a policy as well as a row.
        return rows + chunks[: max(1, k - len(rows))]

    def search_rows(self, query, limit=30):
        """Rows containing the query's distinctive words, kept verbatim.

        Matching keys on rarity, not on every word. A question says "the
        reorder point and supplier for PRD-1031" — but "reorder" and
        "supplier" are column headings that appear in no row at all, while
        "1031" appears in exactly one. Requiring every word matched nothing;
        requiring any word would return most of the sheet. So a row must
        contain at least one term that is rare within this table, and rows
        are then ranked by how much of the query they cover.
        """
        wanted = set(terms(query))
        if not wanted or not self.tables:
            return []

        out = []
        for source, sheet, header, rows in self.tables:
            counts = self._term_counts(source, sheet, rows)
            total = max(1, len(rows))
            # Rare inside this table: fewer than one row in twenty.
            rare = {t for t in wanted if 0 < counts.get(t, 0) <= max(1, total // 20)}
            if not rare:
                continue

            scored = []
            for row in rows:
                cells = set(terms(row))
                hit_rare = rare & cells
                if not hit_rare:
                    continue
                # Two words must land, not one. Asked whether a student with
                # 68% attendance may sit an exam, a single coincidental "68"
                # in an inventory sheet was enough to drag thirty product rows
                # into a question about school policy. An identifier like
                # PRD-1031 still qualifies — it is two terms, "prd" and "1031".
                if len(wanted & cells) < 2:
                    continue
                scored.append((len(wanted & cells), len(hit_rare), row))
            if not scored:
                continue

            scored.sort(key=lambda r: (-r[1], -r[0]))
            hits = [row for _, _, row in scored[:limit]]
            note = ("" if len(scored) <= limit
                    else f"\n({len(scored)} rows match; the {limit} closest are shown)")
            out.append((f"{source} — {sheet}",
                        f"{header}\n" + "\n".join(hits) + note))
        return out

    def _term_counts(self, source, sheet, rows):
        """How many rows each term appears in, computed once per table."""
        key = (source, sheet)
        cached = getattr(self, "_counts_cache", None)
        if cached is None:
            cached = self._counts_cache = {}
        if key not in cached:
            c = Counter()
            for row in rows:
                for t in set(terms(row)):
                    c[t] += 1
            cached[key] = c
        return cached[key]

    def search_chunks(self, query, k=4):
        wanted = Counter(terms(query))
        if not wanted or not self.chunks:
            return []
        n = len(self.chunks)
        scored = []
        for i, counts in enumerate(self.freqs):
            score = 0.0
            for term, want in wanted.items():
                if term in counts:
                    # Rare terms carry the query. A shared "district" says far
                    # less about relevance than a shared "APP-2291".
                    idf = math.log(1 + n / (1 + self.doc_count[term]))
                    score += want * math.log(1 + counts[term]) * idf
            if score > 0:
                scored.append((score, i))
        scored.sort(reverse=True)
        if not scored:
            return []

        # Drop the weak tail. Asked which supplier provides HDMI cables, the
        # search was returning two blocks of an unrelated macOS-versus-Windows
        # PDF simply because they were the next best of a bad lot — nearly
        # 3,000 characters the model then has to read and reason past. A
        # passage worth a fifth of the best one is noise, and noise is what
        # what makes it think until it runs out of room.
        best = scored[0][0]
        keep = [(score, i) for score, i in scored[:k] if score >= best * 0.4]
        return [self.chunks[i] for _, i in keep]


MAKE_VERBS = ("create", "make", "build", "generate", "draft", "produce",
              "prepare", "write me", "give me", "put together", "compile")


MAKE_KINDS = {
    "Spreadsheet": ("excel", "xlsx", "spreadsheet", "sheet", "table", "grid",
                    "comparison table", "csv"),
    "Presentation": ("powerpoint", "ppt", "pptx", "presentation", "deck",
                     "slides", "slide"),
    "Document": ("word", "docx", "document", "report", "brief", "note",
                 "letter", "summary document", "write-up"),
}


def wants_a_file(question):
    """Returns the kind to build, or None if this is an ordinary question."""
    q = question.lower()
    if not any(v in q for v in MAKE_VERBS):
        return None
    # Spreadsheet before Document: "comparison table in a report" is a table.
    for kind in ("Spreadsheet", "Presentation", "Document"):
        if any(word in q for word in MAKE_KINDS[kind]):
            return kind
    return None


SYSTEM = (
    "You answer using the passages you are given.\n"
    "Every fact, figure, name and date must come from them — never from your "
    "own knowledge, and never invented.\n"
    "You may compare, weigh up and draw a conclusion the passages support, "
    "even when they state no conclusion themselves. If a question asks which "
    "is better and the passages give strengths on both sides, say that, and "
    "say what each is better at.\n"
    "Only say you cannot find it in the documents when they genuinely do not "
    "cover the subject at all.\n"
    "Answer in a few sentences, in plain language.\n"
    # A clerk in a Hyderabad school writes the question in the language she
    # thinks in; the policy she is asking about is in English. Answering in
    # English regardless makes her translate her own answer back, which is
    # both a worse product and the sort of thing that quietly decides who
    # uses software and who does not. The material stays whatever language it
    # is in — only the reply follows the question.
    "Reply in the language the question was asked in. If it was asked in "
    "Telugu, answer in Telugu; in Hindi, answer in Hindi; in English, answer "
    "in English. The documents may be in a different language from the "
    "question — quote names, figures and dates from them exactly as written, "
    "and translate only your own words around them."
)
