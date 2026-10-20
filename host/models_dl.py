#!/usr/bin/env python3
"""
Shishya's trained models, fetched from the release and put into Ollama.
Runs on the HOST — the sandbox has no network and never will for this.

A model is too large for one release file (GitHub allows 2 GB), so each is
published in parts with a manifest, models.json:

    {"version": "1.0.5", "models": [{"name": "shishya-code-trained", "job": "code",
      "size": 4683071488, "sha256": "...", "parts": ["shishya-code-trained.gguf.part0", ...],
      "modelfile": "TEMPLATE ...", "score": "74% vs 59%"}]}

get() downloads each part, joins them, checks the whole file's sha256 against
the manifest — a file that does not match is deleted, never imported — writes
a Modelfile pointing at it, runs `ollama create`, and gives the model its job
on the Models screen. Progress is in var/models-get.json for the panel.
"""

import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import ledger
import paths

RELEASE = "https://github.com/FireFoxWay/Shishya-Windows/releases/latest/download/"
STORE = paths.DATA / "models"
STATE = paths.SHARED / ".models-get.json"   # in shared/, so the clone's Models app can show it
ROLES = paths.SHARED / ".models.json"
OLLAMA = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
_lock = threading.Lock()


def _say(**kw):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({**kw, "at": time.time()}), encoding="utf-8")


def state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"state": "idle"}


def manifest():
    with urllib.request.urlopen(RELEASE + "models.json", timeout=30) as r:
        return json.loads(r.read())


def _fetch(url, dest, label, done_bytes, total):
    tmp = dest.with_suffix(dest.suffix + ".part-download")
    with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as fh:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            fh.write(chunk)
            done_bytes[0] += len(chunk)
            if done_bytes[0] % (64 << 20) < (1 << 20):
                _say(state="downloading", model=label, pct=round(100 * done_bytes[0] / max(1, total)))
    tmp.replace(dest)


def _install(m, done_bytes, total):
    STORE.mkdir(parents=True, exist_ok=True)
    gguf = STORE / f"{m['name']}.gguf"
    if not (gguf.exists() and gguf.stat().st_size == m["size"]):
        h = hashlib.sha256()
        with open(gguf, "wb") as out:
            for part in m["parts"]:
                piece = STORE / part
                _fetch(RELEASE + part, piece, m["name"], done_bytes, total)
                with open(piece, "rb") as fh:
                    while chunk := fh.read(1 << 20):
                        out.write(chunk)
                        h.update(chunk)
                piece.unlink()
        if h.hexdigest() != m["sha256"]:
            gguf.unlink(missing_ok=True)
            raise RuntimeError(f"{m['name']} did not match its checksum — not installed")
    mf = STORE / f"{m['name']}.Modelfile"
    mf.write_text(f"FROM {gguf}\n{m['modelfile']}\n", encoding="utf-8")
    _say(state="installing", model=m["name"])
    r = subprocess.run([str(OLLAMA), "create", m["name"], "-f", str(mf)], capture_output=True,
                       text=True, creationflags=0x08000000)
    if r.returncode:
        raise RuntimeError(f"ollama create {m['name']} failed: {(r.stderr or r.stdout)[-200:]}")


def get(only=None):
    """Download and install every trained model in the latest release (or
    those named), then give each its job. One run at a time."""
    if not _lock.acquire(blocking=False):
        return {"error": "already downloading"}
    try:
        man = manifest()
        models = [m for m in man.get("models", []) if not only or m["name"] in only]
        total = sum(m["size"] for m in models)
        done = [0]
        ledger.record(ledger.ALLOW, "models.get", f"{len(models)} model(s), {total / 1e9:.1f} GB",
                      actor="guru", detail=f"from release {man.get('version')}")
        for m in models:
            _install(m, done, total)
        try:
            roles = json.loads(ROLES.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            roles = {}
        roles.update({m["job"]: m["name"] + ":latest" for m in models if m.get("job")})
        ROLES.write_text(json.dumps(roles, indent=2), encoding="utf-8")
        _say(state="done", models=[m["name"] for m in models], version=man.get("version"))
        return state()
    except Exception as e:                              # noqa: BLE001
        _say(state="failed", error=str(e)[:300])
        ledger.record(ledger.DENY, "models.get.fail", type(e).__name__, actor="system", detail=str(e)[:200])
        return state()
    finally:
        _lock.release()


def get_in_background(only=None):
    threading.Thread(target=get, args=(only,), daemon=True, name="models-get").start()
    return {"started": True}
