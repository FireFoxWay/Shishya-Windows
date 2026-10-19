#!/usr/bin/env python3
"""
Shishya — VS Code on the clone's screen.

The real VS Code, in the sandbox like every other app: no network, the
clone's own home for its settings and extensions, shared/work as the folder
it opens. It is not started from here. The host starts Code.exe straight
into the container and places its window on the clone's screen
(host/winvm.py launch_vscode), because Electron needs things only the host
can arrange — this file is the name the menus and the host agree on.

Started by hand inside the sandbox, it can only say so.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import kit   # noqa: E402

if __name__ == "__main__":
    kit.open_app("vscode_app.py")
