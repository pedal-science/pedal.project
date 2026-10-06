# The five repositories become one workspace

**Date:** 2026-10-06
**Question:** working on the pedal means working in five repositories at once, and they were
siblings in `~/code.local/` — outside whatever folder a session was opened on. Every harness this
is done under grants writes only under the directory the session is opened on, so an agent could
read its siblings and not write them: Claude Code carried a per-machine `.claude/settings.local.json`
listing them as additional directories, and the DeepSeek harness asks for approval on each write
outside its one root. That is the first half. The second half is that repositories must not end up
inside one another: an easy mistake with a silent result, where the outer repository commits a
gitlink — a pointer with no URL — and a clone gets an empty directory that says nothing about what
is missing. lifeload's guard against that works but is a per-clone `core.hooksPath` set by hand, so
a clone silently has no guard at all.

**In one line:** everything the pedal is made of now lives in `~/code.local/pedal/`, one folder a
session is opened on, which is deliberately not a repository; a git guard installed *by path* in
`~/.gitconfig` refuses a commit or a push that embeds a repository nothing declares; and
`scripts/workspace check`, which `scripts/status` prints at the start of every session, asserts the
layout, the declaration and the guard. The design, and the alternatives with the measurements that
rejected them, is [docs/workspace.md](../docs/workspace.md).

## The evidence here

| File | Is |
|---|---|
| `before.txt` | every repository's HEAD, branch, upstream, dirty set, worktree list and submodule state, immediately before the move |
| `after.txt` | the same afterwards, with the new path folded back to the old one so the two diff cleanly |
| `guard-acceptance.txt` | the guard firing in the live workspace: an ordinary commit allowed, a clone dropped into a tracked directory refused |

The diff between the snapshots is the whole change: five HEADs moved by the commits made in this
session, four worktrees gone, two files added to NAMBench, twelve to `pedal.project`, and nothing
else. Every branch survived, including the local-only `x/*` and `local-engine` ones, and
`namchain`'s vendored submodule is at the same commit as before.

## What was established before anything moved

The harness was read rather than assumed, because the whole design rests on it:

- A session's sandbox policy holds **one** root, and a session resolves it from its own cwd:
  `resolveWorkspaceRoot(session?.header.cwd ?? this.workspaceRoot)`, "A session cwd is its
  workspace-write boundary" (`packages/sandbox/sandbox-policy/src/index.ts`). The configured
  `workspaceRoot` is the fallback for calls with no session, not a second root.
- `workspace-write` grants that root as a **subtree** plus `/tmp` and the per-user temp dir
  (`packages/sandbox/sandbox/src/roots.ts`), so everything under the opened folder is writable —
  and a session opened on a repository *inside* the workspace cannot write its siblings.
- There is no additional-directory facility: the ACP implementation rejects
  `additionalDirectories` outright, and no `--add-dir`-style flag exists. A parent directory is
  the only zero-config answer.
- Instruction files load from the project root **down to the cwd**, and a repository's own
  `AGENTS.md` loads when a file inside it is touched
  (`packages/context/agent-instructions/src/{files,state}.ts`). With no `.git` above it, the
  workspace root is the project root, so `AGENTS.md` there loads first. DSH does not expand
  Claude Code's `@` imports, so the pointer `CLAUDE.md` contributes its two import lines
  literally — harmless, and worth knowing.
- `~` **is** expanded in `core.hooksPath` (measured with git 2.54: a hook at `~/…/pre-commit` runs
  from a commit), and a *missing* include target is ignored silently — which is why the guard's
  absence has to be checked rather than assumed.
- An `includeIf "gitdir:~/code.local/pedal/"` block matches a repository under the workspace **and
  a worktree of one** (whose `.git` is a file pointing into the main repository), and matches
  nothing else on the machine.

## What moved, and what did not

The five repositories are `pedal.project`, `namchain` (with its declared submodule
`vendor/NeuralAmpModelerCore`), `ljoss`, `rtpi` and `NAMBench`. `midi-commander-custom` stays in
`~/code.local/comidi/` — a peripheral, with two other people's clones beside it — and the NAM
research checkouts stay in `~/code.local/nam/`, where NAMBench's `fetch-vendor.sh` expects them.
`piv`'s checkouts do not move either: the workspace is the Mac's layout, and
`scripts/workspace root --repo` falls back to `$HOME/code.local/<name>` so the scripts work in
both places.

Two things were removed rather than carried across, both verified first: the four registered
worktrees (three under `.claude/worktrees/`, one in `/private/tmp/base`, all clean and every
commit reachable from a branch — their gitdir registrations are absolute paths and a move orphans
them), and `~/cursor-projects/pedal.project`, a second checkout that held no commit the workspace
checkout did not.

## Commits

| Repository | Commit | Is |
|---|---|---|
| `pedal.project` | `44f049b` | the declaration, the guard, `scripts/workspace`, the docs, and the path fixes |
| `namchain` | `3933713` | the pointer in `AGENTS.md` |
| `ljoss` | `175f925` | the compiled default `namchaind` path, now resolved from its own file path; `Tools/levels/signals.py`; `AGENTS.md` |
| `rtpi` | `5940267` | the pointer in `AGENTS.md` |
| `NAMBench` | `dbe7e12` | `AGENTS.md` and `CLAUDE.md`, which it had never had |

All five are local and unpushed, waiting for the owner's say-so.
