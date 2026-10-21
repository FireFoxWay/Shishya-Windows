#!/usr/bin/env python3
"""
Shishya — the clone's sandbox on Windows, made of the operating system's own
parts rather than a virtual machine.

On a Mac the clone lives in a Lima VM. Windows 11 Home has no Hyper-V and no
Windows Sandbox, and a VM was never the point anyway — the point is three
properties, and Windows can give all three to an ordinary process:

  1. It cannot read what it was not given.
     An AppContainer. Every file and folder on the machine refuses its token
     unless that object's ACL names the container's SID. The mount list
     becomes the grant list: shared/ and the runtime are granted, your
     Documents folder is not — not because we check a path somewhere, but
     because the kernel's access check says no.

  2. It cannot reach the network unless you say so.
     An AppContainer with no network capabilities has no network. Not a
     firewall rule that could be lifted from inside: the capability is in the
     token at creation and a process cannot add one to itself. Browsing means
     starting the browser with `internetClient`; locked means nothing has it.
     And the state is MEASURED by reading the capabilities of every live
     process in the container, never remembered.

  3. It cannot put its hands on your windows.
     An AppContainer token runs at low integrity. User Interface Privilege
     Isolation stops a low-integrity process from sending input to, or
     driving through UI Automation, a window owned by anything higher. The
     clone's executor can type into the clone's spreadsheet and physically
     cannot type into yours.

Everything the clone runs goes into one Job Object, so "stop the sandbox" is
one call that cannot miss a straggler, and the memory cap is the job's.

Standard library only: ctypes over kernel32, advapi32 and userenv.
"""

import ctypes
import os
import subprocess
import sys
from ctypes import wintypes
from pathlib import Path

if sys.platform != "win32":                       # pragma: no cover
    raise ImportError("winbox is the Windows sandbox; on macOS use host/vm.py")

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
userenv = ctypes.WinDLL("userenv", use_last_error=True)

# Real pixels. A process that has not said it understands display scaling is
# lied to by Windows about every window's size and position — on a 200%
# screen the clone's 1440x900 reads as 720x450, the screen picture comes back
# as its top-left quarter, and a click lands in the wrong place. Declared here
# because every host module that touches the clone's windows imports this
# first. Harmless if the process already declared something.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))   # PER_MONITOR_V2
except (AttributeError, OSError):
    pass

CONTAINER = "Shishya.Clone"
DISPLAY = "Shishya — the clone"

# Well-known capability SIDs. Named here so the code says which hole it is
# opening instead of carrying an opaque string.
CAPABILITIES = {
    "internetClient":              "S-1-15-3-1",
    "internetClientServer":        "S-1-15-3-2",
    "privateNetworkClientServer":  "S-1-15-3-3",
}

# ─── Win32 plumbing ─────────────────────────────────────────────────────────

PSID = ctypes.c_void_p
HRESULT = ctypes.c_long
SE_GROUP_ENABLED = 0x00000004
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_SUSPENDED = 0x00000004
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES = 0x00020009
PROC_THREAD_ATTRIBUTE_HANDLE_LIST = 0x00020002
STARTF_USESTDHANDLES = 0x00000100
HANDLE_FLAG_INHERIT = 0x00000001
JobObjectBasicProcessIdList = 3
JobObjectExtendedLimitInformation = 9
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x00000200
JOB_OBJECT_LIMIT_BREAKAWAY_OK = 0x00000800
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TokenCapabilities = 30
TokenIsAppContainer = 29
TokenAppContainerSid = 31
HRESULT_ALREADY_EXISTS = ctypes.c_long(0x800700B7).value
INFINITE = 0xFFFFFFFF


class SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [("Sid", PSID), ("Attributes", wintypes.DWORD)]


class SECURITY_CAPABILITIES(ctypes.Structure):
    _fields_ = [("AppContainerSid", PSID),
                ("Capabilities", ctypes.POINTER(SID_AND_ATTRIBUTES)),
                ("CapabilityCount", wintypes.DWORD),
                ("Reserved", wintypes.DWORD)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR), ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD), ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD), ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD), ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD), ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.c_void_p), ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE), ("hStdError", wintypes.HANDLE)]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [("hProcess", wintypes.HANDLE), ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD), ("dwThreadId", wintypes.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(n, ctypes.c_ulonglong) for n in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong),
                ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


