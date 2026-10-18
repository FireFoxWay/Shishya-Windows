#!/usr/bin/env python3
"""
Where the code is, and where the data is.

In a checkout they are the same folder, which is how this project has always
run: shared/ and var/ beside the source. An installed copy cannot work that
way. The program lives in %LOCALAPPDATA%\\Programs\\Shishya and is replaced
wholesale by every update; the shop's books must not live somewhere an
upgrade overwrites. So an installed copy keeps its data in
%LOCALAPPDATA%\\Shishya, and the installer marks the program folder with an
INSTALLED file so this module knows which case it is in.

SHISHYA_DATA overrides both, for tests and for anyone who wants the data on
another drive.
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _data_root():
    chosen = os.environ.get("SHISHYA_DATA")
    if chosen:
        return Path(chosen)
    if (ROOT / "INSTALLED").exists():
        if sys.platform == "win32":
            # A folder of its own, one level down. The clone's home IS this
            # folder (it can list it, not read what is in it), so it must hold
            # nothing but Shishya's — and %LOCALAPPDATA%\Shishya is a name
            # somebody may already have used for something else.
            local = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            return local / "Shishya" / "Data"
        return Path.home() / ".local" / "share" / "shishya"
    return ROOT


DATA = _data_root()
SHARED = DATA / "shared"
VAR = DATA / "var"
INSTALLED = (ROOT / "INSTALLED").exists()

# What a fresh install starts with. Only the seed: the catalogue every other
# part of the shop is demonstrated against, and the demo files. Never the
# training folder of the machine the build was made on — that is somebody's
# real purchase history, and the README already says it must not travel.
SEED = ROOT / "seed"


def ensure():
    """Make the data folders, and stock a first run from the seed."""
    for d in (SHARED, VAR, SHARED / "inbox", SHARED / "work", SHARED / "training",
              SHARED / "traces", SHARED / "jobs", SHARED / "billing", SHARED / "lessons"):
        d.mkdir(parents=True, exist_ok=True)
    if SEED.is_dir():
        import shutil
        for src in SEED.rglob("*"):
            if src.is_file():
                dst = SHARED / src.relative_to(SEED)
                if not dst.exists():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
    return DATA
