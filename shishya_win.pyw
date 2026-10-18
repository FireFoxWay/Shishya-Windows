#!/usr/bin/env python3
"""
Shishya for Windows — what Shishya.exe runs.

One window, the control panel, as a native Windows window rather than a
browser tab: the panel's web pages hosted in WebView2, the browser engine
Windows itself ships. Behind it, in this same process, the panel's server,
the model broker and the watcher (serve.py, host/winhost.py).

The clone lives only while this window is open. Every process the clone
runs is in one Job Object that this process holds, set to kill everything
when the last handle closes — so closing Shishya, or Shishya crashing, ends
the clone with it. Nothing of the clone's keeps running unwatched in the
background after you thought you had shut it.

    pythonw shishya_win.pyw            the window
    pythonw shishya_win.pyw --port N   on another port
"""

import ctypes
import os
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "host"))

import paths   # noqa: E402

TITLE = "Shishya"
APP_ID = "Shishya.Panel"


def _log_to_file():
    """A windowed program has no console; its output goes somewhere a person
    can find when something went wrong, rather than nowhere."""
    logs = paths.VAR / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = open(logs / "panel.log", "a", encoding="utf-8", buffering=1)
    out.write(f"\n— started {time.strftime('%Y-%m-%d %H:%M:%S')} —\n")
    sys.stdout = sys.stderr = out
    return out


def _single_instance():
    """A second Shishya would start a second broker on the same pipe and a
    second set of watchers on the same files. Bring the first one forward."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW(None, False, "Local\\Shishya.Panel")
    if kernel32.GetLastError() == 183:                 # ERROR_ALREADY_EXISTS
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
        sys.exit(0)


def _free_port(wanted):
    for port in (wanted, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return wanted


def _fail(message):
    ctypes.windll.user32.MessageBoxW(None, message, TITLE, 0x10)
    sys.exit(1)


def main():
    _single_instance()
    _log_to_file()
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    port = 8200
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    port = _free_port(port)

    import serve
    try:
        serve.main(port, block=False)
    except SystemExit as e:
        _fail(f"Shishya could not start its panel: {e}")
    url = f"http://localhost:{port}/"
    print(f"panel at {url}")

    icon = ROOT / "windows" / "shishya.ico"
    try:
        import webview
        window = webview.create_window(TITLE, url, width=1520, height=960, min_size=(1100, 700),
                                       background_color="#0b0c0e", text_select=True)
        webview.start(gui="edgechromium", private_mode=False,
                      storage_path=str(paths.VAR / "webview"),
                      icon=str(icon) if icon.exists() else None)
    except Exception:
        # No WebView2 runtime, or pythonnet could not load .NET. Edge in app
        # mode is the same engine in a window of its own; every Windows 11
        # has it. Wait on it, so the clone lives as long as that window.
        traceback.print_exc()
        edge = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / \
            "Microsoft" / "Edge" / "Application" / "msedge.exe"
        if not edge.exists():
            _fail("Shishya needs Microsoft Edge WebView2 to show its window. Install the "
                  "WebView2 runtime from Microsoft and start Shishya again.")
        profile = paths.VAR / "edge-profile"
        subprocess.run([str(edge), f"--app={url}", f"--user-data-dir={profile}",
                        "--no-first-run", "--window-size=1520,960"])

    # The window is closed. Stop the clone explicitly rather than relying on
    # the job closing with this process — it says so in the ledger.
    try:
        import ledger
        import vm
        if vm.status().get("state") in ("running", "starting"):
            ledger.record(ledger.INFO, "vm.stop", "Shishya closed", actor="guru",
                          detail="the clone lives only while the panel is open")
            vm.stop()
    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        traceback.print_exc()
        _fail("Shishya stopped unexpectedly. The details are in var\\logs\\panel.log.")
