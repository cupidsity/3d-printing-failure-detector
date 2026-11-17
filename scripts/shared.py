import os
from pathlib import Path

# Prepare all relevant paths
components_dir = Path.home() / "moonraker" / "moonraker" / "components"
project_dir = Path(__file__).resolve().parent.parent

os.chdir(project_dir)


def get_moonraker_config_path():
    moonraker_config_paths = [
        Path("~/moonraker.conf").expanduser(),  # Default location
        Path("~/printer_data/config/moonraker.conf").expanduser(),  # MainsailOS
    ]

    for config_path in moonraker_config_paths:
        if config_path.exists() and config_path.is_file():
            return config_path

    raise FileNotFoundError("Unable to find moonraker.conf")
