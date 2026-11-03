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

**What this first test did not show.** `pedal.project` itself came from a local bare copy of its commit,
because the script was not on GitHub yet, so the second test below replaced that part.

## The second test: the one-line install, from GitHub, on mp (2026-11-03)

On mp (Linux, x86-64), which has never held the workspace, with `env -i HOME=<empty folder> PATH=$PATH`
and the README's `curl … | bash`, at pedal.project `5d6ea8e`. The folder was deleted afterwards, so mp
still has no workspace and its own git configuration was not touched.

- It took 75 s and exited 0, with 612 MB on disk.
- `scripts/workspace check` said "every check passed": all seven repositories and the vendored NAM core,
  every one clean, at the commit on GitHub, with https remotes and the git guard in force.
- A second run changed nothing.
- From that clone, `scripts/fleet check` passed and the 24 fleet and public-check tests passed.
- It reported the tools mp lacks: ninja, docker, gh and uv.

**What this does not show.** Nothing was built, because mp lacks those tools and installing a builder's
pinned tools is Phase 2. A fresh workspace still cannot measure, since `guitar-di.wav` is not yet in the
public store and the code's private defaults are not yet replaced. No agent session was started from it.
