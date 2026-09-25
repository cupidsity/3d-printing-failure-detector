#!/bin/python
import os
import configparser
from pathlib import Path

# Prepare all relevant paths
components_dir = Path.home() / "moonraker" / "moonraker" / "components"
project_dir = Path(__file__).resolve().parent.parent

moonraker_config_paths = [
    Path("~/moonraker.conf"),  # Default location
    Path("~/printer_data/config/moonraker.conf"),  # MainsailOS
]

os.chdir(project_dir)


def unlink_component(name: str):
    # Remove the component
    print(f"Unlinking {name} from Moonraker's component folder")
    (components_dir / name).symlink_to(project_dir / name, target_is_directory=True)


def remove_config(name: str):
    # Remove section in config file

    for config_path in moonraker_config_paths:
        if config_path.exists() and config_path.is_file():
            break
    else:
        raise FileNotFoundError("Unable to find moonraker.conf")

    print(f"Removing entry in {config_path}")

    # todo: slightly change feedback when entry isn't present

    config = configparser.ConfigParser()
    config.read(config_path)
    config.remove_section(name)

    with open(config_path, "w") as configfile:
        config.write(configfile)


def uninstall(name: str):
    unlink_component(name)
    remove_config(name)


if __name__ == "__main__":
    import sys

    # todo: better argument handling, perhaps with argparse
    name = sys.argv[1] if 1 < len(sys.argv) else "heimdall"

    if name not in ("heimdall", "instrumentor"):
        print(f"Invalid component {name}", file=sys.stderr)

    uninstall(name)