def _sig(fn, res, *args):
    fn.restype, fn.argtypes = res, list(args)
    return fn


_sig(userenv.CreateAppContainerProfile, HRESULT, wintypes.LPCWSTR, wintypes.LPCWSTR,
     wintypes.LPCWSTR, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(PSID))
_sig(userenv.DeriveAppContainerSidFromAppContainerName, HRESULT, wintypes.LPCWSTR,
     ctypes.POINTER(PSID))
_sig(userenv.DeleteAppContainerProfile, HRESULT, wintypes.LPCWSTR)
_sig(userenv.GetAppContainerFolderPath, HRESULT, wintypes.LPCWSTR,
     ctypes.POINTER(wintypes.LPWSTR))
_sig(advapi32.ConvertSidToStringSidW, wintypes.BOOL, PSID, ctypes.POINTER(wintypes.LPWSTR))
_sig(advapi32.ConvertStringSidToSidW, wintypes.BOOL, wintypes.LPCWSTR, ctypes.POINTER(PSID))
_sig(advapi32.FreeSid, ctypes.c_void_p, PSID)
_sig(advapi32.OpenProcessToken, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
     ctypes.POINTER(wintypes.HANDLE))
_sig(advapi32.GetTokenInformation, wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
_sig(advapi32.EqualSid, wintypes.BOOL, PSID, PSID)
_sig(kernel32.LocalFree, ctypes.c_void_p, ctypes.c_void_p)
_sig(kernel32.InitializeProcThreadAttributeList, wintypes.BOOL, ctypes.c_void_p,
     wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.c_size_t))
_sig(kernel32.UpdateProcThreadAttribute, wintypes.BOOL, ctypes.c_void_p, wintypes.DWORD,
     ctypes.c_size_t, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_void_p, ctypes.c_void_p)
_sig(kernel32.DeleteProcThreadAttributeList, None, ctypes.c_void_p)
_sig(kernel32.CreateProcessW, wintypes.BOOL, wintypes.LPCWSTR, wintypes.LPWSTR,
     ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL, wintypes.DWORD, ctypes.c_void_p,
     wintypes.LPCWSTR, ctypes.POINTER(STARTUPINFOEXW), ctypes.POINTER(PROCESS_INFORMATION))
_sig(kernel32.ResumeThread, wintypes.DWORD, wintypes.HANDLE)
_sig(kernel32.CloseHandle, wintypes.BOOL, wintypes.HANDLE)
_sig(kernel32.CreateJobObjectW, wintypes.HANDLE, ctypes.c_void_p, wintypes.LPCWSTR)
_sig(kernel32.OpenJobObjectW, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR)
_sig(kernel32.AssignProcessToJobObject, wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
_sig(kernel32.SetInformationJobObject, wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
     ctypes.c_void_p, wintypes.DWORD)
_sig(kernel32.QueryInformationJobObject, wintypes.BOOL, wintypes.HANDLE, ctypes.c_int,
     ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD))
