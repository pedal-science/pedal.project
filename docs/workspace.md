# The workspace

The pedal's software is seven repositories (rigpa joined on 2026-10-09, comms on 2026-10-19), and a session works on all of them at once. This page
says where they live, why they live that way, and what keeps the arrangement from rotting. It was
written on 2026-10-06, when the repositories moved into the workspace.

## The shape

```
~/code.local/pedal/                        ← the folder a session is opened on. Not a repository.
├── .pedal-workspace                       the marker: how scripts find this root
├── AGENTS.md, CLAUDE.md                   installed from pedal.project/workspace-root/
├── .worktrees/<session>/<repo>/            per-session git worktrees
├── .cache/                                tool caches cloned in from $HOME (scripts/sandbox-cache)
├── pedal.project/                         rikkus/pedal.project
├── namchain/                              rikkus/namchain
│   └── vendor/NeuralAmpModelerCore/       declared submodule, rikkus/OptimisationWorkOnNeuralAmpModelerCore
├── ljoss/                                 rikkus/ljoss
├── rtpi/                                  rikkus/rtpi
├── NAMBench/                              rikkus/NAMBench
├── rigpa/                                 rikkus/rigpa
└── comms/                                 pedal-science/comms
```

`pedal.project` is the only directory of that name; it is a direct child of the workspace root.
`workspace.repos` in `pedal.project` is the declaration this shape is checked against, and
`scripts/workspace` is the tool that reads it.

## Why a container, and why it is not a repository

**One writable root per session.** The harness may read anywhere, but it may write only under the
directory the session was opened on — the session's cwd *is* the sandbox's `workspace-write` root
(`packages/sandbox/sandbox-policy/src/index.ts`: "A session cwd is its workspace-write boundary"),
and a call that wants to write outside it needs approval, once, every time. There is no
additional-directory setting to configure: the policy carries exactly one root, and the ACP
implementation rejects `additionalDirectories` outright. So the only way to give an agent all five
repositories without asking is to open a directory that contains all five.

**Not a repository, because that is the one place the mistake is always available.** A checkout
inside a repository is recorded as a gitlink — a pointer to a commit with no URL — and clones as
an empty directory that says nothing about what is missing. A repository at the workspace root
would be the one repository guaranteed to contain all five and the one place where `git add -A`
costs the most. Without a `.git` there, there is no index to record anything in, so the accident
cannot happen rather than being detected afterwards.

**Not ignored either.** Hiding the child repositories in `.gitignore` or `.git/info/exclude` would
also prevent the mistake, and would cost search: lifeload measured a query finding 178 files
normally and 7 with either entry present, because ripgrep honours ignore files. A workspace whose
whole point is working across repositories cannot have its own content invisible to `rg`.

**Not submodules.** Submodules for the siblings would dirty the parent on every commit in any
child, and a submodule pins a commit into a branch that is often local-only, so a clone checks out
a state that cannot be fetched and does not fail. Both were measured in lifeload's ADR-0011. A
submodule is right for one thing only: a *vendored dependency* at a pinned commit, which is what
`namchain/vendor/NeuralAmpModelerCore` is.

## What each harness does with it

- **Open the workspace, not a repository inside it.** A session opened on `namchain/` can read its
  siblings but cannot write them, because its root is `namchain`. Open the container for
  cross-repo work; open one repository only when the change is confined to it.
- **Claude Code** needs no configuration at all. The `additionalDirectories` block and
  `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD` that used to live in
  `pedal.project/.claude/settings.local.json` existed only to work around the old layout and are
  gone.
- **DeepSeek Harness** reads `AGENTS.md` and `CLAUDE.md` from the project root down to the cwd,
  plus a user-global `~/.dsh/AGENTS.md`. With no `.git` anywhere above it, the workspace root *is*
  the project root, so `AGENTS.md` here loads first; the repository's own `AGENTS.md` loads as
  soon as a file inside it is touched (`packages/context/agent-instructions/src/state.ts` walks the
  directories between the cwd and the touched file). DSH does not expand Claude Code's `@import`
  syntax, so `CLAUDE.md` here contributes its import lines literally — they are two lines, and the
  files they name load anyway.
- **Cursor** is expected to read `AGENTS.md` at the workspace root. If it does not, the fix is a
  `.cursor/rules/pedal.mdc` pointing at the same text.

## The guard: repositories inside repositories

A repository may be inside another repository **only when it is declared** — `git submodule add`,
which records the URL in `.gitmodules` and pins the commit. That is a dependency with provenance.
Anything else is an accident, and it is the accident that fails quietly: the outer repository
commits a gitlink, the clone has an empty directory, and nothing anywhere says why.

