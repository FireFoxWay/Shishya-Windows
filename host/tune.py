#!/usr/bin/env python3
"""
Shishya — models made for Shishya's own jobs. Runs on the HOST.

    python host/tune.py              make every tuned model whose base is here
    python host/tune.py --list       what would be made, from what

A general model asked to "write a Python script that prints hello world"
answered with a paragraph, a markdown fence and a script that read a file
nobody had. Not wrong — just not what this sandbox needs. These are the
same open models with Shishya's rules and a handful of worked examples
built in, made with Ollama's own create (the Modelfile route), so nothing
is retrained and nothing leaves this machine:

  shishya-code       from qwen2.5-coder:7b — code only, pathlib paths into
                     shared/, print the result, no network, no input()
  shishya-answers    from qwen3:4b — answers only from the passages given,
                     and says plainly when they do not cover the question
  shishya-documents  from qwen3:4b — real headings and rows from the facts
                     given, never "Row 1" or "[Name]"

The code examples are written in the exact shape the apps send and read no
file, so the model has seen the job's form before the first real one arrives
without being told about files that are not there. Which model then does each
job is not assumed: vm/jobbench.py runs every candidate on Shishya's real
tasks inside the sandbox and gives each job the one that passes most,
fastest.
"""

import argparse
import json
import sys
import urllib.request

OLLAMA = "http://127.0.0.1:11434"

CODE_SYSTEM = (
    "You write short, complete Python 3 scripts for a sandbox on Windows. Output the code "
    "and nothing else — no explanation, no markdown fences. pandas, openpyxl, matplotlib, "
    "python-docx and python-pptx are available; there is no network and no keyboard, so "
    "never call input() or fetch a URL. Read the user's files from "
    "Path.home() / 'shared' / 'training' and save anything you make to "
    "Path.home() / 'shared' / 'work'. Print the result. Under 40 lines.")

ANSWER_SYSTEM = (
    "You answer using only the passages you are given. Every fact, figure, name and date "
    "comes from them. Answer in one to three plain sentences and name the document it came "
    "from. If the passages do not cover the question, say so in one sentence and say what "
    "they do cover. Never invent.")

DOCUMENT_SYSTEM = (
    "You design documents, spreadsheets and slides from the facts you are given. Use real "
    "headings, real rows and real sentences built from those facts — never placeholders "
    "like 'Row 1', '[Name]' or 'Lorem ipsum', and never facts that were not given. Keep "
    "filenames short, lower-case, with hyphens.")


def _code(brief):
    return f"Write a Python script that: {brief}"


TUNED = {
    "shishya-code": {
        "from": "qwen2.5-coder:7b",
        "system": CODE_SYSTEM,
        "parameters": {"temperature": 0.2, "num_ctx": 8192},
        "messages": [
            {"role": "user", "content": _code("print hello world")},
            {"role": "assistant", "content": 'print("hello world")'},
            {"role": "user", "content": _code("list the files in my work folder with their sizes")},
            {"role": "assistant", "content":
                "from pathlib import Path\n\n"
                "work = Path.home() / 'shared' / 'work'\n"
                "for f in sorted(work.iterdir()):\n"
                "    if f.is_file():\n"
                "        print(f\"{f.name:<40} {f.stat().st_size:>10,} bytes\")"},
        ],
    },
    "shishya-answers": {
        "from": "qwen3:4b",
        "system": ANSWER_SYSTEM,
        "parameters": {"temperature": 0.2, "num_ctx": 8192},
        # No worked examples here, deliberately. Examples are earlier turns of
        # the conversation, so their passages read as still on the table: asked
        # about one file, the model cited "timings.txt" from an example.
        "messages": [],
    },
    "shishya-documents": {
        "from": "qwen3:4b",
        "system": DOCUMENT_SYSTEM,
        "parameters": {"temperature": 0.4, "num_ctx": 8192},
        "messages": [],
    },
}


def _call(path, body=None, timeout=600):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(OLLAMA + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def installed():
    return {m["name"] for m in json.loads(_call("/api/tags"))["models"]}


def create(name, spec):
    body = {"model": name, "from": spec["from"], "system": spec["system"],
            "parameters": spec["parameters"], "stream": False}
    if spec["messages"]:
        body["messages"] = spec["messages"]
    out = json.loads(_call("/api/create", body))
    if out.get("status") != "success":
        raise RuntimeError(f"{name}: {out}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()
    have = installed()
    for name, spec in TUNED.items():
        if args.list:
            print(f"{name:<20} from {spec['from']:<20} {'ready' if spec['from'] in have else 'base missing'}")
            continue
        if spec["from"] not in have:
            print(f"{name}: skipped — {spec['from']} is not downloaded")
            continue
        create(name, spec)
        print(f"{name}: made from {spec['from']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
