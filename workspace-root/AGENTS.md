# The pedal workspace

This directory is the workspace root: the folder a session is opened on, and the root the file
sandbox grants. The pedal's six repositories are inside it, so an agent can read and write all of
them with no extra permissions and no per-project settings.

**Before doing anything, read `pedal.project/AGENTS.md`.** It is canonical for the whole project —
goal, hardware constraints, commands, working rules — and
`pedal.project/docs/working-across-repos.md` says which repository owns what and how a change
reaches the pedal. Each repository's own `AGENTS.md` is authoritative inside it.

## What is here

| Directory | What it is |
|---|---|
| `pedal.project/` | The pedal as a system: hardware design, diagrams, decisions, plan, the Core host's `devices/` configuration, the Pico firmware, `pedald` |
| `namchain/` | The engine: `namchaind`, the control protocol, the soak and bench tools |
| `namchain/vendor/NeuralAmpModelerCore/` | The planar-NEON fork, vendored as a declared submodule on `all-optimisations` |
| `ljoss/` | The rig designer and the front end that drives the engine |
| `rtpi/` | The Core host's kernel, its boot-slot safety net, device-tree work |
| `NAMBench/` | NAM and IR kernel research |
| `rigpa/` | The pedal's on-device UI (C++, Qt 6), on the Core host's screen |

`.worktrees/` holds per-session git worktrees, when two agents need one repository at once.

## Rules that belong to this level

- **This directory is not a git repository and must never become one.** The six repositories are
  independent; a repository here could only record them as gitlinks, which clone as empty
  directories. Never run `git init` here.
- **Work in the repository that owns the change.** Open a session on this folder for cross-repo
  work; open one repository only when the change is confined to it (a session rooted at a
  repository cannot write its siblings).
- **A repository may be inside another repository only when it is declared** — `git submodule add`,
  which records the URL and pins the commit. A checkout dropped into a tracked path is refused by
  `pedal.project/tools/git-hooks/` rather than left to memory. Fetched vendor trees belong in that
  repository's `.gitignore`, owned by its fetch script.
- Start with `pedal.project/scripts/status`; `pedal.project/scripts/workspace check` asserts the
  layout, the root files and the git guard. `pedal.project/docs/workspace.md` is the design.
