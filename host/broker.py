#!/usr/bin/env python3
"""
Shishya — the one thing that crosses into the sandbox: the model.

On the Mac the egress lock was nftables with one hole punched in it: the
host's Ollama at 192.168.5.2:11434. On Windows the AppContainer has no
network at all — not even loopback, which Windows refuses to AppContainers
unless an administrator exempts them, and an exemption would open every
port on localhost rather than one.

So the hole is a named pipe instead. Its ACL names the clone's container SID
and nobody else's, and on the far side of it is this broker, which forwards a
short list of Ollama endpoints and nothing more. The clone can ask the model
a question; it cannot ask the broker to fetch a URL, because there is no code
here that would.

    \\\\.\\pipe\\shishya-model

One request per connection: a line of JSON, then the reply streamed back
until the pipe closes.

    → {"method": "POST", "path": "/api/generate", "body": {...}}\\n
    ← HTTP status line, then the response body, then EOF

Standard library only.
"""

import ctypes
import json
import threading
import time
import urllib.error
import urllib.request
from ctypes import wintypes

PIPE = r"\\.\pipe\shishya-model"
OLLAMA = "http://127.0.0.1:11434"

# What the clone may ask for. Read-only questions about the model and the
# three ways of asking it something. Pulling and deleting models is the
# owner's business and happens in the panel, outside the sandbox.
ALLOWED = {
    ("POST", "/api/generate"), ("POST", "/api/chat"),
    ("POST", "/api/embeddings"), ("POST", "/api/embed"),
    ("POST", "/api/show"), ("GET", "/api/tags"), ("GET", "/api/ps"),
    ("GET", "/api/version"),
}

# Adding and removing models: allowed only while the person at the machine
# is working as the head, and every one goes in the ledger. A download is a
# decision somebody makes on purpose, never one the sandbox makes for itself.
MANAGE = {("POST", "/api/pull"), ("DELETE", "/api/delete")}

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

PIPE_ACCESS_DUPLEX = 0x00000003
PIPE_TYPE_BYTE = 0x00000000
PIPE_READMODE_BYTE = 0x00000000
PIPE_WAIT = 0x00000000
PIPE_REJECT_REMOTE_CLIENTS = 0x00000008
PIPE_UNLIMITED_INSTANCES = 255
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value
ERROR_PIPE_CONNECTED = 535


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p),
                ("bInheritHandle", wintypes.BOOL)]


kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
kernel32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                      wintypes.DWORD, ctypes.POINTER(SECURITY_ATTRIBUTES)]
kernel32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
kernel32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                              ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
kernel32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p),
    ctypes.POINTER(wintypes.ULONG)]


def _security(container_sid):
    """Who may open the pipe: this user, SYSTEM, and the clone's container.

    The S: part is the integrity label. AppContainer tokens are low
    integrity, and an object with no label is treated as medium — which a
    low process may not write to. NW;;;LW says low may write here, and it is
    on this object only.
    """
    sddl = (f"D:P(A;;GA;;;SY)(A;;GA;;;OW)(A;;GRGW;;;{container_sid})"
            f"S:(ML;;NW;;;LW)")
    sd = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
            sddl, 1, ctypes.byref(sd), None):
        raise OSError(ctypes.get_last_error(), "bad pipe security descriptor")
    sa = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), sd, False)
    return sa, sd


def _read_line(h, limit=4 * 1024 * 1024):
    data = bytearray()
    buf = ctypes.create_string_buffer(65536)
    got = wintypes.DWORD()
    while b"\n" not in data:
        if not kernel32.ReadFile(h, buf, len(buf), ctypes.byref(got), None) or not got.value:
            break
        data += buf.raw[:got.value]
        if len(data) > limit:
            raise ValueError("request too large")
    return bytes(data.split(b"\n", 1)[0])


def _write(h, data):
    done = wintypes.DWORD()
    view = memoryview(data)
    while view:
        if not kernel32.WriteFile(h, bytes(view[:65536]), min(len(view), 65536),
                                  ctypes.byref(done), None):
            return False
        view = view[done.value:]
    return True


