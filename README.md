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
git-sd1 amend               # amend after review: refreshes the file list, keeps what you wrote
```

Other arguments (`-a`, `-v`, ...) are passed through to `git commit`. Replace every line marked `(OOPS!)` before pushing.

### Pull requests

```
git-sd1 pr            # push the branch and open (or update) its pull request
git-sd1 pr --draft    # open as a draft, allowed to still contain (OOPS!) lines
git-sd1 pr --open     # also open it in the browser
```

`pr` commits anything staged first. Every pull request starts from its own branch. On a branch that already has its commit, the staged changes are folded into it with `git-sd1 amend`, so review fixes don't pile up as extra commits. Run from `main`, your commits move onto a new `eng/<title>` branch and `main` is reset to match `origin/main`. The branch is rebased onto the latest `main` and force-pushed, and the pull request title and description are rebuilt from the commit message on every run. Edit the commit message, not the description on GitHub.

#### Reused branch names

A branch whose pull request is already closed has usually been landed, and pushing to it again hides new commits under a finished review. Before pushing, `pr` checks whether the branch it is about to use already had a pull request, and if it did, asks:

```
git-sd1: eng/detection-add-fusion already had pull request #4 (merged 2026-09-20), so this
would be a second pull request from the same branch name.
open another pull request from eng/detection-add-fusion anyway? [y/N]
```

Answer `y` to go ahead with that name. Answer `n` and it asks for another branch name to use instead (`eng/` is added if you leave it out), moves your commits there, and opens the pull request from that branch. Leave the name blank to stop: nothing is pushed, and commits that `pr` moved off `main` are put back on `main` exactly as they were.

With no terminal to ask on, `pr` stops instead of guessing. Pass `--branch NAME` to pick a different branch or `--reuse-branch` to use the name anyway.

`pr` needs a GitHub token that can create pull requests. It uses `GITHUB_TOKEN` (or `GH_TOKEN`) if set, and otherwise asks git for the token it already uses to push (your credential helper, or your editor's GitHub login). If you have more than one GitHub account, put your username in the remote (`https://<username>@github.com/...`) so the right token is picked. `pr` prints which account opened the pull request.

### Landing

Add the `merge-queue` label to a pull request to land it. A GitHub Action rebases its commits onto the latest `main` and pushes them there as they are, with no `Merge pull request #N` commit. Before pushing, it fills in `Reviewed by NOBODY (OOPS!).` from the pull request's approvals (`Reviewed by Caleb Feng.`), or `Unreviewed.` if nobody approved. A reviewer line you wrote yourself is left alone.

The queue refuses to land, and says why in a comment, if a reviewer requested changes, a line other than the reviewer line is still `(OOPS!)`, or the commits conflict with `main`. The label is removed either way, so adding it again retries. Landings run one at a time. Please land with the label instead of GitHub's merge button.

`git-sd1 land <number>` does the same thing from your own machine.

Run the tests with `python3 -m unittest discover Tools/Scripts/tests`.

## Team Members 
1. Layla Le
2. John Vezzola
3. Diego Van Eggelpoel
4. Nathan Spees