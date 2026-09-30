# The WM8960 on vip: first bring-up, 2026-09-29

The codec board as wired for 2a on piv, moved to vip's header unchanged. Checked from the spike card
(stock `7.0.0-1017-raspi`), with piv's overlay and mixer state (`devices/piv/rootfs/etc/pedal/codec/`).
Nothing played: capture only.

| Check | Seen | Means |
|---|---|---|
| Load `wm8960-codec-master.dtbo` (compiled in the build container, `dtoverlay -d`) | `wm8960 1-001a` probes; card 0 `wm8960`, `1f000a4000.i2s-wm8960-hifi` | the codec answers on I2C bus 1 at 0x1A, and the simple-audio-card forms on the Pi 5's I2S |
| Apply `wm8960.mixer` (`amixer -s`) | applied; Headphone −6 dB, Speaker 0 | piv's mixer state carries over |
| Register 7 (audio interface) | `0x004e`: MS=1, 32-bit, I2S | **the codec is clock master** |
| Register 4 (clocking) | `0x0005`: SYSCLK from the PLL | its PLL makes 48 kHz from the board's 24 MHz |
| `arecord` 3 s, S32_LE, 48 kHz, 2 ch | 3.54 s wall, 1,152,044 bytes (1,152,000 + header) | clocks run at real time from the codec |

## For step 3

- `dtoverlay` is packaged in resolute (`raspi-utils-dt`, with `libdtovl0`). **piv's
  `/usr/local/bin/dtoverlay` and `/usr/local/lib/libdtovl.so*` were built by hand (2026-09-06) and
  aren't recorded anywhere**; `devices/piv/` should install the package instead.
- `dtoverlay -l` fails on vip ("Failed to find overlays directory": it looks in
  `/boot/firmware/overlays`, which vip's slot layout doesn't have). `pedal-codec` uses that listing
  to avoid loading twice; on vip it should look in `/sys/kernel/config/device-tree/overlays/`.
- Compile the overlay at image build; vip needs no `dtc`.
