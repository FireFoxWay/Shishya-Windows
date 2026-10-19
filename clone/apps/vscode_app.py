#!/usr/bin/env python3
"""
Shishya — VS Code on the clone's screen.

The real VS Code, in the sandbox like every other app: no network, the
clone's own home for its settings and extensions, shared/work as the folder
it opens, and Shishya's tasks and shortcuts for running this OS (`shishya`
in its terminal, vm/shell/ctl.py). The host starts Code.exe straight into
the container and places its window on the clone's screen
(host/winvm.py launch_vscode).

This file runs only when VS Code cannot start yet: the host opens it with
--needs-admin to say what is missing, rather than nothing happening.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kit   # noqa: E402
from PySide6.QtWidgets import QApplication, QVBoxLayout   # noqa: E402

# Quoted: in PowerShell, unquoted (S,RA) is an expression, not text.
GRANT = ('icacls C:\\ /grant "*S-1-15-2-1700322577-3344956600-3688150473-1092480530-'
         '2905792460-468937178-3008308160:(S,RA)"')


class NeedsAdmin(kit.Window):
    def __init__(self):
        super().__init__("VS Code", 640, 330)
        col = QVBoxLayout(self.body)
        col.setContentsMargins(18, 14, 18, 14)
        col.addWidget(kit.label("VS Code needs one step first", role="title"))
        col.addWidget(kit.label(
            "VS Code runs on Node, which looks at the root of C: before it opens any file, "
            "and Windows does not let a sandboxed app do that until an administrator allows "
            "it. Run this once in a terminal opened as administrator, on your own desktop. "
            "It lets Shishya's sandbox read C:\\ itself and nothing below it.", wrap=True))
        cmd = kit.label(GRANT, wrap=True)
        cmd.setStyleSheet("font-family: Consolas, monospace; padding: 8px; background: #f2f2ee;")
        col.addWidget(cmd)
        copy = kit.button("Copy the command", lambda: QApplication.clipboard().setText(GRANT))
        col.addWidget(copy)
        col.addStretch(1)


if __name__ == "__main__":
    if "--needs-admin" in sys.argv:
        kit.application("VS Code")
        sys.exit(kit.run(NeedsAdmin()))
    kit.open_app("vscode_app.py")
