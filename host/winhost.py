#!/usr/bin/env python3
"""
Shishya — what the panel runs beside the web server, on Windows.

Two things that on the Mac were the VM's business:

  the model broker   the pipe the clone reaches the model through (broker.py)
  the watcher        requests the clone writes into shared/ because it cannot
                     do the thing itself: work out a lesson's procedure (the
                     model at full speed, on the host), start the browser
                     (only the host can grant it the web), shut the sandbox
                     down (the clone does not own its own job)

Each request is a file, read and removed, and every one lands in the ledger —
the shared folder is the one channel between the two sides, as it always was.
"""

import json
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import broker
import ledger
import paths
import winbox

TRACES = paths.SHARED / "traces"
_started = {}


def _record_model(ok, method, path):
    # Ordinary questions are not logged one by one — the ledger is for
    # decisions. Refusals are, and so is adding or removing a model.
    if not ok:
        ledger.record(ledger.DENY, "model.refused", f"{method} {path}"[:80], actor="clone",
                      detail="the broker allows questions to the model and nothing else")
    elif path.startswith(("/api/pull", "/api/delete")):
        ledger.record(ledger.ALLOW, "model.manage", f"{method} {path}"[:80], actor="clone")


def _is_head():
    import vm
    return vm.role() == "head"


def start():
    """Start the broker and the watcher once per panel."""
    if _started:
        return _started
    paths.ensure()
    b = broker.Broker(winbox.ensure_container(), on_request=_record_model,
                      may_manage=_is_head).start()
    _started["broker"] = b
    threading.Thread(target=_watch, daemon=True, name="clone-requests").start()
    return _started


def broker_state():
    b = _started.get("broker")
    return b.state() if b else {"pipe": broker.PIPE, "served": 0, "refused": 0, "last": None}


# ─── the clone's requests ───────────────────────────────────────────────────

def _python():
    exe = sys.executable
    return exe[:-len("pythonw.exe")] + "python.exe" if exe.lower().endswith("pythonw.exe") else exe


def _synthesise(folder):
    request = folder / ".synth-requested"
    request.unlink(missing_ok=True)
    ledger.record(ledger.INFO, "lesson.synth", folder.name, actor="clone",
                  detail="asked the host to work out the procedure")
    p = subprocess.run([_python(), str(paths.ROOT / "host" / "synth.py"), str(folder)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=1200, creationflags=winbox.CREATE_NO_WINDOW)
    if p.returncode != 0 or not (folder / "procedure.json").exists():
        why = (p.stderr or p.stdout or "synthesis failed").strip()[-600:]
        (folder / ".synth-error").write_text(why, encoding="utf-8")
        ledger.record(ledger.DENY, "lesson.synth.fail", folder.name, actor="system", detail=why)
    else:
        ledger.record(ledger.ALLOW, "lesson.learned", folder.name, actor="system")


def _launch(vm, req):
    """The clone asking for one of its own apps (clone/kit.py open_app).

    Written by the clone, so read as untrusted: only an app that exists in
    the clone's own apps folder, started into the clone's own container —
    the request can choose which of its apps, never anything else."""
    try:
        ask = json.loads(req.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        ask = {}
    req.unlink(missing_ok=True)
    name = str(ask.get("app", ""))
    args = [str(a)[:500] for a in (ask.get("args") or [])[:4]]
    if not re.fullmatch(r"[a-z]+_app\.py", name):
        ledger.record(ledger.DENY, "app.launch", name[:60] or "?", actor="clone",
                      detail="not one of the clone's apps")
        return
    ledger.record(ledger.INFO, "app.launch", name, actor="clone")
    try:
        vm.launch_app(name, *args)
    except Exception as e:                              # noqa: BLE001
        ledger.record(ledger.DENY, "app.launch.fail", name, actor="system",
                      detail=str(e)[:200])


def _watch():
    import vm
    busy = set()
    while True:
        # Often enough that a pick from the clone's Apps menu feels immediate.
        time.sleep(0.4)
        try:
            for req in TRACES.glob("*/.synth-requested"):
                folder = req.parent
                if folder.name not in busy:
                    busy.add(folder.name)

                    def work(f=folder):
                        try:
                            _synthesise(f)
                        finally:
                            busy.discard(f.name)
                    threading.Thread(target=work, daemon=True).start()

            for req in sorted(paths.SHARED.glob(".launch-*.json")):
                _launch(vm, req)

            stop = paths.SHARED / ".shutdown-requested"
            if stop.exists():
                stop.unlink(missing_ok=True)
                ledger.record(ledger.INFO, "vm.stop", "shut down from inside", actor="clone")
                vm.stop()
        except Exception as e:                          # noqa: BLE001
            # A watcher that dies takes every future request with it, silently.
            ledger.record(ledger.DENY, "watch.error", type(e).__name__, actor="system",
                          detail=str(e)[:200])