class Broker:
    def __init__(self, container_sid, ollama=OLLAMA, on_request=None, may_manage=None):
        self.sid = container_sid
        self.ollama = ollama
        self.on_request = on_request
        self.may_manage = may_manage or (lambda: False)
        self.served = 0
        self.refused = 0
        self.last = None
        self._stop = False

    def _serve_one(self, h):
        try:
            try:
                req = json.loads(_read_line(h) or b"{}")
            except ValueError:
                req = {}
            method = str(req.get("method", "POST")).upper()
            path = str(req.get("path", ""))
            manage = (method, path) in MANAGE
            if (method, path) not in ALLOWED and not (manage and self.may_manage()):
                self.refused += 1
                why = ("only the head adds or removes models — switch to head on the panel"
                       if manage else f"{path} is not something the sandbox may ask for")
                _write(h, f"403 {why}\n".encode())
                if self.on_request:
                    self.on_request(False, method, path)
                return
            if manage and self.on_request:
                self.on_request(True, method, f"{path} {(req.get('body') or {}).get('name', '')}")
            body = req.get("body")
            data = json.dumps(body).encode() if body is not None else None
            r = urllib.request.Request(self.ollama + path, data=data, method=method,
                                       headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(r, timeout=1800) as resp:
                    _write(h, f"{resp.status} OK\n".encode())
                    while True:
                        chunk = resp.read1(65536) if hasattr(resp, "read1") else resp.read(65536)
                        if not chunk:
                            break
                        if not _write(h, chunk):
                            break
            except urllib.error.HTTPError as e:
                _write(h, f"{e.code} {e.reason}\n".encode() + (e.read() or b""))
            except (urllib.error.URLError, OSError) as e:
                _write(h, f"502 the model on this machine is not answering ({e})\n".encode())
            self.served += 1
            self.last = time.time()
            if self.on_request:
                self.on_request(True, method, path)
        finally:
            kernel32.FlushFileBuffers(h)
            kernel32.DisconnectNamedPipe(h)
            kernel32.CloseHandle(h)

    def serve_forever(self):
        sa, sd = _security(self.sid)
        try:
            while not self._stop:
                h = kernel32.CreateNamedPipeW(
                    PIPE, PIPE_ACCESS_DUPLEX,
                    PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
                    PIPE_UNLIMITED_INSTANCES, 65536, 65536, 0, ctypes.byref(sa))
                if h == INVALID_HANDLE_VALUE:
                    time.sleep(1)
                    continue
                ok = kernel32.ConnectNamedPipe(h, None)
                if not ok and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
                    kernel32.CloseHandle(h)
                    continue
                threading.Thread(target=self._serve_one, args=(h,), daemon=True).start()
        finally:
            kernel32.LocalFree(sd)

    def start(self):
        threading.Thread(target=self.serve_forever, daemon=True, name="model-broker").start()
        return self

    def state(self):
        return {"pipe": PIPE, "served": self.served, "refused": self.refused,
                "last": self.last}


# ─── the client side, used from inside the sandbox ──────────────────────────

def request(method, path, body=None, timeout=1800):
    """Ask the model through the pipe. Returns (status, bytes).

    Plain file I/O on the pipe's name: that is all a client needs, and it
    keeps this importable from the clone's apps with nothing but the stdlib.
    """
    deadline = time.time() + 10
    while True:
        try:
            pipe = open(PIPE, "r+b", buffering=0)
            break
        except FileNotFoundError:
            raise ConnectionError("the model pipe is not there — is the panel running?")
        except OSError:
            # ERROR_PIPE_BUSY: every instance is mid-answer. The broker makes a
            # new one as soon as it accepts, so this is a moment, not a fault.
            if time.time() > deadline:
                raise ConnectionError("the model pipe is busy")
            time.sleep(0.1)
    with pipe:
        pipe.write(json.dumps({"method": method, "path": path, "body": body}).encode() + b"\n")
        data = bytearray()
        while True:
            try:
                chunk = pipe.read(65536)
            except OSError:
                break                     # broken pipe: the broker closed, done
            if not chunk:
                break
            data += chunk
    head, _, rest = bytes(data).partition(b"\n")
    try:
        status = int(head.split(b" ", 1)[0])
    except ValueError:
        status = 502
    return status, rest
