import os
import shutil
import sys
import tomllib

from . import frozen, macos

project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if frozen:
    # The built app carries a default config.toml and puts it where people can edit it on first launch: next to the
    # app, or on macOS in Application Support, since files inside Wallpapers.app shouldn't change.
    if macos:
        settings_dir = os.path.expanduser("~/Library/Application Support/Wallpapers")
    else:
        settings_dir = os.path.dirname(sys.executable)
    if not os.path.exists(os.path.join(settings_dir, "config.toml")):
        os.makedirs(settings_dir, exist_ok=True)
        shutil.copy(os.path.join(sys._MEIPASS, "config.toml"), settings_dir)
else:
    settings_dir = project_dir

with open(os.path.join(settings_dir, "config.toml"), "rb") as config_file:
    config = tomllib.load(config_file)
