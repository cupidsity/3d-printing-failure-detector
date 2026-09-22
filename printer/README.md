# printer

Communication with Klipper through the Moonraker API.

## Responsibilities

- read printer state and telemetry (flow, motor behaviour, positions, print progress)
- pause or cancel the active print
- optional notifications over MQTT via Moonraker
- any services or config needed on the printer's host Raspberry Pi

## Safety

Test commands against a printer that is idle or running a throwaway print. Anything that can pause or cancel should be easy to disable during development.

Stack: not chosen yet.
