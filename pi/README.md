# pi

Raspberry Pi setup and deployment. The Pi ties the webcam, detectors, printer connection, and frontend together.

## Scope

- OS and dependency setup
- webcam configuration
- services that run the detector alongside Klipper/Moonraker
- resource limits: detection has to run within the Pi's CPU and memory budget

## Test hardware

Integration testing happens on the team's printers, which are different brands. Note any printer-specific setup here so the software doesn't quietly depend on one machine.