_sig(kernel32.TerminateJobObject, wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_sig(kernel32.OpenProcess, wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
_sig(kernel32.SetHandleInformation, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
     wintypes.DWORD)
_sig(kernel32.WaitForSingleObject, wintypes.DWORD, wintypes.HANDLE, wintypes.DWORD)
_sig(kernel32.GetExitCodeProcess, wintypes.BOOL, wintypes.HANDLE,
     ctypes.POINTER(wintypes.DWORD))
_sig(kernel32.TerminateProcess, wintypes.BOOL, wintypes.HANDLE, wintypes.UINT)
_sig(kernel32.QueryFullProcessImageNameW, wintypes.BOOL, wintypes.HANDLE, wintypes.DWORD,
     wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD))


class SandboxError(RuntimeError):
    pass


def _check(ok, what):
    if not ok:
        err = ctypes.get_last_error()
        raise SandboxError(f"{what} failed: {ctypes.FormatError(err).strip()} ({err})")


# ─── the container ──────────────────────────────────────────────────────────

def _sid_string(psid):
    out = wintypes.LPWSTR()
    _check(advapi32.ConvertSidToStringSidW(psid, ctypes.byref(out)), "ConvertSidToStringSid")
    try:
        return out.value
    finally:
        kernel32.LocalFree(out)


def _sid_from_string(text):
    psid = PSID()
    _check(advapi32.ConvertStringSidToSidW(text, ctypes.byref(psid)), "ConvertStringSidToSid")
    return psid          # LocalFree when done; kept alive by callers for a launch


def ensure_container():
    """Create the AppContainer profile if it is not there. Returns its SID.

    No administrator rights: an AppContainer profile is per-user, which is
    the right scope — the clone belongs to whoever is signed in.
    """
    psid = PSID()
    hr = userenv.CreateAppContainerProfile(CONTAINER, DISPLAY,
                                           "The clone's sandbox. Delete to reset it.",
                                           None, 0, ctypes.byref(psid))
    if hr == HRESULT_ALREADY_EXISTS:
        hr = userenv.DeriveAppContainerSidFromAppContainerName(CONTAINER, ctypes.byref(psid))
    if hr != 0:
        raise SandboxError(f"could not create the AppContainer (HRESULT {hr & 0xFFFFFFFF:#x})")
    try:
        return _sid_string(psid)
    finally:
        advapi32.FreeSid(psid)


def container_sid():
    return ensure_container()


def container_home():
    """The container's own storage — %LOCALAPPDATA%\\Packages\\<name>\\AC.

    The one place on disk an AppContainer can write without being granted
    anything. It is the clone's home directory, and it is what a snapshot
    saves and a rollback restores, the way the VM's disk image was.
    """
    ensure_container()
    sid = container_sid()
    out = wintypes.LPWSTR()
    hr = userenv.GetAppContainerFolderPath(sid, ctypes.byref(out))
    if hr != 0:
        raise SandboxError(f"GetAppContainerFolderPath failed ({hr & 0xFFFFFFFF:#x})")
    try:
        return Path(out.value)
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


def delete_container():
    """Forget the container entirely. Its storage goes with it."""
    stop_all()
    userenv.DeleteAppContainerProfile(CONTAINER)


# ─── the grant list (what the mount list was) ───────────────────────────────

def grant(path, write=False):
    """Let the container see one folder, and everything under it.

    icacls rather than SetNamedSecurityInfo by hand: it merges with the
    existing ACL and propagates to children correctly, which is three hundred
    lines of ctypes to get exactly right and one well-tested program to call.
    No elevation needed — the user owns these folders.
    """
    sid = container_sid()
    rights = "(OI)(CI)M" if write else "(OI)(CI)RX"
    # No /T: an inheritable grant on the folder propagates to everything
    # under it by itself. /T would also stamp it on every one of the
    # runtime's ten thousand files explicitly, for the same result, slowly.
    p = subprocess.run(["icacls", str(path), "/grant", f"*{sid}:{rights}", "/C", "/Q"],
                       capture_output=True, text=True, encoding="oem", errors="replace", creationflags=CREATE_NO_WINDOW)
    if p.returncode != 0:
        raise SandboxError(f"could not grant {path}: {(p.stderr or p.stdout).strip()}")
    return {"path": str(path), "write": write}


def revoke(path):
    sid = container_sid()
    subprocess.run(["icacls", str(path), "/remove:g", f"*{sid}", "/T", "/C", "/Q"],
                   capture_output=True, text=True, encoding="oem", errors="replace", creationflags=CREATE_NO_WINDOW)
    return {"path": str(path), "revoked": True}


def granted(path):
    """Does the container's SID appear on this folder's ACL? Read from the
    ACL itself, so the grant list shown in the panel is the real one."""
    sid = container_sid()
    p = subprocess.run(["icacls", str(path)], capture_output=True, text=True, encoding="oem", errors="replace",
                       creationflags=CREATE_NO_WINDOW)
    text = p.stdout or ""
    if sid in text:
        return "write" if f"{sid}:(OI)(CI)(M)" in text or f"{sid}:(I)(OI)(CI)(M)" in text \
            or "(M)" in text.split(sid, 1)[1].splitlines()[0] else "read"
    return None


# ─── the job: everything the clone runs ─────────────────────────────────────

JOB_NAME = "Local\\Shishya.Clone.Job"
MEMORY_CAP = 8 * 1024 ** 3        # what the VM was given; the same ceiling here
_job = None


def _the_job():
    """One job for the life of this panel. KILL_ON_JOB_CLOSE: if the panel
    dies, the clone dies with it rather than running on unwatched."""
    global _job
    if _job:
        return _job
    job = kernel32.CreateJobObjectW(None, JOB_NAME)
    _check(job, "CreateJobObject")
    _job = job
    _apply_limits()
    return job


# ─── the sandbox's share of the machine ─────────────────────────────────────
# On the Mac this was cpus: and memory: in lima.yaml, fixed when the VM was
# made. A job object can be re-limited while it runs, so on Windows the dock's
# dials change it live: a hard cap on processor time, and a ceiling on the
# memory every clone process together may commit. A process that asks for
# more than the ceiling is refused the allocation — the sandbox slows or an
# app fails, and the rest of the laptop does not.

JobObjectCpuRateControlInformation = 15
JOB_OBJECT_CPU_RATE_CONTROL_ENABLE = 0x1
JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP = 0x4


class JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


LIMITS = {"cpu": 100, "ram": MEMORY_CAP // 1024 ** 3}


def set_limits(cpu=None, ram=None):
    """cpu: percent of the whole machine, 10–100. ram: gigabytes, 2 upward.
    Remembered, and applied to the job now if it exists."""
    if cpu is not None:
        LIMITS["cpu"] = max(10, min(100, int(cpu)))
    if ram is not None:
        LIMITS["ram"] = max(2, min(machine_memory_gb(), int(ram)))
    _apply_limits()
    return dict(LIMITS)


def _apply_limits():
    if not _job:
        return
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                                             | JOB_OBJECT_LIMIT_JOB_MEMORY)
    info.JobMemoryLimit = LIMITS["ram"] * 1024 ** 3
    _check(kernel32.SetInformationJobObject(_job, JobObjectExtendedLimitInformation,
                                            ctypes.byref(info), ctypes.sizeof(info)),
           "SetInformationJobObject(memory)")
    rate = JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
    if LIMITS["cpu"] >= 100:
        rate.ControlFlags = 0                          # no cap at all
    else:
        rate.ControlFlags = JOB_OBJECT_CPU_RATE_CONTROL_ENABLE | JOB_OBJECT_CPU_RATE_CONTROL_HARD_CAP
        rate.CpuRate = LIMITS["cpu"] * 100             # hundredths of a percent
    kernel32.SetInformationJobObject(_job, JobObjectCpuRateControlInformation,
                                     ctypes.byref(rate), ctypes.sizeof(rate))


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def machine_memory_gb():
    m = MEMORYSTATUSEX()
    m.dwLength = ctypes.sizeof(m)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
    return max(2, round(m.ullTotalPhys / 1024 ** 3))


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + \
               [(n, ctypes.c_size_t) for n in (
                   "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                   "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                   "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage",
                   "PrivateUsage")]


def memory_used(pids=None):
    """Bytes the clone's processes have committed — what the RAM limit caps."""
    total = 0
    for pid in (pids if pids is not None else container_pids()):
        h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not h:
            continue
        try:
            c = PROCESS_MEMORY_COUNTERS_EX()
            c.cb = ctypes.sizeof(c)
            if ctypes.windll.psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                total += c.PrivateUsage
        finally:
            kernel32.CloseHandle(h)
    return total


def job_pids():
    if not _job:
        return []

    class LIST(ctypes.Structure):
        _fields_ = [("Assigned", wintypes.DWORD), ("InList", wintypes.DWORD),
                    ("Ids", ctypes.c_size_t * 512)]
    found = LIST()
    if not kernel32.QueryInformationJobObject(_job, JobObjectBasicProcessIdList,
                                              ctypes.byref(found), ctypes.sizeof(found), None):
        return []
    return [int(found.Ids[i]) for i in range(found.InList)]


def stop_all():
    """Everything the clone is running, ended. One call, nothing missed."""
    if _job:
        kernel32.TerminateJobObject(_job, 1)
    # Anything that slipped the job (a panel restart orphaned it) is still in
    # the container, and the container is what defines "the clone".
    for pid in container_pids():
        h = kernel32.OpenProcess(0x0001, False, pid)       # PROCESS_TERMINATE
        if h:
            kernel32.TerminateProcess(h, 1)
            kernel32.CloseHandle(h)
    return {"stopped": True}


# ─── launching ──────────────────────────────────────────────────────────────

class Proc:
    """A handle on one process started inside the container. Enough of the
    subprocess.Popen shape that callers do not care which one they hold."""

    def __init__(self, pi, stdout=None):
        self.pid = pi.dwProcessId
        self._h = pi.hProcess
        self.stdout = stdout
        self.returncode = None

    def poll(self):
        if self.returncode is None:
            code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(self._h, ctypes.byref(code)) and code.value != 259:
                self.returncode = code.value
        return self.returncode

    def wait(self, timeout=None):
        ms = INFINITE if timeout is None else int(timeout * 1000)
        if kernel32.WaitForSingleObject(self._h, ms) != 0:
            raise subprocess.TimeoutExpired("sandboxed process", timeout)
        return self.poll()

    def terminate(self):
        kernel32.TerminateProcess(self._h, 0xFFFFFFF1)     # -15, as SIGTERM was
        self.returncode = -15

    kill = terminate

    def __del__(self):
        try:
            kernel32.CloseHandle(self._h)
        except Exception:
            pass


def _env_block(env):
    text = "".join(f"{k}={v}\0" for k, v in sorted(env.items(), key=lambda kv: kv[0].upper()))
    return ctypes.create_unicode_buffer(text + "\0")


# What a sandboxed process inherits from this one: the variables Windows
# itself needs to run a program, and nothing else. The panel's own
# environment can hold anything — an API token someone exported, a path into
# their home directory — and the sandbox has no business reading it. What the
# clone needs on top of this, the caller says by name.
SYSTEM_ENV = ("SystemRoot", "SystemDrive", "windir", "ComSpec", "PATHEXT",
              "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
              "PROCESSOR_LEVEL", "PROCESSOR_REVISION", "OS", "ProgramData",
              "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432",
              "CommonProgramFiles", "CommonProgramFiles(x86)", "CommonProgramW6432",
              # Windows rewrites these for an AppContainer to point into the
              # container's own storage, and refuses to start the process
              # (ERROR_ENVVAR_NOT_FOUND) when they are missing to rewrite.
              "LOCALAPPDATA", "APPDATA", "USERPROFILE", "TEMP", "TMP",
              "USERNAME", "USERDOMAIN", "COMPUTERNAME", "ALLUSERSPROFILE", "PUBLIC")


def base_env():
    out = {k: os.environ[k] for k in SYSTEM_ENV if k in os.environ}
    root = os.environ.get("SystemRoot", r"C:\Windows")
    out["PATH"] = f"{root}\\System32;{root};{root}\\System32\\Wbem"
    return out


def _cmdline(argv):
    """A list is quoted for the C runtime's rules; a string is passed as it
    is — cmd.exe /s /c has rules of its own and needs the line verbatim."""
    if isinstance(argv, str):
        return argv
    return subprocess.list2cmdline([str(a) for a in argv])


def launch(argv, caps=(), cwd=None, env=None, capture=False, window=True):
    """Start one program inside the container, in the clone's job.

    caps names network capabilities — empty is the egress lock, and it is
    the default, so forgetting to say means no network rather than all of it.

    capture=True wires stdout+stderr to a pipe (for runners whose output the
    panel streams). The pipe is passed with an explicit handle list, so the
    child inherits that one handle and nothing else this process holds.
    """
    for c in caps:
        if c not in CAPABILITIES:
            raise SandboxError(f"unknown capability {c!r}")

    sid = _sid_from_string(container_sid())
    cap_sids = [_sid_from_string(CAPABILITIES[c]) for c in caps]
    cap_arr = (SID_AND_ATTRIBUTES * max(1, len(cap_sids)))()
    for i, s in enumerate(cap_sids):
        cap_arr[i].Sid, cap_arr[i].Attributes = s, SE_GROUP_ENABLED
    sc = SECURITY_CAPABILITIES(sid, cap_arr if cap_sids else None, len(cap_sids), 0)

    n_attrs = 2 if capture else 1
    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, n_attrs, 0, ctypes.byref(size))
    attrs = ctypes.create_string_buffer(size.value)
    _check(kernel32.InitializeProcThreadAttributeList(attrs, n_attrs, 0, ctypes.byref(size)),
           "InitializeProcThreadAttributeList")
    _check(kernel32.UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES,
                                              ctypes.byref(sc), ctypes.sizeof(sc), None, None),
           "UpdateProcThreadAttribute(security capabilities)")

    si = STARTUPINFOEXW()
    si.StartupInfo.cb = ctypes.sizeof(si)
    si.lpAttributeList = ctypes.addressof(attrs)

    reader = None
    handles = None
    if capture:
        import msvcrt
        r, w = os.pipe()
        hw = msvcrt.get_osfhandle(w)
        kernel32.SetHandleInformation(hw, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
        nul = open(os.devnull, "rb")
        hin = msvcrt.get_osfhandle(nul.fileno())
        kernel32.SetHandleInformation(hin, HANDLE_FLAG_INHERIT, HANDLE_FLAG_INHERIT)
        handles = (wintypes.HANDLE * 2)(hw, hin)
        _check(kernel32.UpdateProcThreadAttribute(attrs, 0, PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                                                  handles, ctypes.sizeof(handles), None, None),
               "UpdateProcThreadAttribute(handle list)")
        si.StartupInfo.dwFlags |= STARTF_USESTDHANDLES
        si.StartupInfo.hStdInput = hin
        si.StartupInfo.hStdOutput = hw
        si.StartupInfo.hStdError = hw

    merged = base_env()
    merged.update(env or {})
    block = _env_block(merged)
    flags = (EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT
             | (0 if window else CREATE_NO_WINDOW))
    pi = PROCESS_INFORMATION()
    cmd = ctypes.create_unicode_buffer(_cmdline(argv))
    try:
        ok = kernel32.CreateProcessW(None, cmd, None, None, bool(capture), flags, block,
                                     str(cwd) if cwd else None, ctypes.byref(si),
                                     ctypes.byref(pi))
        first = argv.split()[0] if isinstance(argv, str) else str(argv[0])
        _check(ok, f"starting {Path(first).name} in the sandbox")
        # Into the job BEFORE it runs a single instruction, so there is no
        # moment in which it exists outside "the clone".
        _check(kernel32.AssignProcessToJobObject(_the_job(), pi.hProcess),
               "AssignProcessToJobObject")
        kernel32.ResumeThread(pi.hThread)
        kernel32.CloseHandle(pi.hThread)
    finally:
        kernel32.DeleteProcThreadAttributeList(attrs)
        kernel32.LocalFree(sid)
        for s in cap_sids:
            kernel32.LocalFree(s)
        if capture:
            os.close(w)
            nul.close()

    if capture:
        reader = open(r, "r", encoding="utf-8", errors="replace", newline=None)
    return Proc(pi, reader)


def run(argv, caps=(), cwd=None, env=None, timeout=120):
    """launch() and collect, the shape of subprocess.run."""
    proc = launch(argv, caps=caps, cwd=cwd, env=env, capture=True, window=False)
    out = []
    import threading
    t = threading.Thread(target=lambda: out.append(proc.stdout.read()), daemon=True)
    t.start()
    try:
        code = proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        raise
    t.join(5)
    return {"code": code, "out": "".join(out)}


# ─── measuring — never remembering ──────────────────────────────────────────

def _token_info(pid, klass):
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return None
    tok = wintypes.HANDLE()
    try:
        if not advapi32.OpenProcessToken(h, TOKEN_QUERY, ctypes.byref(tok)):
            return None
        need = wintypes.DWORD()
        advapi32.GetTokenInformation(tok, klass, None, 0, ctypes.byref(need))
        if not need.value:
            return None
        buf = ctypes.create_string_buffer(need.value)
        if not advapi32.GetTokenInformation(tok, klass, buf, need, ctypes.byref(need)):
            return None
        return buf
    finally:
        if tok:
            kernel32.CloseHandle(tok)
        kernel32.CloseHandle(h)


def in_container(pid):
    """Is this process the clone's? Asked of its token: the container SID."""
    buf = _token_info(pid, TokenAppContainerSid)
    if buf is None:
        return False
    psid = ctypes.cast(buf, ctypes.POINTER(PSID))[0]
    if not psid:
        return False
    try:
        if "sid" not in _SID_CACHE:
            _SID_CACHE["sid"] = container_sid()
        return _sid_string(psid) == _SID_CACHE["sid"]
    except SandboxError:
        return False


def capabilities_of(pid):
    """The network capabilities in this process's token, by name."""
    buf = _token_info(pid, TokenCapabilities)
    if buf is None:
        return None
    count = ctypes.cast(buf, ctypes.POINTER(wintypes.DWORD))[0]
    arr = ctypes.cast(ctypes.addressof(buf) + ctypes.sizeof(ctypes.c_void_p),
                      ctypes.POINTER(SID_AND_ATTRIBUTES))
    names = {v: k for k, v in CAPABILITIES.items()}
    found = []
    for i in range(count):
        try:
            s = _sid_string(arr[i].Sid)
        except SandboxError:
            continue
        found.append(names.get(s, s))
    return found


def all_pids():
    """Every process on the machine, from the toolhelp snapshot."""
    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(entry)
    out = []
    try:
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            out.append((entry.th32ProcessID, entry.szExeFile))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return out


kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]


