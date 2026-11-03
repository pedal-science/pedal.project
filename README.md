# pedal.project

An open guitar, bass and vocal effects pedal that runs neural amp models: the hardware design, the
plan, and the configuration of the computers inside it. The other repositories are listed in
[workspace.repos](workspace.repos), and this one is the way in to all of them.

## Starting from nothing

This needs git and the network, and no key, account or existing checkout:

```bash
curl -fsSL https://raw.githubusercontent.com/pedal-science/pedal.project/main/scripts/bootstrap | bash
```

That makes `~/code.local/pedal/` with every repository in it, ready to work in. Then open a session
on that folder, or tell an agent in an empty one: *"Clone github.com/pedal-science/pedal.project, run
its scripts/bootstrap, and follow AGENTS.md."*

[AGENTS.md](AGENTS.md) is where to go next, for people as well as agents.
[docs/operations-plan.md](docs/operations-plan.md) is how the project is run, and
[docs/workspace.md](docs/workspace.md) explains the layout.
