# Early rigpa: 1.9 s off the first frame

Baseline from [the 5 s report](../2026-11-15-boot-5s-vip/README.md), then one change: stop ordering
`rigpa.service` after `namchaind.service`/`pedald.service`; start it at `basic.target` and let its
`Startup` screen show while the engine arrives. The screen condition now waits up to 5 s for the
DSI/HDMI connector instead of failing immediately, so `basic.target` is early enough.

## Measured, same card and PSU, one boot each

| Milestone (from kernel start) | Baseline | Early rigpa | Saved |
|---|---:|---:|---:|
| `rigpa.service` active | 11.423 s | 9.483 s | 1.940 s |
| rigpa first frame | 13.189 s | 11.314 s | 1.875 s |
| rigpa ready / Play | 13.690 s | 11.850 s | 1.840 s |
| `namchaind` active | 11.049 s | 11.203 s | — (starts later than the UI now) |
| `pedald` active | 11.083 s | 11.234 s | — |
| `multi-user.target` | 21.881 s | 21.977 s | — (not the screen path) |

`rigpa` now paints at 11.3 s after kernel start, ≈20.0 s from power-on (firmware ≈8.7 s + kernel
start + 11.3 s), instead of ≈21.9 s. `startup: first frame` arrives 1.83 s after rigpa starts;
engine and Play arrive about half a second later, because `namchaind`/`pedald` are no longer ahead
of it.

## Change

`rigpa/packaging/systemd/rigpa.service`:

```ini
# A client of namchaind and pedald: it waits for neither (it reconnects). Do not order it after the
# engine: that put the first frame behind pedal-codec + namchaind + pedald (~2.8 s on vip). The
# Startup screen shows the starting state while the engine arrives; only basic.target has to be up.
After=basic.target
```

`pedal.project/devices/common/rootfs/etc/systemd/system/rigpa.service.d/10-pedal.conf`: the screen
`ExecCondition` now waits up to 5 s for a connected DSI/HDMI connector, so an early start at
`basic.target` does not skip before the DSI panel's DRM connector appears.

## Also measured, not kept

Masking `systemd-binfmt.service` and its automount (a 462 ms item on the old critical chain) did
not move the screen: first frame 11.293 s vs 11.314 s, within boot-to-boot noise; the masks were
reverted. The 1.9 s win is from the ordering, not from shaving `basic.target`.

Ordering only after `systemd-udevd.service` instead of `basic.target` was also tried: systemd's
default dependencies still add `basic.target`, and the first frame was 11.728 s — no better. Kept
`After=basic.target`.

Repeated early-rigpa boots: first frame 11.314 s and 11.407 s after kernel start (baseline
13.189 s); the ≈1.9 s win is stable across the two boots. Kernel+initrd varied 5.30–5.53 s, which
is why first-frame numbers vary by ~0.1 s.

## What did not change

- Kernel + initramfs are still ≈5.3 s; the firmware still ≈8.7 s to the kernel. This is a screen
  path win only; see the 5 s report for why <5 s is not reachable.
- The 16.7 s userspace tail (`pedal-tune`/`pedal-guard`) is unchanged and does not gate the screen.
- Engine/audio still come up at their own time, now just after the first frame instead of before it.

## Reproduce

```sh
ssh vip 'systemd-analyze; systemctl show -p ActiveEnterTimestampMonotonic rigpa namchaind pedald'
ssh vip 'journalctl -b -u rigpa -o cat | grep startup:'
```

One boot each, bootloader 2026/09/25, official Pi PSU, same SD card. Kernel/initrd times vary by
±0.2 s between boots; the 1.9 s shift is larger than that.
