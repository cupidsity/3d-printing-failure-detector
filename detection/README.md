# detection

Turns webcam frames (and printer telemetry from `printer/`) into evidence of a failed print, then fuses that evidence into one confidence score.

## Planned detectors

| Detector | Looks for | Failure |
| --- | --- | --- |
| frame comparison | object moved between frames | detached from bed |
| progress check | no expected change over several layers | jam, filament runout |
| edge detection | poorly defined shapes | spaghetti |
| texture analysis | rough surfaces | under-extrusion, surface defects |

## Fusion

No detector cancels a print by itself. Each one raises or lowers overall confidence, and action happens only when the combined score passes the user's threshold.

## Testing

Develop against recorded print footage and still images before running live on the Pi. Keep large footage out of git (see `.gitignore`).

Stack: not chosen yet.
