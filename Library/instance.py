import contextlib
import ctypes
import os
import signal
import subprocess
import tempfile

from . import windows

pid_path = os.path.join(tempfile.gettempdir(), "wallpaper_changer.pid")

if windows:
    import ctypes.wintypes as wt

    process_query_limited_information = 0x1000
    still_active = 259

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wt.HANDLE
    kernel32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
    kernel32.GetExitCodeProcess.argtypes = [wt.HANDLE, ctypes.POINTER(wt.DWORD)]
    kernel32.CloseHandle.argtypes = [wt.HANDLE]


def process_start_time(pid):
    # Empty when no such process is running.
    if not windows:
        return subprocess.run(["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return ""
    # A process that already exited can still be opened while anything (a debugger, an IDE) holds a handle to it.
    exit_code = wt.DWORD()
    kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
    times = [wt.FILETIME() for _ in range(4)]
    kernel32.GetProcessTimes(handle, *map(ctypes.byref, times))
    kernel32.CloseHandle(handle)
    if exit_code.value != still_active:
        return ""
    return str(times[0].dwHighDateTime << 32 | times[0].dwLowDateTime)


def kill_previous_instance():
    # The pid file stores pid + start time, so a reused pid never kills an unrelated process.
    try:
        with open(pid_path) as f:
            old_pid, old_start = f.read().split(maxsplit=1)
        old_pid = int(old_pid)
    except (OSError, ValueError):
        old_pid = None
    if old_pid and old_pid != os.getpid() and process_start_time(old_pid) == old_start.strip():
        # It may exit on its own in between, or run as administrator, which a normal process can't stop.
        with contextlib.suppress(OSError):
            os.kill(old_pid, signal.SIGTERM)
    with open(pid_path, "w") as f:
        f.write(f"{os.getpid()} {process_start_time(os.getpid())}")
