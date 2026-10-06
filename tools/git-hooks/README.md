# The pedal workspace's git guards

Two hooks, one rule: **a repository may be embedded in another only if it is declared.**

Installed by machine, not by repository. `~/.gitconfig` carries

```ini
[includeIf "gitdir:~/code.local/pedal/"]
	path = ~/code.local/pedal/pedal.project/tools/git-hooks/hooks.gitconfig
```

so git uses this directory as `core.hooksPath` for every repository under the workspace root —
the main checkouts and any worktree — and for nothing else on the machine. A fresh clone, a new
worktree and a repository added next year all get the guard with no step of their own. That is the
part lifeload's mechanism could not do: there the hooks were tracked but `core.hooksPath` was
local config, so a clone silently had no guard at all.

| Hook | When | What it refuses |
|---|---|---|
| `pre-commit` | before a commit is made | a staged gitlink (mode 160000) whose path is not declared in `.gitmodules` with a URL |
| `pre-push` | before refs are published | the same, judged on the tip tree of each ref being pushed |

**The rule is deliberately not "no gitlinks".** `namchain` vendors
`OptimisationWorkOnNeuralAmpModelerCore` as a declared submodule at a pinned commit, and that is
the sanctioned way to put a repository inside a repository. What is refused is the accident: a
clone dropped into a tracked directory, which git records as a gitlink and which clones as an
empty directory with nothing to say what is missing. A `.gitmodules` entry with a path but no URL
is refused too — it is just as unfetchable.

`scripts/workspace check` asserts every repository under the workspace has this directory as its
effective `hooksPath`, so a guard that has gone missing (the workspace moved, the include edited)
is reported rather than assumed. `tools/tests/test-workspace-guards` proves both directions: an
undeclared clone is refused, a declared submodule commits.

See [docs/workspace.md](../../docs/workspace.md) for the workspace this belongs to.
