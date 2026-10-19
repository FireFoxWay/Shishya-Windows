"""
Runs INSIDE Shishya's sandbox: every candidate script, each with its own
task folder as home, and whether it printed the known answer. Six at a time.

    python container_runner.py <trainhome>        reads/writes jobs.jsonl / results.jsonl there
"""

import json
import os
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

home = Path(sys.argv[1])
jobs = [json.loads(l) for l in (home / "jobs.jsonl").read_text(encoding="utf-8").splitlines()]
scripts = home / "scripts"
scripts.mkdir(exist_ok=True)
lock = threading.Lock()


def check(n, job, out):
    script = scripts / f"{n}.py"
    script.write_text(job["code"], encoding="utf-8")
    user = home / job["folder"]
    env = {**os.environ, "USERPROFILE": str(user), "HOME": str(user),
           "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "MPLBACKEND": "Agg"}
    try:
        p = subprocess.run([sys.executable, "-X", "utf8", str(script)], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=40, cwd=str(user), env=env)
        stdout, stderr, rc = p.stdout, p.stderr, p.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, rc = "", "timed out", -1
    expect = job["expect"]
    ok = rc == 0 and bool(stdout.strip()) and (not expect or any(e.lower() in stdout.lower() for e in expect))
    with lock:
        out.write(json.dumps({"cid": job["cid"], "task": job["task"], "ok": ok, "rc": rc,
                              "out": stdout[-400:], "err": stderr[-400:]}) + "\n")
        out.flush()


with (home / "results.jsonl").open("w", encoding="utf-8") as out:
    with ThreadPoolExecutor(6) as pool:
        for n, job in enumerate(jobs):
            pool.submit(check, n, job, out)
