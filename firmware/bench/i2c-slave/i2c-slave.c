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

#define SDA_PIN 4
#define SCL_PIN 5
#define SLAVE_ADDRESS 0x2a

#define REGISTERS 16

// R0/R1 are complements, R2 is a live seconds counter, R3 is scratch for writes. Big-endian on the
// wire (MSB first), which is the order the WM8960 answers a word read in — the point is to be
// comparable with the codec's transactions, not merely readable.
static volatile uint16_t regs[REGISTERS] = {
    0xDEAD, 0x2152, 0x0000, 0x0000,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
};

static volatile uint8_t selected = 0;   // the byte the master put in a write, or the running read
static volatile uint8_t byte_in_reg = 0;
static volatile bool have_selection = false;

static inline unsigned reg_index(uint8_t sel) { return (sel >> 1) & (REGISTERS - 1); }

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
                selected = (uint8_t)(selected + 2);
            }
        }
        break;
    }
    case I2C_SLAVE_REQUEST:
        // A read repeats the last write's register address, then walks forward two bytes at a time.
        i2c_write_byte_raw(i2c, reg_byte(selected, byte_in_reg));
        if (++byte_in_reg > 1) {
            byte_in_reg = 0;
            selected = (uint8_t)(selected + 2);
        }
        break;
    case I2C_SLAVE_FINISH:
        have_selection = false;
        byte_in_reg = 0;
        break;
    default:
        break;
    }
}

int main(void) {
    stdio_init_all();
    sleep_ms(1500);     // let the USB console come up before the banner

    i2c_init(i2c0, 100 * 1000);
    gpio_set_function(SDA_PIN, GPIO_FUNC_I2C);
    gpio_set_function(SCL_PIN, GPIO_FUNC_I2C);
    gpio_pull_up(SDA_PIN);
    gpio_pull_up(SCL_PIN);

    i2c_slave_init(i2c0, SLAVE_ADDRESS, i2c_slave_handler);

    printf("i2c-slave: up, SDA=GP%d SCL=GP%d, address 0x%02x\n", SDA_PIN, SCL_PIN, SLAVE_ADDRESS);
    printf("i2c-slave: R0=0x%04x R1=0x%04x (complements), R2 counts seconds, R3 takes writes\n",
           regs[0], regs[1]);
    printf("i2c-slave: read it with  i2cget -f -y 1 0x%02x 0x00 w  (and 0x02 for the counter)\n",
           SLAVE_ADDRESS);

    absolute_time_t next = make_timeout_time_ms(1000);
    uint16_t seconds = 0;
    while (true) {
        if (time_reached(next)) {
            next = delayed_by_ms(next, 1000);
            regs[2] = ++seconds;
            if (seconds % 5 == 0) {
                printf("i2c-slave: up %u s, R2=0x%04x, selections=%u\n", seconds, regs[2],
                       have_selection);
            }
        }
        tight_loop_contents();
    }
}
