"""
The training set: for each task, a script that ran in the sandbox and printed
the known answer. Whole folders are held out for the test, so the model is
judged on files it never trained on.

    python build_sft.py          writes work/train.jsonl, work/heldout_tasks.jsonl
"""

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sample   # noqa: E402  — the listing as the app writes it today

WORK = Path(__file__).resolve().parent.parent / "work"
HELD_OUT = 0.15


def main():
    tasks = [json.loads(l) for l in (WORK / "tasks.jsonl").read_text(encoding="utf-8").splitlines()]
    cands = {c["cid"]: c for c in map(json.loads, (WORK / "candidates.jsonl").read_text(encoding="utf-8").splitlines())}
    passed = {}
    for r in map(json.loads, (WORK / "results.jsonl").read_text(encoding="utf-8").splitlines()):
        if r["ok"] and r["cid"] in cands:
            passed.setdefault(r["task"], []).append(cands[r["cid"]])

    folders = sorted({t["folder"] for t in tasks})
    rng = random.Random(11)
    held = set(rng.sample(folders, max(1, int(len(folders) * HELD_OUT))))

    train, seen = [], set()
    for t in tasks:
        if t["folder"] in held:
            continue
        for c in passed.get(t["id"], [])[:2]:          # at most two good answers per task
            # The request with today's listing, not the one it was sampled
            # with: training and real use must see the same kind of prompt.
            prompt = f"{sample.listing(t['folder'])}\n\nWrite a Python script that: {t['brief']}"
            code = c["code"].replace("\r\n", "\n").strip()
            key = (prompt, code)
            if key in seen:
                continue
            seen.add(key)
            train.append({"prompt": [{"role": "system", "content": c["system"]},
                                     {"role": "user", "content": prompt}],
                          "completion": [{"role": "assistant", "content": code}]})
    rng.shuffle(train)
    (WORK / "train.jsonl").write_text("\n".join(json.dumps(x) for x in train), encoding="utf-8")
    heldout = [t for t in tasks if t["folder"] in held]
    (WORK / "heldout_tasks.jsonl").write_text("\n".join(json.dumps(t) for t in heldout), encoding="utf-8")
    solved = sum(1 for t in tasks if t["folder"] not in held and t["id"] in passed)
    print(f"{len(train)} training examples from {solved} solved tasks; "
          f"{len(heldout)} held-out tasks in {len(held)} folders")


if __name__ == "__main__":
    main()
