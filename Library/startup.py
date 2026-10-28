import ctypes
import os
import plistlib
import re
import shutil
import subprocess
import sys

from . import frozen, macos, windows
from .config import project_dir, settings_dir

app_title = "Wallpapers"
startup_name = "wallpapers"
startup_question = (
    "Wallpapers is not set to start when you sign in, so your wallpaper stops changing after a restart.\n\n"
    "Start it automatically when you sign in?"
)
dont_ask = "Don't ask again"

if windows:
    import ctypes.wintypes as wt
    import winreg

    run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    run_value_name = "Wallpapers"
    mb_abortretryignore = 0x02
    mb_iconwarning = 0x30
    mb_setforeground = 0x10000
    idabort, idretry, idignore = 3, 4, 5
    wh_cbt = 5
    hcbt_activate = 5
    wm_getfont = 0x31

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    gdi32 = ctypes.windll.gdi32
    cbt_proc = ctypes.WINFUNCTYPE(wt.LPARAM, ctypes.c_int, wt.WPARAM, wt.LPARAM)
    user32.SetWindowsHookExW.restype = wt.HHOOK
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, cbt_proc, wt.HINSTANCE, wt.DWORD]
    user32.CallNextHookEx.restype = wt.LPARAM
    user32.CallNextHookEx.argtypes = [wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM]
    user32.UnhookWindowsHookEx.argtypes = [wt.HHOOK]
    user32.SetDlgItemTextW.argtypes = [wt.HWND, ctypes.c_int, wt.LPCWSTR]
    user32.GetDlgItem.restype = wt.HWND
    user32.GetDlgItem.argtypes = [wt.HWND, ctypes.c_int]
    user32.GetDC.restype = wt.HDC
    user32.GetDC.argtypes = [wt.HWND]
    user32.ReleaseDC.argtypes = [wt.HWND, wt.HDC]
    user32.SendMessageW.restype = wt.LPARAM
    user32.SendMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
    user32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
    user32.MapWindowPoints.argtypes = [wt.HWND, wt.HWND, ctypes.POINTER(wt.RECT), wt.UINT]
    user32.MoveWindow.argtypes = [wt.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wt.BOOL]
    gdi32.SelectObject.restype = wt.HGDIOBJ
    gdi32.SelectObject.argtypes = [wt.HDC, wt.HGDIOBJ]
    gdi32.GetTextExtentPoint32W.argtypes = [wt.HDC, wt.LPCWSTR, ctypes.c_int, ctypes.POINTER(wt.SIZE)]


def launch_command():
    # The built app (see build.py) runs by itself; from source it's Python running main.py.
    if frozen:
        return [sys.executable]
    python = sys.executable
    if windows:
        # pythonw runs without a console window.
        python = os.path.join(os.path.dirname(python), "pythonw.exe")
    return [python, os.path.join(project_dir, "main.py")]


def startup_entry():
    # Where each OS keeps what starts at sign-in, and what this app's entry there looks like.
    command = launch_command()
    quoted = " ".join(f'"{part}"' for part in command)
    if windows:
        return run_value_name, quoted
    if macos:
        path = os.path.expanduser(f"~/Library/LaunchAgents/{startup_name}.plist")
        return path, plistlib.dumps({"Label": startup_name, "ProgramArguments": command, "RunAtLoad": True})
    config_home = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    # The folder name is fixed by the XDG autostart spec, so desktops find the entry there.
    path = os.path.join(config_home, "autostart", f"{startup_name}.desktop")
    return path, f"[Desktop Entry]\nType=Application\nName={app_title}\nExec={quoted}\n".encode()


def startup_enabled():
    # An entry pointing somewhere else (the app moved, another venv) counts as not enabled.
    where, entry = startup_entry()
    try:
        if windows:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, run_key_path) as key:
                return winreg.QueryValueEx(key, where)[0] == entry
        with open(where, "rb") as f:
            return f.read() == entry
    except OSError:
        return False


def enable_startup():
    where, entry = startup_entry()
    if windows:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, run_key_path) as key:
            winreg.SetValueEx(key, where, 0, winreg.REG_SZ, entry)
        return
    os.makedirs(os.path.dirname(where), exist_ok=True)
    with open(where, "wb") as f:
        f.write(entry)


