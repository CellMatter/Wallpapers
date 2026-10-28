# Builds the standalone Wallpapers app, so the running process shows up as "Wallpapers" with a blank icon instead of
# as Python, and puts it in build/release/, ready to upload: a single file on Windows and Linux, a zipped .app on macOS.
# Everything else PyInstaller makes goes in build/work/. Needs PyInstaller (pip install pyinstaller); it only builds
# for the OS it runs on, so .github/workflows/build.yml builds all three on GitHub.
import os
import platform
import plistlib
import shutil
import subprocess
import sys

import PyInstaller.__main__
from PIL import Image

work_dir = os.path.join("build", "work")
dist_dir = os.path.join(work_dir, "dist")
release_dir = os.path.join("build", "release")
os_name = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
# Mac builds only run on the chip they were built on, so every archive names it.
release_name = os.path.join(release_dir, f"Wallpapers-{os_name}-{platform.machine().lower()}")
os.makedirs(work_dir, exist_ok=True)
os.makedirs(release_dir, exist_ok=True)
# The app writes this default config.toml where people can edit it on first launch.
options = ["--add-data", f"{os.path.abspath('config.toml')}{os.pathsep}."]
if sys.platform != "darwin":
    # One self-contained file. A Mac .app is already a single item, and PyInstaller is retiring onefile .apps.
    options.append("--onefile")

if sys.platform in ("win32", "darwin"):
    icon_path = os.path.abspath(os.path.join(work_dir, "blank.ico"))
    Image.new("RGBA", (256, 256)).save(icon_path, sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
    # On macOS, --windowed is what makes a .app.
    options += ["--windowed", "--icon", icon_path]

if sys.platform == "win32":
    # Task Manager names a process by its exe's FileDescription.
    version_path = os.path.abspath(os.path.join(work_dir, "version.txt"))
    with open(version_path, "w") as f:
        f.write(
            "VSVersionInfo(ffi=FixedFileInfo(filevers=(1, 0, 0, 0), prodvers=(1, 0, 0, 0)), kids=["
            "StringFileInfo([StringTable('040904B0', [StringStruct('FileDescription', 'Wallpapers'), "
            "StringStruct('ProductName', 'Wallpapers'), StringStruct('OriginalFilename', 'Wallpapers.exe'), "
            "StringStruct('FileVersion', '1.0.0.0'), StringStruct('ProductVersion', '1.0.0.0')])]), "
            "VarFileInfo([VarStruct('Translation', [1033, 1200])])])"
        )
    options += ["--version-file", version_path]

PyInstaller.__main__.run(
    [
        "main.py", "--name", "Wallpapers", "--noconfirm",
        "--workpath", work_dir, "--specpath", work_dir, "--distpath", dist_dir, *options,
    ]
)

if sys.platform == "darwin":
    app_path = os.path.join(dist_dir, "Wallpapers.app")
    plist_path = os.path.join(app_path, "Contents", "Info.plist")
    with open(plist_path, "rb") as f:
        info = plistlib.load(f)
    # A background app: no Dock icon or menu bar while it runs.
    info["LSUIElement"] = True
    with open(plist_path, "wb") as f:
        plistlib.dump(info, f)
    # Editing Info.plist breaks PyInstaller's signature, and Apple Silicon Macs refuse unsigned apps; sign it again.
    subprocess.run(["codesign", "--force", "--deep", "--sign", "-", app_path], check=True)
    # ditto keeps the links inside the .app, which a plain zip would break.
    release_path = release_name + ".zip"
    subprocess.run(["ditto", "-c", "-k", "--keepParent", app_path, release_path], check=True)
else:
    extension = ".exe" if sys.platform == "win32" else ""
    release_path = shutil.copy(os.path.join(dist_dir, "Wallpapers" + extension), release_name + extension)

print(f"\nReady to ship: {os.path.abspath(release_path)}")
