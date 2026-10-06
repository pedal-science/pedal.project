// A known-register I2C slave, for the bench.
//
// The one question this project cannot answer from software alone is "is it the controller or the
// device?". Every read of the WM8960 aborts in the RP1 controller (lost arbitration, SDA stuck at
// low) while writes are clean, and none of the suspects can be eliminated with the pedal's own
// hardware: the codec is the only device on the bus
// (pedal.project bench-results/2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md).
//
// So this is a second device with a register map that is known because we wrote it. Hang it on the
// same two wires as the codec, read it with the same `i2cget -f -y 1 0x2a <reg> w`, and:
//
//   its registers read back            -> the controller, the bus and the pins are fine, and the
//                                         codec's read protocol (or the codec) is the fault
//   the same aborts as the codec's     -> the controller's read path is the fault, whatever the
//                                         device on the other end is
//
// The map is deliberately awkward to fake. R0 and R1 are bitwise complements, so a stuck or
// half-read bus cannot satisfy both; R2 counts seconds, so a read that returns the same value
// twice a second apart did not come off the wire; R3 takes writes, so the write path can be
// exercised too.
//
// Wire it (both ends 3.3 V logic, no level shifting):
//
//   Pico 2 W physical pin  6  (GP4)  -> Core host header pin 3  (GPIO2, SDA1)
//   Pico 2 W physical pin  7  (GP5)  -> Core host header pin 5  (GPIO3, SCL1)
//   Pico 2 W physical pin  8  (GND)  -> Core host header pin 6  (GND)
//   Pico 2 W physical pin 39 (VSYS)  -> Core host header pin 2  (5 V)
//
// Powering it from the header keeps the Mac out of the loop, so there is no second ground path
// and no USB cable to unplug mid-measurement. Build and flash it while it is on the Mac, then move
// the four leads.
//
// SDK 2.3.1, board pico2_w, USB stdio: the same environment the pedal firmware is built in.
#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"
#include "hardware/i2c.h"
#include "pico/i2c_slave.h"
#include "pico/cyw43_arch.h"

#ifndef SDA_PIN
#define SDA_PIN 4          /* i2c0's SDA on the Pico */
#endif
#ifndef SCL_PIN
#define SCL_PIN 5          /* i2c0's SCL */
#endif
#ifndef SLAVE_I2C
#define SLAVE_I2C 0
#endif
#if SLAVE_I2C == 1
#define SLAVE_INST i2c1    /* the other pair: GP2/GP3, for a suspected dead pad */
#else
#define SLAVE_INST i2c0
#endif
#define SLAVE_ADDRESS 0x2a

/* Self-test: with two jumpers between the two I2C pairs (see the README), the *other* block acts as
 * a master and reads this slave's register 0x00 the way i2cget does — register byte, repeated
 * start, two bytes back. It proves the peripheral, the event handler, the register map and the
 * counters on their own, with no other hardware in the loop, which is the difference between "the
 * firmware is not listening" and "nothing reaches the pins". */
#ifndef SLAVE_SELFTEST
#define SLAVE_SELFTEST 0
#endif
#if SLAVE_SELFTEST
#if SLAVE_I2C == 1
#define MASTER_INST i2c0
#define MASTER_SDA 4
#define MASTER_SCL 5
#else
#define MASTER_INST i2c1
#define MASTER_SDA 2
#define MASTER_SCL 3
#endif
#endif

#define REGISTERS 16

// R0/R1 are complements, R2 is a live seconds counter, R3 is scratch for writes. The master
// selects a register by *number* (0x00, 0x01, ...), as the WM8960 does, and the value goes out
// big-endian (MSB first), which is also the WM8960's order — the point is to look like the codec's
// transactions on the wire, not merely to be readable. Note that `i2cget ... w` prints an SMBus
// word low byte first, so R0 reads back as 0xadde, not 0xdead.
static volatile uint16_t regs[REGISTERS] = {
    0xDEAD, 0x2152, 0x0000, 0x0000,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
};

// What the master has actually done to us. "Transactions" is one per completed transfer, so a
// console that shows it climbing while nothing answers on the bus means the address and the wiring
// reach the slave and the problem is in the reply; a console that shows zero means the master's
// transactions never arrive. That distinction is the first thing to look at from the bench.
static volatile uint32_t transactions = 0;
static volatile uint32_t bytes_in = 0;
static volatile uint32_t bytes_out = 0;

static volatile uint8_t selected = 0;   // the byte the master put in a write, or the running read
static volatile uint8_t byte_in_reg = 0;
static volatile bool have_selection = false;

// The selection byte is a register number, not a byte offset: 0x01 means R1. Treating it as a byte
// offset reads back the register below the one asked for, which is exactly what the first working
// run did — the values looked plausible and were wrong by one.
static inline unsigned reg_index(uint8_t sel) { return sel & (REGISTERS - 1); }

static uint8_t reg_byte(uint8_t sel, unsigned off) {
    uint16_t v = regs[reg_index(sel)];
    return off ? (uint8_t)(v & 0xff) : (uint8_t)(v >> 8);
}

static void reg_store(uint8_t sel, unsigned off, uint8_t b) {
    unsigned i = reg_index(sel);
    uint16_t v = regs[i];
    regs[i] = off ? (uint16_t)((v & 0xff00) | b) : (uint16_t)((b << 8) | (v & 0x00ff));
}

