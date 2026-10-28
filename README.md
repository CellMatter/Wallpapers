# Wallpapers

Generates a new abstract wallpaper of layered, draped sheets every few minutes and sets it as your desktop background.
It's written for Windows, macOS and Linux and renders at your screen's resolution.

> [!NOTE]
> Only tested on Windows. The macOS and Linux support has never run on a real machine.
> AI (Claude Opus 5.5 & Sonnet 5.5) was used for this project.

<p>
  <img src="docs/render-pink.png" alt="Pink render" width="49%">
  <img src="docs/render-teal.png" alt="Teal render" width="49%">
  <img src="docs/render-green.png" alt="Green render" width="49%">
  <img src="docs/render-red.png" alt="Red render" width="49%">
</p>

## Run

Needs Python 3.11 or newer.

```bash
pip install -r requirements.txt
python main.py
```

On Windows, use `pythonw main.py` to run it without a console window. On first launch it offers to start itself when
you sign in. Starting it again replaces the copy that is already running.

## Build

To get a standalone app that shows up as "Wallpapers" instead of Python:

```bash
pip install pyinstaller
python build.py
```

The file to upload ends up in `build/release/`; everything else goes in `build/work/`. PyInstaller only builds for the
system it runs on, so this gives you the build for your own OS. To get all three, push the repo to GitHub and run the
**Build** workflow from the Actions tab (the builds can be downloaded from the run), or push a tag like `v1.0` to
attach them to a GitHub Release.

| OS | File | Settings file (created on first launch) |
|---|---|---|
| Windows | `Wallpapers-windows-amd64.exe` | `config.toml` next to the exe |
| macOS | `Wallpapers-macos-arm64.zip`, containing `Wallpapers.app` | `~/Library/Application Support/Wallpapers/config.toml` |
| Linux | `Wallpapers-linux-x86_64` | `config.toml` next to the program |

- The end of each name is the chip it was built for. GitHub builds the Mac app for Apple Silicon only; it won't run on
  Intel Macs.
- On Linux, make the downloaded file runnable first: `chmod +x Wallpapers-linux-x86_64`.
- The Mac app isn't signed with an Apple Developer ID, so macOS blocks the first launch: right-click it and choose
  Open, or use System Settings → Privacy & Security → Open Anyway.

## Configure

Edit `config.toml`:

| Setting | What it does |
|---|---|
| `interval_seconds` | Random wait between wallpapers, as `[min, max]` |
| `change_only_when_hidden` | Only swap while windows cover the desktop (Windows only) |
| `hue_ranges`, `saturation`, `brightness` | Tint colors to pick from |
| `supersample` | Edge smoothness; higher is slower |
| `wallpaper_command` | Your own command for setting the wallpaper; `{path}` is the image |
| `ask_startup` | Whether to offer starting at sign-in |

## Supported desktops

Windows, macOS, and on Linux GNOME (plus Ubuntu, Budgie and Pantheon), KDE Plasma, XFCE, Cinnamon and MATE. For
anything else (sway, i3, Hyprland…), set `wallpaper_command`, for example `["feh", "--bg-fill", "{path}"]`. On Linux, the
startup question needs `zenity` or `kdialog`.

## License

MIT, see [LICENSE](LICENSE).
