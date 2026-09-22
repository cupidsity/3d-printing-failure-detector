# frontend

User-facing layer. Integrates with the existing printer interface rather than shipping as a separate app.

## MVP

- toggle automatic cancellation
- set the confidence threshold
- show whether monitoring is active and whether a potential failure was detected

## Later

- live webcam view
- per-detector outputs
- recent detection events with the reason a print was flagged
- per-detector settings

## Development

Build against simulated data first, then connect to the real backend. Only display information the real system can actually produce.

Stack: not chosen yet.
