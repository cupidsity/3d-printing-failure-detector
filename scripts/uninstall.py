#!/bin/python
import os
import configparser
from pathlib import Path

from .shared import components_dir, project_dir, get_moonraker_config_path


def unlink_component(name: str):
    # Remove the component
    print(f"Unlinking {name} from Moonraker's component folder")
    (components_dir / name).symlink_to(project_dir / name, target_is_directory=True)


def remove_moonraker_config(name: str, moonraker_config_path: Path):
    print(f"Removing entry in {moonraker_config_path}")

    # Remove section in config file
    # todo: slightly change feedback when entry isn't present

    config = configparser.ConfigParser()
    config.read(moonraker_config_path)
    config.remove_section(name)

    with open(moonraker_config_path, "w") as configfile:
        config.write(configfile)


def remove_config(path: Path):
    path.unlink()


def uninstall(name: str):
    moonraker_config_path = get_moonraker_config_path()

    unlink_component(name)
    remove_moonraker_config(name, moonraker_config_path)

    # End instrumentor, that's all it needs
    if name != "heimdall":
        print(
            f"{name} has been uninstalled. Restart Moonraker to unload the running component"
        )

    remove_config(moonraker_config_path.parent / "heimdall.conf")

    print(
        f"{name} has been uninstalled. Restart Moonraker to unload the running component"
    )


if __name__ == "__main__":
    import sys

    # todo: better argument handling, perhaps with argparse
    name = sys.argv[1] if 1 < len(sys.argv) else "heimdall"

    if name not in ("heimdall", "instrumentor"):
        print(f"Invalid component {name}", file=sys.stderr)

    uninstall(name)
