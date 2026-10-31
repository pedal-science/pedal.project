# Licensing for pedal.science

## Principles

* Licensing should minimise restrictions on use

## Approach

* Software: Use the [MIT licence](https://en.wikipedia.org/wiki/MIT_License) [text](mit-licence-text)
* Hardware: Use the [CERN Open Hardware Licence, Version 2 – Permissive (CERN-OHL-P-2.0](https://cern-ohl.web.cern.ch/) [text](cern-ohl-p-2.0-licence-text)
* Website and video: Use [Creative Commons Attribution 4.0 (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/) [text](cc-by-4.0-licence-text)
* Align with the original licence[s] and terms where contributing outside of pedal.science projects
  — e.g. rtpi's kernel patches are GPL-2.0-only, like the kernel [text](gpl-2.0-licence-text)

## How a repository carries them

* One licence: a `LICENSE` file at the top level, the licence text exactly.
* Two: a `LICENSE-<licence>` file for each (`LICENSE-MIT`, `LICENSE-CERN-OHL-P`,
  `LICENSE-CC-BY-4.0`), and a `LICENSING.md` saying which paths each covers and what in the
  repository is other people's. GitHub recognises each file and lists both licences.
* A licence that covers one directory only goes in that directory, as its `LICENSE`, with a line
  in the repository's README (rtpi's `patches/`).
* The licence files are the texts exactly, with nothing added: the split lives in `LICENSING.md`.
* Third-party code keeps its own `LICENSE` beside it.

| Repository | Files |
|---|---|
| `pedal.project` | `LICENSE-MIT`, `LICENSE-CERN-OHL-P`, `LICENSING.md` |
| `comms` | `LICENSE-CC-BY-4.0`, `LICENSE-MIT`, `LICENSING.md` |
| `rtpi` | `LICENSE` (MIT), `patches/LICENSE` (GPL-2.0) |
| `namchain`, `ljoss`, `NAMBench`, `rigpa` | `LICENSE` (MIT) |
