# Detection

Turns webcam frames and other printer data into evidence of a failed print. Each detection method is independant from the printer itself, and can be ran in isolation with test data. Subsets of the detectors can be enabled to match user preferences.

## Planned detectors

| Detector | Looks for | Failure |
| --- | --- | --- |
| virtual_camera | print area matches current gcode progress | missing objects, spaghetti |
| delta_frames | object moved between frames | detached from bed |
| progress check | no expected change over several layers | jam, filament runout |
| edge_detection | poorly defined shapes | spaghetti |
| texture_detection | rough surfaces | under-extrusion, surface defects |
| sensors | sensor data matching what's expected | layer shifts, filament jams |


## Testing

Develop against recorded print footage and still images before running live on the Pi. Keep large footage out of git (see `.gitignore`).