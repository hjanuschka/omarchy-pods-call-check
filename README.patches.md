# Patches

## Layout

| Ref | Points at | Rule |
|---|---|---|
| `upstream` | `thisisgm/omarchy-pods` | pristine, never commit here |
| `origin` | `hjanuschka/omarchy-pods` | our fork; `main` stays equal to `upstream/main` |
| `main` | `upstream/main` | pristine, no local commits |
| `patches/*` | one branch per patch | each rebases onto `upstream/main` on its own |

## Patch 1: `patches/mic-capture-guard`

- Base at import: `fff7fec` (`upstream/main`, plugin 1.3.6)
- Files: `daemon/media/capturematch.hpp`, `daemon/media/mediacontroller.cpp`,
  `daemon/tests/tst_capturematch.cpp`
- Upstream status: not submitted yet. Candidate for a PR to `thisisgm/omarchy-pods`.

`MediaController::removeAudioOutputDevice()` released the bluez card on a
both-pods-out report without checking for a live capture, so taking the
headphones off during a call dropped the headset profiles the mic was on and
ended the call. `attemptA2dpActivation()` already defers under a live capture
("Switching under a live capture cuts the mic"); the release path did not.

The fix adds `mayReleaseCard(CaptureState)` beside `unansweredChecksAfter()`,
so the decision is testable without a sound server, as
`daemon/tests/CMakeLists.txt` requires.

Evidence, and its limit: `ctest` is green, 19/19, including
`onlyAnIdleCaptureReleasesTheCard`. That test covers the predicate only. The
original defect was observed in the journal (both-out released the card at
10:32:52 while the capture was live) but the fix has **not** yet been driven at
runtime: that needs a live capture plus the headphones physically coming off.
Do not describe this patch as runtime-verified until that is done.

## Rebasing onto a newer upstream

```bash
git fetch upstream
git switch main && git merge --ff-only upstream/main
git switch patches/mic-capture-guard
git rebase upstream/main
cd daemon && cmake --build build && ctest --test-dir build
```

The daemon is a fork of upstream librepods' `linux/main.cpp`, so a patch here
can collide with an upstream resync of that file. If it does, check whether the
capture guard arrived upstream before resolving by hand.
