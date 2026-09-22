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
[Detection] Average detector scores instead of taking the max
https://github.com/cupidsity/3d-printing-failure-detector/issues/24

Reviewed by Reviewer Name.

What the change does, why it was needed, and any important
implementation decisions.

Test: detection/tests/test_fusion.py

* detection/fusion.py:
(Fusion.fuse):
(legacy_fuse): Deleted.
* detection/tests/test_fusion.py: Added.
```

- The title starts with the area it touches in brackets, taken from the top-level folder (`[Detection]`, `[Printer]`, `[Frontend]`, `[Pi]`, `[Tools]`).
- The issue link is only there when the change has a GitHub issue.
- `Test:` (or `Tests:`, one per line) lists the test files the change adds or modifies.
- Functions are qualified by their class (`Class.method` in Python and TypeScript, `Class::method` in C++). Functions the change removes are marked `Deleted.`

`git-sd1` fills most of this in for you. Run this once after cloning, and again whenever anything in `Tools/Scripts/hooks` changes:

```
Tools/Scripts/git-sd1 setup
```

Setup installs the commit hook. Then put `Tools/Scripts` on your `PATH` (setup prints the exact line for your `~/.zshrc` or `~/.bashrc`) so `git-sd1` works from anywhere. Stage your changes and commit with:

```
git-sd1 commit              # new commit, file list filled in from what's staged
git-sd1 commit --issue 24   # also link issue 24 and use its title
git-sd1 commit --update     # amend after review: refreshes the file list, keeps what you wrote
```

Other arguments (`-a`, `-v`, ...) are passed through to `git commit`. Replace every line marked `(OOPS!)` before pushing.

### Pull requests

```
git-sd1 pr            # push the branch and open (or update) its pull request
git-sd1 pr --draft    # open as a draft, allowed to still contain (OOPS!) lines
git-sd1 pr --open     # also open it in the browser
```

`pr` commits anything staged first. On a branch that already has its commit, the staged changes are folded into it with `commit --update`, so review fixes don't pile up as extra commits. Run from `main`, your commits move onto a new `eng/<title>` branch and `main` is reset to match `origin/main`. The branch is rebased onto the latest `main` and force-pushed, and the pull request title and description are rebuilt from the commit message on every run. Edit the commit message, not the description on GitHub.

`pr` needs a GitHub token that can create pull requests. It uses `GITHUB_TOKEN` (or `GH_TOKEN`) if set, and otherwise asks git for the token it already uses to push (your credential helper, or your editor's GitHub login). If you have more than one GitHub account, put your username in the remote (`https://<username>@github.com/...`) so the right token is picked. `pr` prints which account opened the pull request.

Run the tests with `python3 -m unittest discover Tools/Scripts/tests`.

## Team Members 
Layla Le
