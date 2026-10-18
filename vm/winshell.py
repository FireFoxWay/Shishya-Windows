#!/usr/bin/env python3
"""
The panel's terminal, inside the Windows sandbox. Runs INSIDE the AppContainer.

    python winshell.py "dir work"

On the Mac a command ran in bash as the clone. In a Windows AppContainer the
native shells are hobbled — measured: cmd's built-in `dir` answers "Access is
denied" on every pattern (it asks about the volume, which a container may not
see), and PowerShell refuses to start at all. A terminal whose first command
fails is not a terminal, so the everyday ones are answered here, in Python,
with exactly the reach the sandbox has; anything else goes to cmd.exe as it
would have.

Same honesty as before: not a real terminal, no session that survives to the
next command — `cd` says where you would be and changes nothing.
"""

import fnmatch
import getpass
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path


def human(n):
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def where(arg):
    return Path(os.path.expandvars(os.path.expanduser(arg))) if arg else Path.cwd()


def listing(args):
    flags = {a.lower() for a in args if a.startswith(("/", "-"))}
    rest = [a for a in args if not a.startswith(("/", "-"))]
    target = where(rest[0] if rest else "")
    pattern = "*"
    if not target.exists() and any(ch in target.name for ch in "*?"):
        target, pattern = target.parent, target.name
    if target.is_file():
        items = [target]
    else:
        items = sorted((p for p in target.iterdir() if fnmatch.fnmatch(p.name.lower(), pattern.lower())),
                       key=lambda p: (not p.is_dir(), p.name.lower()))
    bare = "/b" in flags or "-1" in flags
    if not bare:
        print(f" Directory of {target}\n")
    for p in items:
        if bare:
            print(p.name)
            continue
        st = p.stat()
        when = time.strftime("%d-%m-%Y  %H:%M", time.localtime(st.st_mtime))
        print(f"{when}    {'<DIR>' if p.is_dir() else human(st.st_size):>9}  {p.name}")
    if not bare:
        print(f"\n{sum(1 for p in items if p.is_file())} file(s), "
              f"{sum(1 for p in items if p.is_dir())} folder(s)")


def show(args):
    for a in args:
        sys.stdout.write(where(a).read_text(encoding="utf-8", errors="replace"))
        sys.stdout.write("\n")


def main(line):
    line = line.strip()
    if not line:
        return 0
    try:
        words = shlex.split(line, posix=False)
    except ValueError:
        words = line.split()
    head, args = words[0].lower(), [w.strip('"') for w in words[1:]]
    if head in ("dir", "ls"):
        listing(args)
    elif head in ("type", "cat"):
        show(args)
    elif head in ("cd", "pwd", "chdir"):
        print(where(args[0]).resolve() if args and head != "pwd" else Path.cwd())
        if args and head != "pwd":
            print("(each command starts fresh — use the full path in the next one)")
    elif head == "whoami":
        print(f"{getpass.getuser()} — inside the clone's sandbox")
    elif head == "where":
        import shutil
        for a in args:
            print(shutil.which(a) or f"INFO: no {a} on the sandbox's PATH")
    elif head in ("python", "python3", "py"):
        # The rest of the line exactly as typed: Windows parses a command
        # line's quoting itself, and re-splitting it here mangled -c "...".
        rest = line[len(words[0]):]
        return subprocess.run(f'"{sys.executable}"{rest}').returncode
    else:
        return subprocess.run(f'cmd.exe /d /s /c "{line}"').returncode
    return 0


if __name__ == "__main__":
    os.chdir(Path.home())
    try:
        sys.exit(main(" ".join(sys.argv[1:])))
    except OSError as e:
        print(f"{type(e).__name__}: {e}")
        sys.exit(1)
