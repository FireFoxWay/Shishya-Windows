#!/usr/bin/env python3
"""
The home screen's data, in one call (web/home.html).

Everything on that screen is real: today's takings are read from the
counter's own sales book, the tile badges from the inbox, the catalogue and
the schedule, the dock from the sandbox itself. It was designed as a demo
with sample figures; a screen that shows invented numbers to a shop owner is
the one kind of wrong this project exists not to be, so nothing here is
sample data, and where there is nothing yet it says so.

Read-only. Polled every few seconds, so every part is cheap and every part
fails on its own — one unreadable file must not blank the whole screen.
"""

import datetime as dt
import json
import sys
import time

import dashboard
import ledger
import paths
import profile
import vm

SHARED = paths.SHARED
WINDOWS = sys.platform == "win32"


def _safe(fn, default):
    try:
        return fn()
    except Exception:                                    # noqa: BLE001
        return default


def today():
    """Takings, bills and the GST inside them, for today and the same
    weekday last week — the comparison a shopkeeper actually makes."""
    rows = dashboard._sales_rows()
    day = dt.date.today()
    week_ago = (day - dt.timedelta(days=7)).isoformat()
    day = day.isoformat()
    takings = last_week = tax = 0.0
    bills, voided, last = set(), set(), ""
    for r in rows:
        at = (r.get("at") or "")
        when = at[:10]
        if when == day:
            takings += dashboard._num(r.get("amount"))
            tax += dashboard._num(r.get("tax"))
            if r.get("kind") == "sale":
                bills.add(r.get("bill"))
            if r.get("kind") == "void":
                voided.add(r.get("bill"))
            last = max(last, at)
        elif when == week_ago:
            last_week += dashboard._num(r.get("amount"))
    change = None
    if last_week > 0:
        change = round(100 * (takings - last_week) / last_week)
    return {"takings": round(takings, 2), "bills": len(bills - voided),
            "tax": round(tax, 2), "last_week": round(last_week, 2), "change": change,
            "last_sale": last[11:16] if last else None, "any_sales": bool(rows)}


def _count_files(folder):
    try:
        return sum(1 for p in folder.iterdir()
                   if p.is_file() and not p.name.startswith(".") and p.suffix != ".part")
    except OSError:
        return 0


def _next_schedule():
    """The next scheduled run today, or the first one tomorrow."""
    items = [i for i in vm.read_schedules() if i.get("enabled", True) and i.get("at")]
    if not items:
        return None
    now = time.strftime("%H:%M")
    later = sorted((i for i in items if i["at"] >= now and i.get("last") != time.strftime("%Y-%m-%d")),
                   key=lambda i: i["at"])
    pick = later[0] if later else sorted(items, key=lambda i: i["at"])[0]
    return {"label": pick.get("label") or pick.get("runner"), "at": pick["at"],
            "today": bool(later)}


def _model():
    try:
        return json.loads((SHARED / ".models.json").read_text(encoding="utf-8")).get("answers")
    except (OSError, ValueError):
        return None


def network(state):
    """What the sandbox may reach: the policy, and the measurement."""
    if state != "running":
        return {"mode": None, "locked": None, "detail": "the sandbox is not running"}
    egress = vm.egress_state()
    if WINDOWS:
        import winvm
        mode = winvm._mode()
    else:
        browse = vm.browsing_state().get("browsing")
        ssh = vm.ssh_state().get("ssh")
        mode = "ssh" if ssh else "browsing" if browse else \
            ("locked" if egress.get("locked") else "open")
    return {"mode": mode, "locked": egress.get("locked"), "detail": egress.get("detail")}


def activity(state, lesson=None):
    """What the clone is doing, for the orb. Read from the same state the
    rest of the panel reads — never guessed."""
    if lesson and lesson.get("state") == "running":
        return {"state": "working", "label": "Working",
                "detail": f"performing the lesson “{lesson.get('title')}”"}
    job = _safe(vm.job_state, {})
    if job.get("state") in ("working", "starting"):
        return {"state": "solving", "label": "Working on a job",
                "detail": job.get("step") or "working on the job you gave it"}
    clone = _safe(lambda: (SHARED / ".state").read_text(encoding="utf-8").strip(), "idle")
    if state in ("starting",):
        return {"state": "connecting", "label": "Starting", "detail": "the sandbox is starting"}
    if state != "running":
        return {"state": "breathing", "label": "Sandbox off",
                "detail": "the sandbox is not running — nothing is being worked on"}
    if clone == "working":
        return {"state": "composing", "label": "Thinking",
                "detail": "an app on the clone's screen is waiting for the model"}
    if clone == "wheel":
        return {"state": "listening", "label": "Watching",
                "detail": "a lesson is being taught — do the job once, then press I'm done"}
    return {"state": "breathing", "label": "Ready", "detail": "idle, and ready when you are"}


def everything(lesson=None):
    status = _safe(vm.status, {"state": "unknown"})
    state = status.get("state", "unknown")
    who = profile.read()
    stock = _safe(lambda: dashboard._sandbox("books").running_out(), [])
    alerts = _safe(lambda: vm.alerts().get("alerts", []), [])
    entries = _safe(lambda: ledger.read(limit=2000), [])
    midnight = time.mktime(dt.date.today().timetuple())
    todays = [e for e in entries if e.get("t", 0) >= midnight]
    out = {
        "platform": "windows" if WINDOWS else sys.platform,
        "name": (who.get("name") or "").strip(),
        "role": vm.role(),
        "today": _safe(today, None),
        "inbox": _count_files(SHARED / "inbox"),
        "training": _count_files(SHARED / "training"),
        "lessons": len(_safe(vm.lessons, [])),
        "low_stock": len(stock),
        "out_of_stock": sum(1 for r in stock if r.get("stock", 1) <= 0),
        "alerts": [a.get("text") or a.get("message") or str(a) for a in alerts][:3],
        "approvals": len(_safe(vm.pending_approvals, [])),
        "schedule": _safe(_next_schedule, None),
        "model": _model(),
        "ledger": {"today": len(todays),
                   "refused": sum(1 for e in todays if e.get("verdict") == "deny")},
        "sandbox": {"state": state, "processes": status.get("processes"),
                    "detail": status.get("detail")},
        "network": _safe(lambda: network(state), {"mode": None, "locked": None}),
        "activity": activity(state, lesson),
        "clock": time.strftime("%H:%M"),
    }
    if WINDOWS:
        import winbox
        import winvm
        out["limits"] = winvm.limits()
        out["limits"]["ram_used"] = round(_safe(winbox.memory_used, 0) / 1024 ** 3, 1) \
            if state == "running" else 0
        if state == "running":
            import screen
            out["sandbox"]["popped"] = _safe(screen.popped, False)
    return out
