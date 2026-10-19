"""
Old model against new, on the held-out folders neither was trained on.

    python compare.py sample shishya-code shishya-code-trained    write each model's answers
    (then run verify.vbs — it checks them in the sandbox)
    python compare.py report                                     how many each got right
"""

import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"


def sample(models):
    (WORK / "eval_cands.jsonl").unlink(missing_ok=True)
    (WORK / "eval_results.jsonl").unlink(missing_ok=True)
    for m in models:
        subprocess.run([sys.executable, str(Path(__file__).with_name("sample.py")), "--model", m, "--k", "1",
                        "--tasks", str(WORK / "heldout_tasks.jsonl"), "--out", str(WORK / "eval_cands.jsonl"),
                        "--tag", "eval"], check=True)
    (WORK / "verify.json").write_text(json.dumps({"candidates": "eval_cands.jsonl",
                                                  "results": "eval_results.jsonl"}), encoding="utf-8")
    print("Now run verify.vbs, wait for work/verify.done, then: compare.py report")


def report():
    (WORK / "verify.json").unlink(missing_ok=True)
    rows = [json.loads(l) for l in (WORK / "eval_results.jsonl").read_text(encoding="utf-8").splitlines()]
    score = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        model = r["cid"].split("~")[1]
        score[model][0] += r["ok"]
        score[model][1] += 1
    for model, (ok, n) in sorted(score.items(), key=lambda kv: -kv[1][0]):
        print(f"{model:<28} {ok}/{n} = {100 * ok / n:.0f}%")


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "sample":
        sample(sys.argv[2:])
    elif sys.argv[1:] == ["report"]:
        report()
    else:
        print(__doc__)
