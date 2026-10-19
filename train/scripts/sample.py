"""
Candidate scripts for every task, from a local model through Ollama.

The prompt is exactly what Shishya's Code app sends — its system prompt and
codegen.describe_material()'s listing of the folder — with the paths as the
sandbox will see them when the scripts are checked (verify_host.py).

    python sample.py --model shishya-code --k 2
    python sample.py --model qwen3.8:27b --k 1 --only-failed   the teacher, for what the student missed
"""

import argparse
import json
import os
import sys
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
SHISHYA = Path(os.environ.get("SHISHYA_SRC", Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Shishya"))
TRAINHOME = Path(os.environ["LOCALAPPDATA"]) / "Packages" / "shishya.clone" / "AC" / "home" / "trainhome"
sys.path.insert(0, str(SHISHYA / "vm" / "shell"))
import codegen   # noqa: E402
import common    # noqa: E402

APP_SYSTEM = (
    "You write short, complete Python 3 scripts. Output the code and nothing else — no "
    f"explanation, no markdown fences. The script runs in a sandbox on {codegen.PLATFORM} with "
    "pandas, openpyxl, python-docx and python-pptx available. Build paths with pathlib — "
    "Path.home() / 'shared' / 'training' / '<name>' — never a string starting with ~. Print "
    "results rather than returning them, and keep it under 40 lines.")
SYSTEMS = [APP_SYSTEM, codegen.CODE_SYSTEM]
_listing_lock = threading.Lock()


def listing(fid):
    """describe_material() of this task's folder, with the paths the
    sandbox will use. One at a time: it reads a module-level setting."""
    local = WORK / "folders" / fid / "shared" / "training"
    with _listing_lock:
        common.TRAINING = local
        text = codegen.describe_material()
    return text.replace(str(local), str(TRAINHOME / fid / "shared" / "training"))


def ask(model, system, prompt, temperature):
    body = {"model": model, "system": system, "prompt": prompt, "stream": False, "think": False,
            "options": {"temperature": temperature, "num_ctx": 8192, "num_predict": 1200}}
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        text = json.loads(r.read())["response"]
    return codegen.repair(codegen.strip_fences(common._strip_think(text)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="shishya-code")
    ap.add_argument("--k", type=int, default=2)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--only-failed", action="store_true")
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--tag", default="", help="keeps a second pass apart from the first")
    ap.add_argument("--tasks", default=str(WORK / "tasks.jsonl"))
    ap.add_argument("--out", default=str(WORK / "candidates.jsonl"))
    args = ap.parse_args()

    tasks = [json.loads(l) for l in Path(args.tasks).read_text(encoding="utf-8").splitlines()]
    if args.only_failed:
        passed = set()
        res = WORK / "results.jsonl"
        if res.exists():
            for l in res.read_text(encoding="utf-8").splitlines():
                r = json.loads(l)
                if r["ok"]:
                    passed.add(r["task"])
        tasks = [t for t in tasks if t["id"] not in passed]
    out_path = Path(args.out)
    lock = threading.Lock()
    done = [0]

    def one(t, i):
        system = SYSTEMS[(hash(t["id"]) + i) % 2]
        prompt = f"{listing(t['folder'])}\n\nWrite a Python script that: {t['brief']}"
        try:
            code = ask(args.model, system, prompt, args.temperature if i else 0.2)
        except Exception as e:                       # noqa: BLE001
            code = ""
            print("error", t["id"], e, flush=True)
        row = {"cid": f"{t['id']}~{args.model}~{args.tag}{i}", "task": t["id"], "folder": t["folder"],
               "system": system, "prompt": prompt, "code": code, "model": args.model}
        with lock:
            with out_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row) + "\n")
            done[0] += 1
            if done[0] % 50 == 0:
                print(f"{done[0]}/{len(tasks) * args.k}", flush=True)

    with ThreadPoolExecutor(args.threads) as pool:
        for t in tasks:
            for i in range(args.k):
                pool.submit(one, t, i)
    print("done", done[0])


if __name__ == "__main__":
    main()
