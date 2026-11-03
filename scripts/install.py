#!/bin/python
import os
import configparser
from pathlib import Path

from .shared import components_dir, project_dir, get_moonraker_config_path


def link_component(name: str):
    # Add the project as a component

    if not (components_dir / name).exists():
        print(f"Linking {name} to Moonraker's component folder")
        (components_dir / name).symlink_to(project_dir / name, target_is_directory=True)
        print("Component linked!")
    else:
        print(f"{components_dir / name} already exists, skipping...")


def append_moonraker_config(name: str, moonraker_config_path: Path):
    # Create section in config file
    # todo: check with the user that it's the right location

    config = configparser.ConfigParser()
    config.read(moonraker_config_path)

    if config.has_section(name):
        print(
            f"Entry for {name} already exists in {moonraker_config_path}, skipping..."
        )

    else:
        print(f"Creating entry in {moonraker_config_path}")
        config.add_section(name)
        with open(moonraker_config_path, "w") as configfile:
            config.write(configfile)
        print("Entry created!")


def generate_config(moonraker_config_path: Path):

    print("Generating heimdall config...")
    if (moonraker_config_path.parent / "heimdall.conf").exists():
        print(
            f"Merging with previous config at {(moonraker_config_path.parent / "heimdall.conf").as_posix()}"
        )

    # ConfigParser prefers keys from later entries, and silently ignores missing files
    config = configparser.ConfigParser()
    config.read(
        [
            project_dir / "scripts" / "default_config.conf",
            moonraker_config_path.parent / "heimdall.conf",
        ]
    )

    # Check if we need to ask about pausing
    if "allow_pause" not in config["heimdall"]:

        # See if klippy has pausing enabled
        klippy_config = configparser.ConfigParser()
        klippy_config.read(moonraker_config_path.parent / "printer.cfg")

        if "pause_resume" in klippy_config:
            print("Allow Heimdall to automatically pause failing prints? (Y/n)")
            choice = input("> ")

            if choice in ("n", "N", "no", "No", "NO"):
                config["heimdall"]["allow_pause"] = "false"
            else:
                config["heimdall"]["allow_pause"] = "true"
        else:
            print(
                "Pausing not configured in Klippy (printer.cfg). Heimdall will not automatically pause failing prints"
            )
            config["heimdall"]["allow_pause"] = "false"

    with open(moonraker_config_path) as f:
        config.write(f)

    print(
        f"Config file written to {(moonraker_config_path.parent / "heimdall.conf").as_posix()}"
    )


def install(name: str):
    moonraker_config_path = get_moonraker_config_path()
    link_component(name)
    append_moonraker_config(name, moonraker_config_path)

    # End instrumentor, that's all it needs
    if name != "heimdall":
        print(
            f"{name} has been installed and will be loaded the next time Moonraker starts."
        )
        print("Moonraker can be restarted now with `sudo systemctl restart moonraker`")
        return

    generate_config(moonraker_config_path)

    print(
        f"{name} has been installed and will be loaded the next time Moonraker starts."
    )
    print("Moonraker can be restarted now with `sudo systemctl restart moonraker`")


if __name__ == "__main__":
    import sys

    # todo: better argument handling, perhaps with argparse
    name = sys.argv[1] if 1 < len(sys.argv) else "heimdall"

    if name not in ("heimdall", "instrumentor"):
        print(f"Invalid component {name}", file=sys.stderr)

    install(name)