def widen_dont_ask_button(dialog):
    # MessageBox's buttons are too narrow for "Don't ask again": widen it and shift the right-aligned row left.
    button = user32.GetDlgItem(dialog, idignore)
    dc = user32.GetDC(button)
    old_font = gdi32.SelectObject(dc, user32.SendMessageW(button, wm_getfont, 0, 0))
    text = wt.SIZE()
    gdi32.GetTextExtentPoint32W(dc, dont_ask, len(dont_ask), ctypes.byref(text))
    gdi32.SelectObject(dc, old_font)
    user32.ReleaseDC(button, dc)
    rect = wt.RECT()
    user32.GetClientRect(button, ctypes.byref(rect))
    # Leave about a line's height of padding on each side of the text.
    extra = text.cx + 2 * text.cy - rect.right
    if extra <= 0:
        return
    for button_id in (idabort, idretry, idignore):
        item = user32.GetDlgItem(dialog, button_id)
        user32.GetWindowRect(item, ctypes.byref(rect))
        user32.MapWindowPoints(None, dialog, ctypes.byref(rect), 2)
        width = rect.right - rect.left + (extra if button_id == idignore else 0)
        user32.MoveWindow(item, rect.left - extra, rect.top, width, rect.bottom - rect.top, True)


def ask_about_startup():
    # Shows the startup question as a warning with Yes, No and Don't ask again; returns "yes", "no" or "never".
    # Closing the dialog always counts as No, never as Don't ask again.
    if windows:
        # MessageBox only has stock buttons, so Abort/Retry/Ignore get relabelled as the box opens. That set has no
        # Cancel, so the box can't be closed without picking one.
        def relabel(code, wparam, lparam):
            if code == hcbt_activate:
                for button, label in zip((idabort, idretry, idignore), ("Yes", "No", dont_ask)):
                    user32.SetDlgItemTextW(wparam, button, label)
                widen_dont_ask_button(wparam)
            return user32.CallNextHookEx(None, code, wparam, lparam)

        callback = cbt_proc(relabel)
        hook = user32.SetWindowsHookExW(wh_cbt, callback, None, kernel32.GetCurrentThreadId())
        flags = mb_abortretryignore | mb_iconwarning | mb_setforeground
        answer = user32.MessageBoxW(None, startup_question, app_title, flags)
        user32.UnhookWindowsHookEx(hook)
        return {idabort: "yes", idignore: "never"}.get(answer, "no")
    if macos:
        # Without a button named Cancel, Esc can't dismiss the dialog.
        script = [
            "on run argv",
            f'display dialog (item 1 of argv) with title "{app_title}" with icon caution '
            f'buttons {{"{dont_ask}", "No", "Yes"}} default button "Yes"',
            "end run",
        ]
        command = ["osascript", *(arg for line in script for arg in ("-e", line)), startup_question]
        clicked = subprocess.run(command, capture_output=True, text=True).stdout.strip().removeprefix("button returned:")
        return {"Yes": "yes", dont_ask: "never"}.get(clicked, "no")
    # zenity ships with GNOME-family desktops, kdialog with KDE.
    if shutil.which("zenity"):
        command = ["zenity", "--question", f"--title={app_title}", f"--text={startup_question}", "--ok-label=Yes",
                   "--cancel-label=No", f"--extra-button={dont_ask}"]
        result = subprocess.run(command, capture_output=True, text=True)
        # The extra button prints its label; Yes exits with 0.
        return "never" if result.stdout.strip() == dont_ask else "yes" if result.returncode == 0 else "no"
    if shutil.which("kdialog"):
        # kdialog's Cancel slot is what Esc and closing pick, so it's the No button here.
        command = ["kdialog", "--title", app_title, "--warningyesnocancel", startup_question, "--yes-label", "Yes",
                   "--no-label", dont_ask, "--cancel-label", "No"]
        return {0: "yes", 1: "never"}.get(subprocess.run(command).returncode, "no")
    print(f"Warning: {startup_question.splitlines()[0]} Install zenity or kdialog to be asked about it.", file=sys.stderr)
    return "no"


def stop_asking():
    # tomllib can only read, so flip the line by hand to keep the file's comments.
    path = os.path.join(settings_dir, "config.toml")
    with open(path, encoding="utf-8", newline="") as f:
        text = f.read()
    text, found = re.subn(r"(?m)^ask_startup\s*=[^\r\n]*", "ask_startup = false", text)
    if not found:
        text += "\nask_startup = false\n"
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def offer_startup():
    if startup_enabled():
        return
    answer = ask_about_startup()
    if answer == "yes":
        enable_startup()
    elif answer == "never":
        stop_asking()
