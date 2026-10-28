import sys

windows = sys.platform == "win32"
macos = sys.platform == "darwin"
# True when running as the app built by build.py instead of from source.
frozen = getattr(sys, "frozen", False)