_SID_CACHE = {}


def container_pids():
    """Every live process whose token carries the clone's container SID —
    whether or not this panel started it. The container is the clone.

    The container SID is computed once per run: deriving it is a userenv call
    and this is asked every few seconds."""
    if "sid" not in _SID_CACHE:
        _SID_CACHE["sid"] = container_sid()
    return [pid for pid, _ in all_pids() if pid > 4 and in_container(pid)]


class UNICODE_STRING(ctypes.Structure):
    _fields_ = [("Length", wintypes.USHORT), ("MaximumLength", wintypes.USHORT),
                ("Buffer", ctypes.c_void_p)]


ntdll = ctypes.WinDLL("ntdll")
ntdll.NtQueryInformationProcess.restype = ctypes.c_long
ntdll.NtQueryInformationProcess.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p,
                                            wintypes.ULONG, ctypes.POINTER(wintypes.ULONG)]
ProcessCommandLineInformation = 60


def command_line(pid):
    """The command line a process was started with, or "" — how "close the
    Billing app" finds the billing process among the clone's pythonw.exes."""
    h = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not h:
        return ""
    try:
        need = wintypes.ULONG()
        ntdll.NtQueryInformationProcess(h, ProcessCommandLineInformation, None, 0,
                                        ctypes.byref(need))
        if not need.value:
            return ""
        buf = ctypes.create_string_buffer(need.value)
        if ntdll.NtQueryInformationProcess(h, ProcessCommandLineInformation, buf,
                                           need, ctypes.byref(need)) != 0:
            return ""
        us = UNICODE_STRING.from_buffer(buf)
        return ctypes.wstring_at(us.Buffer, us.Length // 2) if us.Buffer else ""
    finally:
        kernel32.CloseHandle(h)


def terminate(pid):
    h = kernel32.OpenProcess(0x0001, False, pid)          # PROCESS_TERMINATE
    if not h:
        return False
    try:
        return bool(kernel32.TerminateProcess(h, 1))
    finally:
        kernel32.CloseHandle(h)


def processes():
    """What the clone is running right now, with what each may reach."""
    names = dict(all_pids())
    out = []
    for pid in container_pids():
        out.append({"pid": pid, "exe": names.get(pid, "?"),
                    "caps": capabilities_of(pid) or []})
    return out


def network_state():
    """The egress lock, measured from every live process in the container.

    Three answers, like the Mac's: None when nothing is running (there is no
    sandbox to be locked or open), True when no process holds a network
    capability, False — naming who — when one does.
    """
    procs = processes()
    if not procs:
        return {"locked": None, "detail": "the sandbox is not running", "holders": []}
    holders = [p for p in procs if p["caps"]]
    if not holders:
        return {"locked": True, "holders": [],
                "detail": f"no network capability in any of {len(procs)} sandboxed "
                          f"process(es) — only the model pipe crosses"}
    return {"locked": False, "holders": holders,
            "detail": "; ".join(f"{h['exe']} holds {', '.join(h['caps'])}" for h in holders)}


if __name__ == "__main__":
    import json
    fn = sys.argv[1] if len(sys.argv) > 1 else "processes"
    print(json.dumps(globals()[fn](*sys.argv[2:]), indent=2, default=str))
