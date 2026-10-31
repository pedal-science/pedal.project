# Licensing

This repository holds both software and hardware, so it carries two licences, chosen by the
pedal.science policy in [licensing/README.md](licensing/README.md). Both are permissive.

| Licence | Text | Covers |
|---|---|---|
| MIT | [LICENSE-MIT](LICENSE-MIT) | Everything not listed below: `devices/`, `firmware/`, `scripts/`, `tools/`, the pedal service, the docs about software, bench results |
| CERN-OHL-P-2.0 | [LICENSE-CERN-OHL-P](LICENSE-CERN-OHL-P) | The hardware design: `schematic/`, `stripboard/`, `breadboard/`, `enclosure/`, `docs/wiring/`, `docs/diagrams/` (except `plan-dependency-graph.html`), and the hardware docs — `docs/hardware-handoff.md`, `docs/bom.md`, `docs/build-*.md`, `docs/modules.md`, `docs/module-boards.md`, `docs/board-a-netlist.md`, `docs/balanced-outputs.md`, `docs/codec-bringup-*.md` |

The scripts in the hardware directories (`stripboard/board1.py`, `schematic/case-wiring.py` and
the rest) are under CERN-OHL-P with the design they hold: they are where the layouts and the
wiring live, which is what the licence calls Source.

Copyright 2026 Rik Hemsley. Source location: https://github.com/pedal-science/pedal.project

## Not ours

These are other people's work, kept for reference, and stay under their owners' terms:

- `references/` — makers' schematics, datasheets and drawings (SparkFun, Neutrik, the display
  module's seller)
- `imaginings/` — makers' drawings and photographs among the sketches
- `pi5/`, `pico2w/` — Raspberry Pi's pinout diagrams
