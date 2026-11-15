# No-initramfs kernel trial on vip

**Result: not viable as built; reverted.** The initrd is not just a filesystem-loading
convenience on this board — it is what loads the SD host driver after the RP1/PCIe resources are
ready. Building the same drivers into the kernel makes the driver probe too early and fail.

## What was built

Kernel `7.0.0-1017-raspi-realtime-nofs3-trimmed` from rtpi, with the stock config plus:

```
CONFIG_MMC_BLOCK=y
CONFIG_RPMB=y                     # required for MMC_BLOCK=y: depends on RPMB || !RPMB
CONFIG_MMC_SDHCI_BRCMSTB=y
CONFIG_MMC_SDHCI_IPROC=y
CONFIG_EXT4_FS=y
```

(The first attempt left `CONFIG_MMC_BLOCK=m` because `CONFIG_RPMB=m` prevents the block driver
from being built in; adding `CONFIG_RPMB=y` after the module trim fixed it.) Artifacts:
14 MB boot tarball, 4.9 MB modules, release `...-nofs3-trimmed`.

## What happened

With the candidate kernel the bootloader reached `Starting OS` at 8.047 s, then the kernel
reported:

```
[    1.306844] sdhci-brcmstb 1001100000.mmc: error -EINVAL: invalid resource (null)
```

The built-in `sdhci-brcmstb` probes at 1.3 s, before the RP1/PCIe resources exist; no SD block
device appears, so there is no root filesystem. The board fell back to slot b (the stock kernel
with its normal initrd). The same driver loaded from the initrd works because dracut loads it
after RP1/PCIe are up.

A hand-built 1.1 MB BusyBox initramfs cut the firmware's initrd read enough for
`Starting OS 7093 ms` (vs 8.05 s), but it never mounted the root; the custom `/init` was not
reached reliably and the attempt was abandoned. (A separate empty-initrd trial also failed; the
kernel does not fall back to the root filesystem when an initramfs is present but has no
`/init`.)

## Conclusion

- **No-initrd kernel: blocked by driver probe order.** The SD host driver must remain a module
  loaded from the initrd (or its probe must be deferred until RP1/PCIe resources are ready).
- **The initrd can still be made much smaller/simpler.** A minimal initramfs containing only
  BusyBox plus the four storage modules (`mmc_block`, `rpmb-core`, `cqhci`, `sdhci-brcmstb`)
  is ~1 MB. Getting its `/init` to mount `/dev/mmcblk0p5` and `switch_root` is the remaining
  problem; that path is worth debugging with the Debug Probe now on piv (`/dev/ttyACM0`), not
  with the built-in-driver kernel.
- Firmware saved by the 1 MB initrd alone: `Starting OS` 8.05 → 7.09 s. The bigger prize is
  removing dracut's 2.5 s userspace initrd time.

The candidate was removed from the root, the original 21 MB initrd is back, and slot b is the
running/default slot. EEPROM/quiet/early-rigpa changes are unchanged.
