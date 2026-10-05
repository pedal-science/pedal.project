# The header UART came up disabled after a card rewrite, and the pedal now owns it

**Date:** 2026-10-05
**Question:** pedald had been running since the re-pave, but the Pico's link was dead and `/status`
read `session: false`. The service was fine; `/dev/ttyAMA0` did not exist.

## What was wrong

RP1's UART0 — `/axi/pcie@1000120000/rp1/serial@30000`, the 40-pin header's pins 8 and 10 — was in
the device tree but **disabled**:

```
serial@30000 {
    compatible = "arm,pl011-axi";
    clocks = <…>; clock-names = "uartclk", "apb_pclk";
    pinctrl-names = "default"; pinctrl-0 = <0x2a>;   /* the GPIO14/15 group */
    status = "disabled";
};
```

with no `1f00030000.serial` line in dmesg at all, and only `ttyAMA10` (the console) and `ttyS0`
(Bluetooth) present. So the PL011 never probed, pedald logged `cannot open /dev/ttyAMA0: No such
file or directory` from its first attempt of the boot, and the Pico — correctly — went back to
`sent hello` once a second with nobody to answer.

**Not the cause**, checked one by one:

| Suspect | Verdict |
|---|---|
| The DTB in the boot slot | Both slots carry `1d1988ef…`, byte-identical to the stock DTB that booted with `ttyAMA0` working on 2026-10-04 |
| The tree's boot template | rtpi's `vip-boot` has written `enable_uart=1` and never a `uart0` overlay; its history shows no removal |
| Which config the firmware reads | `autoboot.txt` on BOOTSEL points at partition 2, and partition 2's `config.txt` does say `enable_uart=1` |
| The service | pedald does the right thing throughout: one log line per state change, backoff, HTTP still up, engine untouched |

What did change is the boot environment: `autoboot.txt` was rewritten **2026-10-05 20:42** by the
overnight card/re-paving work, and `enable_uart=1` has not been enough since. The bootloader's own
version could not be read from the pedal root — `vcgencmd` is not installed and neither is the
eeprom package — so whether the firmware changed is still open.

## The fix

The pedal enables the peripheral it depends on itself, the way it already does for the codec:

- `devices/common/rootfs/etc/pedal/uart/uart0-enable.dts` — an overlay that sets `status = "okay"`
  and the same `pinctrl-0` the card's own `uart0-pi5.dtbo` sets (the base DTB exports the `uart0`
  and `uart0_pins` symbols, and the node already carries its clocks and interrupt).
- `devices/common/rootfs/usr/local/sbin/pedal-uart` + `pedal-uart.service` — loads it at boot,
  `Before=pedald.service`, skipping it when configfs already has it.
- `pedal-device` enables and restarts it with the rest, and reverts it.

Tested on the running host before it was committed, with no reboot:

```
$ dtoverlay -d /tmp/pedal-uart uart0-enable
$ ls -l /dev/ttyAMA0
crw-rw---- 1 root dialout 204, 64 … /dev/ttyAMA0
[ 3639.647991] 1f00030000.serial: ttyAMA0 at MMIO 0x1f00030000 (irq = 123, base_baud = 0) is a PL011 AXI
```

and pedald picked it up on its next retry:

```
21:50:45 pedald: /dev/ttyAMA0 open at 115200 baud
21:50:45 pedald: Pico says hello: fw '0.1', protocol 1.0, caps 0x0000
```

| | |
|---|---|
| `/status` | `open true`, `session true`, `frames_ok` rising, `frames_bad 0`, `pico {fw '0.1'}` |
| The Pico's console | `session=1`, `proto: ping 25 -> pong`, `proto: pong 117` — both directions |
| Pin mux | `pin 14/15 … function uart0` |
| The engine | untouched: `running`, `ok`, `xruns 0` |

## Still open

`dtoverlay=uart0` in the boot partition's `config.txt` — durably, in rtpi's `vip-boot` template
beside `enable_uart=1` — would bring the node up before any service runs, and is the canonical Pi
way. It is not needed for the link (the pedal's overlay covers it) but it would mean a freshly
written card has the UART without depending on this unit, and it is worth doing when the boot area
is next touched. Why `enable_uart=1` stopped being honoured is the more interesting question: if
the bootloader was updated on 2026-10-05, other firmware behaviour may have moved with it.