`pedal.project/tools/git-hooks/` holds a `pre-commit` that refuses a staged gitlink whose path is
not declared with a URL, and a `pre-push` that refuses to publish a tip holding one. The rule is
deliberately not "no gitlinks": `namchain`'s vendored fork is a declared submodule and must keep
working.

It is installed by machine, not by repository. `~/.gitconfig` carries

```ini
[includeIf "gitdir:~/code.local/pedal/"]
	path = ~/code.local/pedal/pedal.project/tools/git-hooks/hooks.gitconfig
```

so git uses that directory as `core.hooksPath` for every repository under the workspace — the main
checkouts and every worktree — and for nothing else on the machine. That is the part lifeload's
mechanism could not do: its hooks were tracked in `.githooks/`, but `core.hooksPath` was *local*
config set by hand, so a clone had no guard and said nothing. Here a fresh clone, a new worktree
and a repository added next year all get it, because the guard follows the path rather than a
setup step.

The failure mode to know about: a missing include target is ignored silently by git, so if the
workspace is renamed the guard stops applying without an error. `scripts/workspace check` is what
catches that, and `scripts/status` prints it at the start of every session.

## scripts/workspace

| Command | Does |
|---|---|
| `check [--brief]` | Asserts the invariants below and prints one line per failure. `scripts/status` runs it with `--brief`. |
| `apply [--dry-run]` | Installs `.pedal-workspace`, `AGENTS.md` and `CLAUDE.md` at the workspace root from `pedal.project/workspace-root/`. Idempotent, like `devices/<host>/apply`. |
| `clone` | Clones what `workspace.repos` declares and is missing, then initialises its submodules. This is how the workspace is rebuilt on a new machine. |
| `add <url> <path>` | Adds a repository: refuses a path inside another repository and prints the `git submodule add` that would be right instead, and appends the entry to `workspace.repos` otherwise. |
| `root [--repo <name>]` | Prints the workspace root, or one repository's path, by walking up for `.pedal-workspace`. `deploy-engine`, `make-card`, `soak-replay` and `status` ask it instead of hardcoding a path. |

`root --repo` falls back to the legacy `$HOME/code.local/<name>` when there is no workspace marker,
so the scripts work on a checkout that has not moved and on piv, whose checkouts stay where they
are.

## What `check` asserts

1. The workspace root is not inside a git repository, and has no `.git` of its own.
2. Every `workspace.repos` entry is present, is a repository, and its `origin` is that repository
   (compared as host and path, so `https` and `ssh` spellings compare equal).
3. A `submodule` entry is declared in its parent's `.gitmodules` **with a URL**, and is checked
   out. A detached HEAD is normal after a clone and is reported, not failed.
4. No repository has a gitlink in its index or in `HEAD` that nothing declares.
5. Every repository's effective `core.hooksPath` is the guard directory, and the hooks are there.
6. `.pedal-workspace`, `AGENTS.md` and `CLAUDE.md` at the root match `pedal.project/workspace-root/`.
7. No worktree is registered outside the workspace: one outside it would be outside the sandbox and
   outside the guard.
8. Nested repositories that are gitignored are reported as information — they are fetched
   dependencies, and NAMBench has nine of them.

## Worktrees

Two agents on one repository each get a git worktree, under `<workspace>/.worktrees/<name>/<repo>`.
That directory is hidden, so ripgrep skips it; it is outside every repository, so it needs no
`.git/info/exclude` entry and creates no `git status` noise; it is inside the workspace, so it is
writable and the guard covers it (`gitdir:` matches a worktree's administration directory, which
lives inside its main repository).

A worktree whose main repository is *outside* the workspace would not be covered. The check
reports that case, and the four worktrees that existed before the move were removed rather than
carried across, because their registrations hold absolute paths.

## Adding the next repository

`scripts/workspace add <url> <path>` is the whole procedure. It refuses to put a checkout inside
another repository's tree and says what to do instead: declare it as a submodule if that
repository needs it at a commit, or ignore the path and let that repository's fetch script own it
(which is what NAMBench does with its nine vendor clones). If the new repository is a sibling, it
lands at the workspace root and appears in `workspace.repos` so that `check` keeps checking it.

## Alternatives that were rejected, and why

- **A repository at the workspace root, guarded by the hook.** Reintroduces the mistake at the one
  level that contains everything, needs the guard rather than being safe by construction, shows
  the children as untracked for ever, and puts `git clean -xfd` beside five live repositories. It
  buys almost nothing: with the children untracked, a git-backed change summary at that level has
  nothing to show.
- **Submodules for the siblings.** See above: ADR-0011's two measured problems.
- **Ignoring the children.** Search loss, measured.
- **Opening `~/code.local` itself.** It contains about fifty other projects, which would all become
  writable, and the workspace would have no boundary to check.
- **`danger-full-access`.** Turns the sandbox off for everything rather than answering the
  question, which is where the work lives.
