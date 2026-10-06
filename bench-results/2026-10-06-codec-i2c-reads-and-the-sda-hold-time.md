# The codec's I2C reads, the SDA hold time, and a wedged RP1 controller

2026-10-06. Two questions, on the bench: can the WM8960's registers be read at all now that
`i2c-tools` is on vip, and is an SDA hold time the thing that makes reads work? The second was
tried and answered — **no** — and the attempt wedged the I2C bus in a way that is worth writing
down, because it says where the fault actually is.

Instrument: `scripts/diag --host vip` for the pedal's own account, `i2cget` 4.4 on vip, `pinctrl`
for the two bus lines, and the driver's `dev_dbg` timings through dynamic debug. Nothing here was
measured with a scope; that is the one instrument this session did not have, and it is the one the
next session should reach for.

## Reads fail; writes do not

The codec's I2C address is held by the `wm8960` driver, so a read needs `I2C_SLAVE_FORCE`:

```
# i2cget -y 1 0x1a 0x00 w
Error: Could not set address to 0x1a: Device or resource busy
# i2cget -f -y 1 0x1a 0x00 w
Error: Read failed
```

`EBUSY` without `-f` is correct (a driver holds 0x1a); `-f` is `I2C_SLAVE_FORCE`. Every read then
aborts in the controller, on every register:

```
i2c_designware 1f00074000.i2c: i2c_dw_handle_tx_abort: lost arbitration
i2c_designware 1f00074000.i2c: i2c_dw_handle_tx_abort: SDA stuck at low
```

Twenty-two of those appeared, the first at uptime 39115 s — which is exactly the first read
attempt. There were **none** in the preceding 10.9 hours, and a read of an unused address (0x20)
completes with a plain NAK and no abort, so the controller and the bus are healthy until something
reads the codec.

Writes are unaffected, measured rather than assumed: setting `Headphone` 115 → 114 → 115 through
`amixer` returned 0 both times (`amixer` reports a NAK as a write error, so 0 means the chip ACKed),
the control read back as set, the driver's cache showed `0x02/0x03 = 0x0173`, and the abort count
stayed at 22 across both writes.

## The SDA hold time does not fix it

`i2c-sda-hold-time-ns` is the one timing knob the device tree can set on this controller:
`dw_i2c_plat_probe()` converts it to cycles with the bus clock and `i2c_dw_init()` writes it to
`DW_IC_SDA_HOLD`. It was applied with a throwaway overlay against `&i2c1`, re-probing
`1f00074000.i2c` each time so the driver read it. Dynamic debug (`file i2c-designware-common.c +p`)
printed what was actually programmed:

| property | driver's own line | reads |
|---|---|---|
| 300 ns | (not printed: debug was off) | all fail, same two aborts |
| 1000 ns | `SDA Hold Time TX:RX = 200:1` | all fail, same two aborts |
| 3000 ns | `SDA Hold Time TX:RX = 600:1` | all fail, same two aborts |
| 10000 ns | `SDA Hold Time TX:RX = 2000:1` | bus wedged (below) |

The bus clock is 200 MHz, so the conversion is right and the property was honoured. It changes
nothing. Two further facts close this line of enquiry:

- a **single-message** read (`i2cget -f -y 1 0x1a`, no register write, no repeated start) fails the
  same way, so the repeated start is not the trigger either;
- the driver already applies the workaround it knows for this exact symptom —
  `i2c_dw_set_sda_hold()` forces a non-zero SDA **RX** hold with the comment "Workaround for
  avoiding TX arbitration lost in case I2C slave pulls SDA down 'too quickly' after falling edge of
  SCL". Adding TX hold on top of that does nothing.

## The 10 µs round wedged the bus, and the controller was holding SDA

At 10000 ns — 10 µs, a whole bit period at 100 kHz, well out of spec — the driver's teardown write
aborted and then everything timed out:

```
i2c_dw_handle_tx_abort: SDA stuck at low
i2c_designware 1f00074000.i2c: controller timed out
wm8960 1-001a: Failed to issue reset
wm8960 1-001a: probe with driver wm8960 failed with error -110
```

No sound card, and `namchaind` went to `state: lost` (`device_lost`, retrying every 250 ms). The two
lines said which end was at fault:

```
2: a3    pu | lo // GPIO2 = SDA1        <- held low
3: a3    pu | hi // GPIO3 = SCL1
```

Unbinding the controller driver released the pins, and **SDA went high immediately**
(`2: ip pu | hi`), then low again the moment the controller was re-bound. So the **RP1 I2C
controller**, not the codec, was holding SDA low: the codec was fine all along. Nine clocks on SCL
(the standard recovery for a slave that will not release the line) changed nothing, because the
controller re-wedges when it is enabled.

A reboot cleared it — RP1 is reset at boot — and the pedal came back whole: card up, both lines idle
high, `scripts/diag --host vip` reporting **1 info, 10 ok**. The overlays and the property went with
the reboot, so the device tree is back to its committed state.

## What this leaves

**For the pedal.** No I2C bus recovery exists on this host, which is why a wedge needs a reboot:
`i2c-recover-bus` is a no-op because the `i2c1` node has no `scl-gpios`/`sda-gpios`, and the
controller's own bus-clear feature only runs from the abort path while a wedged controller produces
timeouts instead. Adding those two GPIOs (with a GPIO pinctrl state) to the `i2c1` node in rtpi's
device tree is the change that would have saved this session.

**For the read fault.** It is not timing. What is left is the controller's read path or the codec's
read protocol, and two cheap measurements separate them: a second I2C device with a known ID
register on the same bus (if reads fail on it too, it is the controller), or two scope channels on
SDA and SCL during one `i2cget` (100 kHz, one transaction, which is all the evidence anyone needs).
That a controller can wedge on a two-device bus at 100 kHz is itself a reason to suspect the
controller rather than the codec.

**For `pedal-diag`.** Its finding for "the codec is on I2C but no card appeared" blames the I2S
leads; what actually happened was a driver probe failing with `Failed to issue reset` in `dmesg`.
The tool quotes `dmesg` elsewhere and should quote it here first.