// The SDK's slave handler: RECEIVE for every byte the master wrote, REQUEST for every byte it wants
// back, FINISH on the STOP that ends a transfer.
static void i2c_slave_handler(i2c_inst_t *i2c, i2c_slave_event_t event) {
    switch (event) {
    case I2C_SLAVE_RECEIVE: {
        uint8_t b = i2c_read_byte_raw(i2c);
        bytes_in++;
        if (!have_selection) {
            // The first byte of a write is the register address, exactly as the WM8960's protocol
            // has it; everything after it is data, big-endian, auto-incrementing like a memory.
            selected = b;
            byte_in_reg = 0;
            have_selection = true;
        } else {
            reg_store(selected, byte_in_reg, b);
            if (++byte_in_reg > 1) {
                byte_in_reg = 0;
                selected = (uint8_t)((selected + 1) & (REGISTERS - 1));
            }
        }
        break;
    }
    case I2C_SLAVE_REQUEST:
        // A read repeats the last write's register address, then walks forward two bytes at a time.
        i2c_write_byte_raw(i2c, reg_byte(selected, byte_in_reg));
        bytes_out++;
        if (++byte_in_reg > 1) {
            byte_in_reg = 0;
            selected = (uint8_t)((selected + 1) & (REGISTERS - 1));
        }
        break;
    case I2C_SLAVE_FINISH:
        have_selection = false;
        byte_in_reg = 0;
        transactions++;
        break;
    default:
        break;
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(1500);     // let the USB console come up before the banner

    i2c_init(SLAVE_INST, 100 * 1000);
    gpio_set_function(SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(SDA_PIN);
    gpio_pull_up(SCL_PIN);

    i2c_slave_init(SLAVE_INST, SLAVE_ADDRESS, i2c_slave_handler);
#if SLAVE_SELFTEST
    i2c_init(MASTER_INST, 100 * 1000);
    gpio_set_function(MASTER_SDA, GPIO_FUNC_I2C);
    gpio_set_function(MASTER_SCL, GPIO_FUNC_I2C);
    gpio_pull_up(MASTER_SDA);
    gpio_pull_up(MASTER_SCL);
#endif

    // The LED is the only sign of life when it is powered from the header with the USB lead out,
    // and "is the firmware running at all" is the first question when nothing answers on the bus.
    // On a W board the LED lives on the wireless chip, so this needs cyw43; it is not needed for
    // anything else here.
    bool led_ready = cyw43_arch_init() == 0;

    printf("i2c-slave: up, i2c%d SDA=GP%d SCL=GP%d, address 0x%02x\n", SLAVE_I2C, SDA_PIN, SCL_PIN,
           SLAVE_ADDRESS);
#if SLAVE_SELFTEST
    printf("i2c-slave: SELF-TEST on: i2c%d SDA=GP%d SCL=GP%d must be jumpered to the pair above\n",
           SLAVE_I2C == 1 ? 0 : 1, MASTER_SDA, MASTER_SCL);
#endif
    printf("i2c-slave: R0=0x%04x R1=0x%04x (complements), R2 counts seconds, R3 takes writes\n",
           regs[0], regs[1]);
    printf("i2c-slave: read it with  i2cget -f -y 1 0x%02x 0x00 w  (and 0x02 for the counter)\n",
           SLAVE_ADDRESS);
    printf("i2c-slave: the transaction counter below is what says whether the master reaches us\n");

    absolute_time_t next = make_timeout_time_ms(1000);
    uint16_t seconds = 0;
#if SLAVE_SELFTEST
    bool selftest_done_this_second = false;
#endif
    while (true) {
        if (time_reached(next)) {
            next = delayed_by_ms(next, 1000);
            regs[2] = ++seconds;
            if (led_ready) {
                cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, seconds % 2);
            }
            if (seconds % 5 == 0) {
                // The line levels matter as much as the counters: a pin that follows what the
                // master drives is on the same wire as the master's pin, and one that ignores it is
                // not — which is what separates a wiring fault from a silent device.
                printf("i2c-slave: up %u s, R2=0x%04x, transactions=%u (in %u, out %u), "
                       "SDA=%d SCL=%d\n",
                       seconds, regs[2], transactions, bytes_in, bytes_out,
                       gpio_get(SDA_PIN), gpio_get(SCL_PIN));
            }
        }
#if SLAVE_SELFTEST
        // Read our own register 0x00 the way the master does, and say what came back.
        if (seconds % 2 == 0 && !selftest_done_this_second) {
            selftest_done_this_second = true;
            uint8_t reg = 0x00, buf[2] = {0, 0};
            i2c_write_blocking(MASTER_INST, SLAVE_ADDRESS, &reg, 1, true);
            int n = i2c_read_blocking(MASTER_INST, SLAVE_ADDRESS, buf, 2, false);
            printf("i2c-slave: selftest -> %d byte(s) 0x%02x%02x (want 0xdead); slave has seen "
                   "%u transaction(s)\n", n, buf[0], buf[1], transactions);
            if (led_ready) {
                cyw43_arch_gpio_put(CYW43_WL_GPIO_LED_PIN, 0);
            }
        }
        if (seconds % 2 == 1) {
            selftest_done_this_second = false;
        }
#endif
        tight_loop_contents();
    }
}
