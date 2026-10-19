#!/usr/bin/env python3
"""
Shishya — which model should do each job. Runs INSIDE the sandbox, from the
Models app's "Test them on Shishya's jobs", or by hand:

    python jobbench.py                    every local model, every job
    python jobbench.py --apply            ...and give each job its winner
    python jobbench.py --models a,b --jobs code

bench.py asked one question of every model. This asks each job's own
questions, in the exact shape the apps ask them, with answers known in
advance, and judges the result rather than the prose:

  code       the script is run here, in the sandbox, and its output checked
  answers    grounded answers from passages, an honest "they don't say",
             and the decide step that routes a request to the right tool
  documents  a schema-shaped spreadsheet built from the given facts

Each job goes to the model that passes the most of its tests; a tie goes to
the faster one. Small and quick wins whenever it is as right as big and
slow — the point of a model per job.
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import codegen     # noqa: E402
import common      # noqa: E402
import documents   # noqa: E402
import library     # noqa: E402

POLICY = (common.TRAINING / "attendance-policy.md")
CIRCULAR = (common.TRAINING / "circular-exam-schedule.txt")


def _text(p, n=1600):
    try:
        return p.read_text(encoding="utf-8")[:n]
    except OSError:
        return ""


def _passages():
    return "\n\n".join(f"[from {p.name}]\n{_text(p)}" for p in (POLICY, CIRCULAR) if p.exists())


def _first_training_file():
    names = sorted(p.name for p in common.TRAINING.iterdir()
                   if p.is_file() and not p.name.startswith("."))
    return names[0] if names else "?"


# ─── the tests ──────────────────────────────────────────────────────────────

def code_test(brief, check):
    def run(model):
        code = codegen.repair(common.ask(f"{codegen.describe_material()}\n\nWrite a Python script that: {brief}",
                                         system=codegen.CODE_SYSTEM, budget=4096, timeout=900,
                                         model=model))
        if not codegen.usable(code):
            return False, "wrote no program"
        out, err = codegen.run_script(code)
        if not out:
            return False, f"crashed: {(err or '?').strip().splitlines()[-1][:60]}"
        return check(out), out[:80].replace("\n", " | ")
    return run


# An answer that opens by thinking aloud, or recites the instructions back
# ("...when they genuinely do not cover..."), is not one a person should be
# shown, however right the words in it are.
THINKING_ALOUD = ("okay", "first, i need", "let me ", "alright")
RECITED = "genuinely do not cover"


def answer_test(question, check):
    def run(model):
        out = common.ask(f"PASSAGES:\n{_passages()}\n\nQUESTION: {question}",
                         system=library.SYSTEM, timeout=600, model=model)
        low = out.lower().strip()
        clean = not low.startswith(THINKING_ALOUD) and RECITED not in low
        return clean and check(low), out[:80].replace("\n", " ")
    return run


def decide_test(request, want):
    def run(model):
        prompt = f"The user's documents are: {', '.join(p.name for p in common.TRAINING.iterdir())}\n\nRequest: {request}"
        try:
            out = json.loads(common.ask(prompt, system=codegen.DECIDE_SYSTEM, schema=codegen.DECIDE,
                                        budget=1024, timeout=600, model=model))
        except ValueError:
            return False, "not JSON"
        return out.get("action") == want, f"chose {out.get('action')}"
    return run


def document_test():
    def run(model):
        kind = "Spreadsheet"
        prompt = (f"{documents.ASKS[kind]}\n\nWHAT IS NEEDED:\na table of the exam dates and timings\n\n"
                  f"SOURCE MATERIAL — build from these facts and invent no others:\n{_passages()}\n\n"
                  "Give it a short filename, no extension.")
        try:
            spec = json.loads(common.ask(prompt, schema=documents.SCHEMAS[kind], budget=4096,
                                         timeout=900, model=model))
        except ValueError:
            return False, "not JSON"
        flat = json.dumps(spec).lower()
        ok = bool(spec.get("filename")) and "march" in flat and "row 1" not in flat
        return ok, f"{spec.get('filename')!r}"
    return run


TESTS = {
    "code": [
        ("hello", code_test("print hello world", lambda o: "hello world" in o.lower())),
        ("list", code_test("list the files in my training folder",
                           lambda o: _first_training_file().lower() in o.lower())),
        ("count", code_test("count how many students are in class-9b-term1.csv and print the number",
                            lambda o: any(ch.isdigit() for ch in o))),
    ],
    "answers": [
        ("grounded", answer_test("Can a student with 70% attendance sit the annual exam?",
                                 lambda o: "principal" in o or "medical" in o or "exempt" in o)),
        ("absent", answer_test("What is the school's bus fee?",
                               lambda o: any(w in o for w in ("don't", "do not", "does not", "not mention",
                                                             "no information", "not say", "cannot find",
                                                             "can't find", "not cover", "not in")))),
        ("route-code", decide_test("how many students in class 9B scored above 80 in maths", "code")),
        ("route-answer", decide_test("what is the minimum attendance to sit the exam", "answer")),
    ],
    "documents": [
        ("sheet", document_test()),
    ],
}


def fits(model):
    """Was this model wholly in graphics memory when it last answered?"""
    try:
        for m in common.model_request("GET", "/api/ps", timeout=10).get("models", []):
            if m.get("name") == model or m.get("model") == model:
                return m.get("size_vram", 0) >= m.get("size", 1)
    except Exception:                                  # noqa: BLE001
        pass
    return True


def installed():
    tags = common.model_request("GET", "/api/tags", timeout=20)
    return [m["name"] for m in tags.get("models", []) if "cloud" not in m["name"]]


def measure(models=None, jobs=None, say=print):
    """Every model on every job's tests. Returns (results per job, winners)."""
    models = models or installed()
    jobs = [j for j in (jobs or TESTS) if j in TESTS]
    table = {}
    for model in models:
        for job in jobs:
            passed, spent = 0, 0.0
            for name, run in TESTS[job]:
                start = time.time()
                try:
                    ok, note = run(model)
                except Exception as e:                 # noqa: BLE001 — a failure is a result
                    ok, note = False, f"{type(e).__name__}: {str(e)[:60]}"
                took = time.time() - start
                spent += took
                passed += bool(ok)
                say(f"{model:<24}{job:<10}{name:<14}{'pass' if ok else 'FAIL':<6}{took:>6.1f}s  {note}")
            table.setdefault(job, []).append({"model": model, "passed": passed,
                                              "of": len(TESTS[job]), "seconds": round(spent, 1),
                                              "fits": fits(model)})
    # A model that does not fit on the graphics card runs partly on the CPU:
    # right, but minutes per answer. It wins a job only if nothing that fits
    # passes anything.
    winners = {job: sorted(rows, key=lambda r: (not r["fits"], -r["passed"], r["seconds"]))[0]["model"]
               for job, rows in table.items()}
    (common.SHARED / ".bench-jobs.json").write_text(
        json.dumps({"at": time.strftime("%Y-%m-%d %H:%M"), "results": table, "winners": winners},
                   indent=2), encoding="utf-8")
    return table, winners


def apply(winners):
    """Give each job its winner — the same file the Models screen writes."""
    try:
        chosen = json.loads(common.ROLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        chosen = {}
    chosen.update(winners)
    common.ROLES.write_text(json.dumps(chosen, indent=2), encoding="utf-8")
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models")
    ap.add_argument("--jobs")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    models = [m.strip() for m in args.models.split(",")] if args.models else None
    jobs = [j.strip() for j in args.jobs.split(",")] if args.jobs else None
    table, winners = measure(models, jobs, say=lambda line: print(line, flush=True))
    print()
    for job, rows in table.items():
        best = next(r for r in rows if r["model"] == winners[job])
        print(f"{job:<10} → {best['model']}  ({best['passed']}/{best['of']} in {best['seconds']}s)")
    if args.apply and winners:
        apply(winners)
        print("Applied to the Models screen.")


if __name__ == "__main__":
    main()
