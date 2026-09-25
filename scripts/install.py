#!/bin/python
import os
import configparser
from pathlib import Path

# Prepare all relevant paths
components_dir = Path.home() / "moonraker" / "moonraker" / "components"
project_dir = Path(__file__).resolve().parent.parent

moonraker_config_paths = [
    Path("~/moonraker.conf").expanduser(),  # Default location
    Path("~/printer_data/config/moonraker.conf").expanduser(),  # MainsailOS
]

os.chdir(project_dir)


def link_component(name: str):
    # Add the project as a component

    if not (components_dir / name).exists():
        print(f"Linking {name} to Moonraker's component folder")
        (components_dir / name).symlink_to(project_dir / name, target_is_directory=True)
    else:
        print(f"{components_dir / name} already exists, skipping...")


def append_config(name: str):
    # Create section in config file

    for config_path in moonraker_config_paths:
        if config_path.exists() and config_path.is_file():
            break
    else:
        raise FileNotFoundError("Unable to find moonraker.conf")

    # todo: check with the user that it's the right location

    config = configparser.ConfigParser()
    config.read(config_path)

    if config.has_section(name):
        print(f"Entry for {name} already exists in {config_path}, skipping...")

    else:
        print(f"Creating entry in {config_path}")
        config.add_section(name)
        with open(config_path, "w") as configfile:
            config.write(configfile)


def install(name: str):
    link_component(name)
    append_config(name)

    print(f"{name} has been installed and will be loaded the next time Moonraker starts.")
    print("Moonraker can be restarted now with `sudo systemctl restart moonraker`")


if __name__ == "__main__":
    import sys

    # todo: better argument handling, perhaps with argparse
    name = sys.argv[1] if 1 < len(sys.argv) else "heimdall"

    if name not in ("heimdall", "instrumentor"):
        print(f"Invalid component {name}", file=sys.stderr)

    install(name)
