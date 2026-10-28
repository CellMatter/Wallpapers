import ctypes
import os
import plistlib
import shutil
import subprocess
import sys

from . import frozen, macos, windows
from .config import project_dir

app_title = "Wallpapers"
startup_name = "wallpapers"
startup_question = (
    "Wallpapers is not set to start when you sign in, so your wallpaper stops changing after a restart.\n\n"
    "Start it automatically when you sign in?\n\n"
    "(Set ask_startup = false in config.toml to stop this question.)"
)

if windows:
    import winreg

    run_key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    run_value_name = "Wallpapers"
    mb_yesno = 0x04
    mb_iconwarning = 0x30
    mb_setforeground = 0x10000
    idyes = 6

    user32 = ctypes.windll.user32


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


def ask_yes_no_warning(message):
    if windows:
        return user32.MessageBoxW(None, message, app_title, mb_yesno | mb_iconwarning | mb_setforeground) == idyes
    if macos:
        script = [
            "on run argv",
            f'display dialog (item 1 of argv) with title "{app_title}" with icon caution buttons {{"No", "Yes"}} default button "Yes"',
            "end run",
        ]
        command = ["osascript", *(arg for line in script for arg in ("-e", line)), message]
        return "Yes" in subprocess.run(command, capture_output=True, text=True).stdout
    # zenity ships with GNOME-family desktops, kdialog with KDE.
    if shutil.which("zenity"):
        return subprocess.run(["zenity", "--question", f"--title={app_title}", f"--text={message}"]).returncode == 0
    if shutil.which("kdialog"):
        return subprocess.run(["kdialog", "--title", app_title, "--warningyesno", message]).returncode == 0
    print(f"Warning: {message.splitlines()[0]} Install zenity or kdialog to be asked about it.", file=sys.stderr)
    return False


def offer_startup():
    if not startup_enabled() and ask_yes_no_warning(startup_question):
        enable_startup()
