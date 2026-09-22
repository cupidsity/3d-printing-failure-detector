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
## Commits

Significant commits follow this format:

```
Short descriptive title
https://github.com/cupidsity/3d-printing-failure-detector/issues/24

Reviewed by Reviewer Name.

What the change does, why it was needed, and any important
implementation decisions.

* path/to/changed/file:
(ChangedFunction):
* path/to/new/file: Added.
```

`Tools/Scripts/git-sd1` fills most of this in for you. Run this once after cloning, and again whenever anything in `Tools/Scripts/hooks` changes:

```
Tools/Scripts/git-sd1 setup
```

Then stage your changes and commit with:

```
Tools/Scripts/git-sd1 commit              # new commit, file list filled in from what's staged
Tools/Scripts/git-sd1 commit --issue 24   # also link issue 24 and use its title
Tools/Scripts/git-sd1 commit --update     # amend after review: refreshes the file list, keeps what you wrote
```

Other arguments (`-a`, `-v`, ...) are passed through to `git commit`. If you add `Tools/Scripts` to your `PATH`, `git sd1 commit` works too. Replace every line marked `(OOPS!)` before pushing.

Run the tests with `python3 -m unittest discover Tools/Scripts/tests`.
