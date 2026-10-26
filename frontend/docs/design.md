# Heimdall UI design

This explains the Heimdall overlay design in the Figma file [3d printing UI](https://www.figma.com/design/RuESD2gCHyeUYiCW0gXPMq/3d-printing-UI): what each part is for and why it looks the way it does. The Figma frames are the source of truth; this document is the reasoning behind them.

## What the screen is for

Heimdall watches a print through the webcam, combines several detectors into one failure confidence score, and pauses or cancels the print through Moonraker when that score passes a threshold the user sets. The UI sits alongside Mainsail/Fluidd rather than replacing it.

The person using it is a hobbyist with one printer who leaves long prints running. They glance at Heimdall from across the room or check it on their phone while away. So the screen has to answer one question at a glance: **is my print OK, and if not, what did Heimdall do about it?**

Everything else follows from that:

- The webcam view is the most important thing on screen, so the UI covers as little of it as possible.
- Status and confidence are readable from a distance.
- When Heimdall stops a print, the screen always says why.

## Frames in Figma

| Frame | Shows |
| --- | --- |
| Heimdall / Monitoring / Desktop | Normal state: monitoring on, low confidence |
| Heimdall / Flagged / Desktop | Heimdall has paused the print: high confidence, reason, action taken |
| Heimdall / Not monitoring / Desktop | Monitoring is off, so there is no reading |
| Heimdall / Monitoring / Desktop / Flags open | The Recent flags dropdown open |
| Heimdall / Monitoring / Desktop / Settings open | The Settings dropdown open |
| Heimdall / Monitoring / Phone | Phone layout, normal state |
| Heimdall / Flagged / Phone | Phone layout after Heimdall paused the print |
| Heimdall / Not monitoring / Phone | Phone layout with monitoring off |
| Heimdall / Monitoring / Phone / Settings open | The settings bottom sheet on phone |
| Heimdall / Design notes | Palette, type and rules, kept in the file |

The two original frames ("Heimdall – Monitoring" and "Heimdall – Flagged") are the first pass and are left as they were for comparison.

## Visual direction: railway platform signs

The look is taken from the signs above railway platforms. Those signs solve the same problem Heimdall has: give one status that people can read from far away at a glance, and make a disruption impossible to miss.

What that gives the design:

- **Solid sign-blue plates with white type.** Opaque surfaces stay readable over any part of the camera image, whether it is the dark printer frame or the bright print. We avoided the see-through "glass" panels from the first pass because their contrast changes with whatever is behind them.
- **Signal yellow for disruptions.** On a platform, the yellow notice is what tells you the train isn't coming. Here it tells you Heimdall acted.
- **One sign typeface.** Overpass is based on Highway Gothic, the US road-sign lettering, so it is built to be read at a distance.

The first-pass frames were rejected for looking generic: dark translucent panel, green toggles, pill badges. The platform-sign direction gives Heimdall its own identity while still using standard controls (toggles, a segmented control, a slider) that anyone knows how to use.

## Layout

### Desktop: the camera owns the screen

The webcam image fills the whole screen. Heimdall puts only two things on top of it, both at the edges:

1. **Status plate, top left.** This corner is usually the blurry printer frame, not the print.
2. **A row of buttons, top right:** Recent flags, Settings, and a link back to Mainsail.

Nothing sits at the bottom or in the middle, because that's where the print and nozzle are. An earlier version had a full-height settings column and then a bottom bar; both covered too much of the print, so settings and flags moved into dropdowns that only appear when opened.

### Phone: the whole camera frame, then the details

The webcam image is 4:3. Stretching it to fill a tall phone screen would crop it down to a narrow slice, so on phone the **whole image is shown at full width with nothing on top of it**. The status plate, recent flags and the Settings button sit below it. Settings opens as a bottom sheet, the usual phone pattern for a panel of controls.

Recent flags are shown open on phone (not behind a button) because there is room below the image, and on a phone the list is the next thing someone checking in remotely wants to see.

## The parts

### Status plate

The most important element. It answers "is my print OK?" in one line, then gives the evidence.

| Part | Purpose |
| --- | --- |
| Heimdall mark and name | Says which tool this is, since the page sits next to Mainsail. The mark is a lens (a ring with a yellow pupil) because Heimdall watches. |
| Status line | The answer in plain words: "Watching the print", "Paused at 14:02", "Not watching". Large and bold so it reads from across the room. |
| Reason (flagged only) | Why Heimdall acted, e.g. "Spaghetti near the nozzle". A stopped print must always say why. |
| Reading | The failure confidence and what it is measured against: "12% failure confidence, acts at 80%". The number is bold; the sentence says what it means. |
| Confidence line | The same reading drawn on a fixed 0–100 track, with a yellow stop at the threshold. You can see at a glance how close the print is to being stopped. |
| Next step (flagged only) | "Resume or cancel it in Mainsail." Heimdall can't resume a print itself, so it tells the user where to go. |

**How it changes by state**

- **Monitoring:** sign blue. The confidence fill is white because it is below the threshold.
- **Flagged:** the whole plate turns signal yellow with dark text. This is the platform disruption notice: the one moment the screen should shout.
- **Not monitoring:** sign blue, the status reads "Not watching", and the reading says "No reading. Monitoring is off." The line has no fill. We show "No reading" rather than "0%", because 0% would claim the print was checked and found fine.

### The confidence line and threshold stop

Confidence is always drawn on the same 0–100 line, at the same length, in every state. That keeps it comparable from one glance to the next: a fill that reaches past the yellow stop always means the same thing.

- **Track (dark blue):** the full 0–100 range.
- **Fill:** the current confidence. White below the threshold, yellow at or past it.
- **Yellow stop:** the threshold, the point where Heimdall acts.

### Top-right buttons

Each button shows a short summary, so the user gets the important fact without opening anything:

| Button | Summary shown | Opens |
| --- | --- | --- |
| Recent flags | When the last flag happened, e.g. "Last 21:40 yesterday" | The flags dropdown |
| Settings | What Heimdall will do, e.g. "Pause at 80%", or "Monitoring off" in yellow | The settings dropdown |
| Mainsail | — | Goes back to the printer interface |

A button turns white while its dropdown is open, so it's clear which panel belongs to which button.

### Recent flags dropdown

A short history of every time confidence passed the threshold, laid out like a departures board: one row per event, with columns that line up.

| Column | Purpose |
| --- | --- |
| Time, then day | When it happened. The time is bold; the day ("Today", "Yesterday", "Sunday") is quieter underneath. |
| Confidence | How sure Heimdall was, right-aligned so the numbers line up. |
| Reason | What Heimdall saw. |
| Action | What Heimdall did, in a colour per action: **Paused** in yellow, **Cancelled** in red, **No action** in grey. "No action" happens when Act automatically was off. |

Every flag stays in the list with what happened to it. Nothing is removed once handled, so the user can always see why an earlier print was stopped. The list is capped at three rows with "View all" for the full history.

### Settings dropdown (desktop) and sheet (phone)

All four settings the product supports, in the order a user thinks about them:

| Setting | Control | Purpose |
| --- | --- | --- |
| Monitoring | Toggle | Turns Heimdall's watching on or off. |
| Act automatically | Toggle | Whether Heimdall stops the print itself, or only records a flag. |
| When it acts | Pause / Cancel segmented control | What Heimdall does when it acts. Pause is listed first because it can be undone. |
| Threshold | Slider with the value in yellow | The confidence at which Heimdall acts. The yellow knob matches the yellow stop on the confidence line, so the two read as the same value. |

Each toggle has a one-line description saying what it does. When monitoring is off, "Act automatically" and "When it acts" are dimmed but still readable, and the description says why ("Takes effect when monitoring is on"). A disabled control that doesn't explain itself looks broken.

## Colour

| Name | Hex | Used for |
| --- | --- | --- |
| Sign blue | `#12306B` | Plates and panels |
| Rule | `#23427E` | 1px lines between flag rows |
| Track | `#2B4A8A` | Empty part of the confidence line and slider |
| White | `#FFFFFF` | Main text; confidence fill below the threshold |
| Muted | `#C9D4EC` | Secondary text |
| Faint | `#9FB1D6` | Meta text: days, descriptions |
| Signal yellow | `#F2C200` | The threshold, and anything at or past it |
| Stop red | `#FF8A7A` | "Cancelled", on blue only |
| Phone ground | `#0C0D10` | Background around the camera image on phone |

**Yellow has exactly one meaning:** the threshold, or that Heimdall acted. It is never used for decoration. Keeping it that way means a glance at the screen is enough: no yellow, nothing to worry about.

The camera image is the only colourful thing on screen. The UI sticks to blue, white and one state colour so it never competes with the print.

## Type

One typeface, **Overpass**, at a few sizes:

| Role | Size and weight |
| --- | --- |
| Status line | 24, ExtraBold |
| Panel headings | 18, ExtraBold |
| Labels and body | 14–16, Regular to Bold |
| Meta (days, descriptions) | 13, Regular |

One family keeps the screen calm, and Overpass has the road-sign character the direction needs.

## Data the screen shows

Heimdall only shows data the backend actually produces:

- whether monitoring is on
- one combined failure confidence, 0–100
- the threshold
- whether Act automatically is on, and whether it pauses or cancels
- recent flags: time, confidence, reason, and the action taken

These were deliberately **left out** of the first-pass design because the backend doesn't provide them: the gcode filename, a "Moonraker connected" indicator, "frame analysed 2s ago", and per-detector scores. Adding any of them would mean extending the backend first.

**Sample data.** The flag times, reasons and percentages in the frames are placeholders, not real history.

## Things we deliberately avoided

- **See-through glass panels and gradient scrims:** contrast changes with whatever the camera shows behind them.
- **Shadows on resting plates:** the only shadows are on the open dropdowns, because those genuinely float over the content.
- **Pill badges and emoji:** the action column uses coloured words instead, which read just as fast.
- **Covering the middle or bottom of the camera:** that is where the print is.

## Open questions

- **"View all" flags** has no screen designed yet. It needs a full flag history view.
- **Resuming a paused print** happens in Mainsail. If Heimdall should offer a resume button itself, the backend needs a resume call.
- **Error states** (camera feed lost, Heimdall not running) are not designed yet.
