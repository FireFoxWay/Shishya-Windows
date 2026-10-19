#!/usr/bin/env python3
"""
shishya — the clone's own OS, from a command line. Runs INSIDE the sandbox.

    shishya apps                 what can be opened
    shishya open billing         open an app on the clone's screen
    shishya open files <folder>  ...with what it should show
    shishya lessons              what has been taught
    shishya run                  pick a lesson and perform it
    shishya run <lesson-id>      perform that one
    shishya shutdown             ask for the sandbox to be shut down

VS Code's tasks and keyboard shortcuts call this, so a shortcut can do a
task: open Billing, run the morning stock lesson, and so on. Nothing here
acts directly. Each command is a request the host reads and checks, as the
start panel's are (host/winhost.py): only the clone's own apps, only taught
lessons, and every one written in the ledger.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common   # noqa: E402

APPS = Path(__file__).resolve().parents[2] / "clone" / "apps"


def apps():
    return sorted(p.name[:-len("_app.py")] for p in APPS.glob("*_app.py"))


def lessons():
    found = sorted(common.TRACES.glob("*/procedure.json"), key=lambda f: f.stat().st_mtime,
                   reverse=True)
    out = []
    for f in found:
        try:
            title = json.loads(f.read_text(encoding="utf-8")).get("title") or f.parent.name
        except (OSError, ValueError):
            continue
        out.append((f.parent.name, title))
    return out


def _request(kind, body):
    (common.SHARED / f".{kind}-{time.time_ns()}.json").write_text(json.dumps(body), encoding="utf-8")


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__.strip().split("\n\n")[1])
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "apps":
        print("\n".join(apps()))
    elif cmd == "open":
        if not rest or rest[0] not in apps():
            print(f"Open which? One of: {', '.join(apps())}")
            return 2
        _request("launch", {"app": f"{rest[0]}_app.py", "args": rest[1:]})
        print(f"Opening {rest[0]} on the clone's screen.")
    elif cmd == "lessons":
        for lid, title in lessons():
            print(f"{lid:<28} {title}")
    elif cmd == "run":
        known = lessons()
        if not known:
            print("Nothing has been taught yet. Teach a lesson first.")
            return 2
        lid = rest[0] if rest else None
        if not lid:
            for n, (_, title) in enumerate(known, 1):
                print(f"  {n}. {title}")
            pick = input("Run which? ").strip()
            if not pick.isdigit() or not 1 <= int(pick) <= len(known):
                print("Nothing run.")
                return 2
            lid = known[int(pick) - 1][0]
        if lid not in {k for k, _ in known}:
            print(f"No lesson called {lid!r}.")
            return 2
        _request("run", {"lesson": lid})
        print(f"Asked Shishya to run {dict(known)[lid]!r}. Watch it on the clone's screen.")
    elif cmd == "shutdown":
        (common.SHARED / ".shutdown-requested").write_text("1", encoding="utf-8")
        print("Asked for the sandbox to shut down.")
    else:
        print(f"Unknown command {cmd!r}. Try: shishya help")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
