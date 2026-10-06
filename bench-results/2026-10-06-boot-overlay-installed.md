# The I2C recovery overlay is on vip's card, and in every card from now on

2026-10-06. Two halves of one thing: `rp1-i2c1-recovery.dts` existed and was proved to arm the
DesignWare driver's bus recovery, but it was in no boot partition, so a bus held low still cost a
reboot — and a card written from the image would not have carried it either.

## What was done

**rtpi now installs it.** `vip-boot init-pedal-boot` and `init-rescue-boot` compile every
`*.dts` in `devices/vip/dt/` with `dtc` and copy the `.dtbo` into each boot tree's `overlays/` —
slot `a` and slot `b` of the pedal partition, and the rescue partition's — then enable each one
with a `dtoverlay=` line in that partition's `config.txt`. The config and the files are written
from the same list, so they cannot disagree, and `--dt-dir` overrides where the sources are read
from (the tests use it). A `.dts` that will not compile **stops the build** rather than shipping a
card without it. `device-tree-compiler` was added to the build container's packages, since that is
where the compile happens.

Why this and not a runtime overlay like the pedal's own (`pedal-uart`, `pedal-codec`): the driver
reads `scl-gpios`/`sda-gpios` once, at probe, which is long before any systemd unit runs. A
runtime overlay only takes effect after an unbind/bind of `1f00074000.i2c`, which is how the arming
was proved on 2026-10-06 but is not something to do at every boot.

**vip's card was updated by hand**, because its config.txt predates the mechanism (it does not even
carry the `dtoverlay=uart0` line that vip-boot has written since 2026-10-05 — the card has never
been rewritten since). The three steps, on the host, exactly what vip-boot would do:

```sh
# compile (dtc is in devices/vip/packages, so the pedal root has it)
dtc -q -@ -I dts -O dtb -o /var/tmp/rp1-i2c1-recovery.dtbo /var/tmp/rp1-i2c1-recovery.dts

mount -o rw,noatime LABEL=PEDAL-BOOT /mnt/peek
install -m 644 /var/tmp/rp1-i2c1-recovery.dtbo /mnt/peek/a/overlays/
install -m 644 /var/tmp/rp1-i2c1-recovery.dtbo /mnt/peek/b/overlays/
# then append to /mnt/peek/config.txt, in its last [all] section:
#   dtoverlay=rp1-i2c1-recovery
sync && umount /mnt/peek

mount -o rw,noatime LABEL=RESCUE-BOOT /mnt/peek
install -m 644 /var/tmp/rp1-i2c1-recovery.dtbo /mnt/peek/overlays/
# the same line appended to that config.txt
sync && umount /mnt/peek
```

Verified by remounting both read-only: `a/overlays/rp1-i2c1-recovery.dtbo` and
`b/overlays/rp1-i2c1-recovery.dtbo` (833 bytes each), rescue's `overlays/` likewise, and the line
present in both `config.txt` files. Nothing else on the card was touched, and no mount was left
behind.

## What is proved, and what is not

Proved: the code path works with real `dtc` — rtpi's `tests/vip-boot` gains a test that runs
`init-pedal-boot` (both slots, fallback kernel) and `init-rescue-boot` against a temporary overlay
and asserts the `.dtbo` and the `dtoverlay=` line in each, plus a test that a broken `.dts` fails
the build. Both were run **on vip**, where `dtc` exists, because the Mac has no `dtc`:

```
Ran 10 tests in 4.204s
OK
```

Not proved: that the firmware applies it and the driver arms at boot. That needs a reboot, and a
levels campaign held the Core host's lock for this session (`scripts/host-lock`, 16:03Z), so the
next reboot is the test. What to look for:

```sh
dmesg | grep "GPIO recovery mode"     # i2c_designware 1f00074000.i2c: running with GPIO recovery mode! scl,sda
pinctrl 2,3                            # both lines idle high
```

The arming itself was already seen once, at runtime, with the same overlay
([2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md](2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md)).

## Reverting

Mount each partition read-write, delete `rp1-i2c1-recovery.dtbo` from the boot trees it was put
in, and delete the four-line block ending in `dtoverlay=rp1-i2c1-recovery` from `config.txt`. A
card written from the image after this commit carries it again — the image and the hand install
now say the same thing, which is the point of doing both.

## Left alone on purpose

- `dtoverlay=uart0` is absent from vip's card for the same reason, and the pedal boots fine
  without it because `pedal-uart.service` loads an equivalent overlay at runtime. Adding it to a
  live card is a second boot-affecting change with a test (a reboot) this session could not run,
  so it was not bundled with this one.
- The read fault itself is unchanged: the codec still cannot be read (see the note above), and the
  recovery being armed does not make reads work — it makes a wedge survivable.
