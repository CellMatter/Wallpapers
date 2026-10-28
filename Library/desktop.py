import ctypes
import glob
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time

from . import macos, windows
from .config import config

# Every OS sets the wallpaper from a file, so the current one has to exist on disk; temp is enough for that.
data_dir = os.path.join(tempfile.gettempdir(), "wallpapers")

if windows:
    import ctypes.wintypes as wt

    spi_set_desk_wallpaper = 20
    spif_update_ini_file = 0x01
    spif_send_change = 0x02

    gwl_exstyle = -20
    ws_ex_transparent = 0x20
    ws_ex_toolwindow = 0x80
    dwmwa_cloaked = 14
    monitor_default_to_nearest = 2
    sm_cxscreen = 0
    sm_cyscreen = 1
    sm_cmonitors = 80

    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    # Otherwise display scaling makes Windows report a shrunken screen, and the wallpaper comes out blurry.
    user32.SetProcessDPIAware()

    user32.MonitorFromWindow.restype = wt.HMONITOR
    user32.MonitorFromWindow.argtypes = [wt.HWND, wt.DWORD]
    user32.GetWindowLongW.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetClassNameW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
    user32.IsWindowVisible.argtypes = [wt.HWND]
    user32.IsIconic.argtypes = [wt.HWND]
    dwmapi.DwmGetWindowAttribute.argtypes = [wt.HWND, wt.DWORD, ctypes.c_void_p, wt.DWORD]

    class MonitorInfo(ctypes.Structure):
        _fields_ = [("cbSize", wt.DWORD), ("rcMonitor", wt.RECT), ("rcWork", wt.RECT), ("dwFlags", wt.DWORD)]

    user32.GetMonitorInfoW.argtypes = [wt.HMONITOR, ctypes.POINTER(MonitorInfo)]
    enum_windows_proc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def macos_screen_size():
    report = json.loads(subprocess.run(["system_profiler", "-json", "SPDisplaysDataType"], capture_output=True, text=True).stdout)
    displays = [display for gpu in report["SPDisplaysDataType"] for display in gpu.get("spdisplays_ndrvs", [])]
    main_display = next((d for d in displays if d.get("spdisplays_main") == "spdisplays_yes"), displays[0])
    width, height = re.findall(r"\d+", main_display["_spdisplays_pixels"])[:2]
    return int(width), int(height)


def linux_screen_size():
    # Native resolution of each connected monitor, straight from the kernel, so it works on X11 and Wayland alike.
    sizes = []
    for status_path in glob.glob("/sys/class/drm/*/status"):
        with open(status_path) as status:
            if status.read().strip() != "connected":
                continue
        # The first mode listed is the monitor's preferred (native) one.
        with open(os.path.join(os.path.dirname(status_path), "modes")) as modes:
            match = re.match(r"(\d+)x(\d+)", modes.readline())
        if match:
            sizes.append((int(match[1]), int(match[2])))
    if not sizes and shutil.which("xrandr"):
        # Drivers without kernel modesetting (like NVIDIA's, by default) leave that empty; ask X instead.
        listing = subprocess.run(["xrandr", "--current"], capture_output=True, text=True).stdout
        sizes = [(int(w), int(h)) for w, h in re.findall(r" connected (?:primary )?(\d+)x(\d+)", listing)]
    if not sizes:
        sys.exit("Can't find the screen resolution.")
    # ponytail: the biggest monitor wins; the others get it scaled down.
    return max(sizes, key=lambda size: size[0] * size[1])


def screen_size():
    if windows:
        return user32.GetSystemMetrics(sm_cxscreen), user32.GetSystemMetrics(sm_cyscreen)
    return macos_screen_size() if macos else linux_screen_size()


def linux_wallpaper_commands(path):
    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    uri = pathlib.Path(path).as_uri()
    if "kde" in desktop:
        return [["plasma-apply-wallpaperimage", path]]
    if "xfce" in desktop:
        # One property per monitor and workspace.
        listed = subprocess.run(["xfconf-query", "-c", "xfce4-desktop", "-l"], capture_output=True, text=True).stdout
        return [["xfconf-query", "-c", "xfce4-desktop", "-p", p, "-s", path] for p in listed.split() if p.endswith("/last-image")]
    if "cinnamon" in desktop:
        return [["gsettings", "set", "org.cinnamon.desktop.background", "picture-uri", uri]]
    if "mate" in desktop:
        return [["gsettings", "set", "org.mate.background", "picture-filename", path]]
    if any(name in desktop for name in ("gnome", "unity", "pantheon", "budgie")):
        # GNOME 42+ keeps a separate picture for dark mode; older versions just reject that key.
        return [["gsettings", "set", "org.gnome.desktop.background", key, uri] for key in ("picture-uri", "picture-uri-dark")]
    sys.exit(f"Can't set the wallpaper on desktop {desktop!r}; set wallpaper_command in config.toml.")


def set_wallpaper(image):
    # A new file name every time: GNOME and macOS keep showing the old picture when the path stays the same.
    os.makedirs(data_dir, exist_ok=True)
    name = f"wallpaper-{time.time_ns()}.png"
    path = os.path.join(data_dir, name)
    image.save(path, format="PNG")
    if config["wallpaper_command"]:
        commands = [[part.replace("{path}", path) for part in config["wallpaper_command"]]]
    elif windows:
        user32.SystemParametersInfoW(spi_set_desk_wallpaper, 0, path, spif_update_ini_file | spif_send_change)
        commands = []
    elif macos:
        script = ["on run argv", 'tell application "System Events" to tell every desktop to set picture to (item 1 of argv)', "end run"]
        commands = [["osascript", *(arg for line in script for arg in ("-e", line)), path]]
    else:
        commands = linux_wallpaper_commands(path)
    for command in commands:
        subprocess.run(command)
    for old in os.listdir(data_dir):
        if old.startswith("wallpaper-") and old != name:
            os.remove(os.path.join(data_dir, old))


def desktop_hidden():
    # Hidden when every monitor's work area is fully covered by some visible window.
    # ponytail: Windows only; macOS and Linux (X11/Wayland each differ) always count as hidden, so they change on the timer.
    if not windows:
        return True
    covered = set()

    def check(hwnd, _):
        class_name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, class_name, 64)
        cloaked = ctypes.c_int(0)
        dwmapi.DwmGetWindowAttribute(hwnd, dwmwa_cloaked, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
        if (
            not user32.IsWindowVisible(hwnd)
            or user32.IsIconic(hwnd)
            or cloaked.value
            or class_name.value in ("Progman", "WorkerW")
            or user32.GetWindowLongW(hwnd, gwl_exstyle) & (ws_ex_transparent | ws_ex_toolwindow)
        ):
            return True
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        monitor = user32.MonitorFromWindow(hwnd, monitor_default_to_nearest)
        info = MonitorInfo(cbSize=ctypes.sizeof(MonitorInfo))
        user32.GetMonitorInfoW(monitor, ctypes.byref(info))
        work = info.rcWork
        if rect.left <= work.left and rect.top <= work.top and rect.right >= work.right and rect.bottom >= work.bottom:
            covered.add(monitor)
        return True

    user32.EnumWindows(enum_windows_proc(check), 0)
    return len(covered) >= user32.GetSystemMetrics(sm_cmonitors)
