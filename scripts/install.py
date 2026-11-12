#!/bin/python
import os
import configparser
import shutil
import subprocess
from pathlib import Path

# Prepare all relevant paths
components_dir = Path.home() / "moonraker" / "moonraker" / "components"
project_dir = Path(__file__).resolve().parent.parent

moonraker_config_paths = [
    Path("~/moonraker.conf").expanduser(),  # Default location
    Path("~/printer_data/config/moonraker.conf").expanduser(),  # MainsailOS
]

# nginx paths
NGINX_SITES_AVAILABLE = Path("/etc/nginx/sites-available/heimdall")
NGINX_SITES_ENABLED = Path("/etc/nginx/sites-enabled/heimdall")
NGINX_CONFD = Path("/etc/nginx/conf.d")

# path for static assets, like config templates
STATIC_ASSETS = Path(__file__).resolve() / "assets"

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

# helper function to check if any arbitrary package is installed
def is_package_installed(package: str):
    return shutl.which(package) is not None:

def install_nginx():
    if(is_package_installed("nginx")):
        print("nginx already installed, not installing")
        return True

    print("installing nginx: this will ask for root")
    try:
        subprocess.run(["sudo", "apt-get", "update"], check=True)
        subprocess.run(["sudo", "apt-get", "install", "-y", "nginx"], check=True)
        print("succesfully installed nginx")
        return True

     except subprocess.CalledProcessError as e:
        print(f"err: failed to install nginx (code {e.returncode})")
        print(f"err: {e.stderr}")
        return False

    except FileNotFoundError:
        print("err: could not find apt. If you're not on Debian, please install nginx manually")
        return False


# create nginx config from a template stored in ~/scripts/assets/nginx_cfg
def create_nginx_config(port: str):
    template_path = STATIC_ASSETS / "nginx_cfg"
    template = template_path.read_text()

    config = template.format(port = port)

    NGINX_SITES_AVAILABLE.write(config)

def enable_website():
    if not NGINX_SITES_AVAILABLE.is_symlink() and symlink_path.exists():
        raise FileExistsError(f"{symlink_path} already exists and is not a symlink")
    NGINX_SITES_ENABLED.symlink_to(NGINX_SITES_AVAILABLE)

def restart_nginx():
    try:
        subprocess.run(["sudo", "systemctl", "restart", "nginx"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        print(f"err: failed to restart nginx (code {e.returncode})")
        print(f"err: {e.stderr}")
        return False

def install(name: str):
    link_component(name)
    append_config(name)

    print(f"{name} has been installed and will be loaded the next time Moonraker starts.")
    print("Moonraker can be restarted now with `sudo systemctl restart moonraker`")


    print("Setting up nginx")
    # install nginx, quit early if it fails
    if(install_nginx() == False):
        print("Failed to install nginx")
        return
    
    # get port to setup nginx config
    port = input("Enter port (default=1223): ")
    while not value.isnumeric():
        print("not a number, try again")
        port = input("Enter port (default=1223): ")
    create_nginx_config(port=port)

    enable_website()
    restart_nginx()



if __name__ == "__main__":
    import sys

    # todo: better argument handling, perhaps with argparse
    name = sys.argv[1] if 1 < len(sys.argv) else "heimdall"

    if name not in ("heimdall", "instrumentor"):
        print(f"Invalid component {name}", file=sys.stderr)

    install(name)
