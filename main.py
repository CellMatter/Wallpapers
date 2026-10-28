import random
import time

from Library.config import config
from Library.desktop import desktop_hidden, screen_size, set_wallpaper
from Library.generator import render_wallpaper
from Library.instance import kill_previous_instance
from Library.startup import offer_startup

poll_interval = 5


def main():
    kill_previous_instance()
    if config["ask_startup"]:
        offer_startup()
    first = True
    while True:
        # Render ahead of time so the swap is instant once the desktop is out of sight.
        image = render_wallpaper(*screen_size())
        # The first wallpaper of a run is shown right away, even with the desktop visible.
        while not first and config["change_only_when_hidden"] and not desktop_hidden():
            time.sleep(poll_interval)
        set_wallpaper(image)
        first = False
        time.sleep(random.uniform(*config["interval_seconds"]))


if __name__ == "__main__":
    main()
