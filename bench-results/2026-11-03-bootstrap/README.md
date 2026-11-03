# Starting from nothing: the first test of scripts/bootstrap (2026-11-03)

On the M2, with `env -i HOME=<empty folder> PATH=$PATH`, so no git configuration, no keys and no
workspace. It took about a minute.

- Every repository in `workspace.repos` cloned over https, with the vendored NAM core and its own
  submodules.
- `scripts/workspace check` passed: "every check passed", the git guard in force through `~/.gitconfig`.
- With `comms` deleted, running it again restored only that repository.
- From the fresh clone, namchain configured with CMake, and `public-check`'s tests passed.

**The first run found a real bug:** `workspace clone` passed a submodule's path relative to the wrong
folder, so it could never have worked on a fresh machine. Nothing had ever run it on one.

**What this does not show.** `pedal.project` itself came from a local bare copy of its commit, because
the script was not on GitHub yet. Nothing was built, tools were this machine's own, and a fresh
workspace still cannot measure, since `guitar-di.wav` is not yet in the public store.
