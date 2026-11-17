# Scripts

The simplest install path is to clone the github repo and run an install script. It will copy files to all relevant locations, install required packages, and set up default configs. The uninstall script will undo every feasible install step.

The installer and uninstaller are idempotent, so running one multiple times will have no effect. If the installer errors, it can be reran once the issue is fixed without breaking previous steps.
