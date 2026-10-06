# i2c-slave — a known-register device for the bench

A bench instrument, not part of the pedal: an RP2350 acting as an I2C slave with a register map we
wrote, so a read of it on vip's bus can be compared with a read of the codec. It exists because
every read of the WM8960 aborts in the RP1 controller — lost arbitration, SDA stuck at low — while
writes have been clean for hours, and the codec is the only device on that bus, so nothing could
separate "the controller cannot read" from "this codec cannot be read"
([bench-results/2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md](../../../bench-results/2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md)).

## The register map

16-bit registers, big-endian on the wire (MSB first — the order the WM8960 answers a word read in),
auto-incrementing like a memory:

| Register | Value | Why |
|---|---|---|
| `0x00` | `0xDEAD` | the identity word |
| `0x01` | `0x2152` | its bitwise complement, so a stuck or half-read bus cannot satisfy both |
| `0x02` | seconds since reset | a **live** value: read it twice a second apart and it must change. A read path that returns stale bytes fails this and passes the first two |
| `0x03` | writable | exercises the write path on the same device |

## Build and flash (on the Mac)

```sh
firmware/bench/i2c-slave/build.sh     # -> build/i2c-slave.uf2
firmware/bench/i2c-slave/flash.sh     # the bench Pico only, see the warning below
```

**Only the bench Pico may be plugged into the Mac when flashing**: `picotool` writes to whatever is
on the other end, and this firmware would take the pedal's controls away. The pedal's own firmware
is `firmware/build.sh` + `firmware/flash.sh`, a different UF2 in a different build directory.

## Wire it to vip's header

Both ends are 3.3 V logic; no level shifting. Power it from the header so the Mac is not in the
loop and there is no second ground path:

| Bench Pico 2 W | Core host 40-pin header |
|---|---|
| pin 6 (GP4, SDA) | pin 3 (GPIO2, SDA1) |
| pin 7 (GP5, SCL) | pin 5 (GPIO3, SCL1) |
| pin 8 (GND) | pin 6 (GND) |
| pin 39 (VSYS) | pin 2 (5 V) |

The pedal's own Pico keeps its UART link and is not touched. The codec stays where it is, at
`0x1a`; this answers at `0x2a`.

## If nothing answers: the self-test

`transactions=0` on the console after a bus scan means the slave's peripheral saw no start condition
at all. That is either "the signals never arrive" or "this firmware is not listening", and the
counter alone cannot tell them apart. The self-test can, with no other hardware:

1. Jumper the two I2C pairs on the *Pico itself*: GP2 to GP4, GP3 to GP5.
2. Build and flash the variant whose other block is a master:

```sh
export PICO_TOOLCHAIN_PATH=$HOME/pico/arm-gnu-toolchain-15.3.rel1 PICO_SDK_PATH=$HOME/pico/pico-sdk
PATH=$PICO_TOOLCHAIN_PATH/bin:$PATH cmake -S firmware/bench/i2c-slave -B /tmp/selftest \
  -G Ninja -DPICO_BOARD=pico2_w -DSLAVE_SELFTEST=1 && cmake --build /tmp/selftest
```

The console then prints, every two seconds, what it read back from its own slave register `0x00`:

```
i2c-slave: selftest -> 2 byte(s) 0xdead (want 0xdead); slave has seen 1 transaction(s)
```

`0xdead` and a rising counter prove the peripheral, the event handler, the register map and the
counters. If they hold, the firmware is not the problem and the fault is in the wiring between the
Pico and the Core host. If they do not, no amount of rewiring will help and the fault is here.

The same switches reposition the slave on the other pair, for a suspected dead pad:
`-DSLAVE_I2C=1 -DSLAVE_SDA=2 -DSLAVE_SCL=3` puts it on i2c1 (GP2/GP3) instead of i2c0 (GP4/GP5).

## The measurement

With the campaign (or any soak) finished — the Core host is shared, so this waits for its lock:

```sh
ssh vip 'sudo i2cget -f -y 1 0x2a 0x00 w'    # expect 0xdead
ssh vip 'sudo i2cget -f -y 1 0x2a 0x01 w'    # expect 0x2152
ssh vip 'sudo i2cget -f -y 1 0x2a 0x02 w'; sleep 1
ssh vip 'sudo i2cget -f -y 1 0x2a 0x02 w'    # the two must differ
ssh vip 'sudo i2cget -f -y 1 0x1a 0x00 w'    # the codec, for contrast: fails today
ssh vip 'sudo dmesg | grep i2c_dw_handle_tx_abort | tail -4'
```

| What comes back | What it means |
|---|---|
| `0xdead`, `0x2152`, and a counter that moves | the controller, the bus and the pins read fine, so **the codec's read is the fault** — its protocol, its board, or the part |
| the same `lost arbitration` / `SDA stuck at low` aborts as the codec's reads, for `0x2a` too | **the controller's read path is the fault**, whatever is on the other end |
| a clean NAK (`no acknowledgment`, no abort) for `0x2a` | the slave is not answering at all — check the four leads, that the Pico is powered and its console says `i2c-slave: up`, and that `i2cdetect` sees `2a` before reading anything into it |

Whichever way it goes, the result belongs in `bench-results/`.
