"""
Checks every candidate in work/candidates.jsonl inside Shishya's sandbox and
writes work/results.jsonl. Started outside the Claude app (explorer), as the
host is: it copies the task folders into the container's home, runs
container_runner.py in the container, and copies the results back.
"""

import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "work"
APP = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "Shishya"
sys.path.insert(0, str(APP / "host"))
import winbox   # noqa: E402
import winvm    # noqa: E402

# A job of its own. Sharing Shishya's named job meant Shishya, started while
# this ran, joined this job and was refused ("AssignProcessToJobObject:
# Access is denied").
winbox.JOB_NAME = "Local\\Shishya.Training.Job"

# Which candidates and where the results go: work/verify.json when the test
# set is being checked, the training candidates otherwise.
conf = {"candidates": "candidates.jsonl", "results": "results.jsonl"}
if (WORK / "verify.json").exists():
    conf.update(json.loads((WORK / "verify.json").read_text(encoding="utf-8")))
CANDS, RESULTS = WORK / conf["candidates"], WORK / conf["results"]
log = open(WORK / "verify.log", "w", encoding="utf-8")
try:
    trainhome = winvm.clone_home() / "trainhome"
    trainhome.mkdir(exist_ok=True)
    for f in (WORK / "folders").iterdir():
        dest = trainhome / f.name
        if not dest.exists():
            shutil.copytree(f, dest)
    tasks = {t["id"]: t for t in map(json.loads, (WORK / "tasks.jsonl").read_text(encoding="utf-8").splitlines())}
    done = set()
    if RESULTS.exists():
        done = {json.loads(l)["cid"] for l in RESULTS.read_text(encoding="utf-8").splitlines()}
    jobs = []
    for l in CANDS.read_text(encoding="utf-8").splitlines():
        c = json.loads(l)
        if c["cid"] in done or not c["code"].strip():
            continue
        jobs.append({"cid": c["cid"], "task": c["task"], "folder": c["folder"], "code": c["code"],
                     "expect": tasks[c["task"]]["expect"]})
    (trainhome / "jobs.jsonl").write_text("\n".join(json.dumps(j) for j in jobs), encoding="utf-8")
    shutil.copy(Path(__file__).with_name("container_runner.py"), trainhome / "container_runner.py")
    print(f"{len(jobs)} candidates to check", file=log, flush=True)
    rt = winvm._need_runtime()
    r = winbox.run([str(rt / "python.exe"), "-I", "-X", "utf8", str(trainhome / "container_runner.py"),
                    str(trainhome)], caps=(), env=winvm.clone_env(), cwd=str(trainhome), timeout=40 * len(jobs) + 300)
    print("runner exit", r["code"], r["out"][-2000:], file=log, flush=True)
    with RESULTS.open("a", encoding="utf-8") as out:
        out.write((trainhome / "results.jsonl").read_text(encoding="utf-8").rstrip("\n") + "\n")
except Exception:
    import traceback
    traceback.print_exc(file=log)
finally:
    (WORK / "verify.done").write_text("done", encoding="utf-8")
