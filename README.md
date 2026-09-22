# 3d-printing-failure-detector

A locally-run failure detector for Klipper 3D printers. A webcam watches the print, several detection methods look for signs of failure, and their outputs are combined into a single confidence score. When that score passes a user-set threshold, the system pauses or cancels the print through the Moonraker API.

Everything runs on a Raspberry Pi (or similar) next to the printer.

## Repository layout

| Path | Contents |
| --- | --- |
| `detection/` | image-processing detectors and the confidence fusion logic |
| `printer/` | Moonraker client, printer commands, MQTT notifications |
| `frontend/` | user-facing interface |
| `pi/` | Raspberry Pi setup, services, deployment |