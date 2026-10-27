#include "footswitch.h"

#include <stdio.h>

#include "pico/stdlib.h"
#include "protocol.h"

// The control board's pins, which the cut-down board keeps (stripboard/module_boards.py).
static const uint8_t pins[FOOTSWITCH_COUNT] = {10, 11, 12};

// Footswitches 1-3 send the general-purpose switch controllers (U8, decided 2026-10-06).
#define CC_FIRST 80u

// A reading has to hold this long to count. The 100 nF at each switch takes the fastest bounce;
// footswitches bounce far worse than panel buttons, and 10-20 ms is the handoff's window. Ten
// keeps the press inside D10's 50 ms with room for the link and the switch.
#define DEBOUNCE_MS 10u

// The panic bypass is a long press on footswitch 3, the assignable one (index 2). Its press still
// sends cc 82 at once, so the press is not held back; footswitches 1 and 2 step rigs, and a long
// press on either would step one before it bypassed.
#define PANIC_SWITCH 2u
#define LONG_PRESS_MS 1000u

static struct {
    bool raw;          // the last sample, true while pressed
    bool pressed;      // the debounced state
    uint32_t since_ms; // when raw last changed
    uint32_t down_ms;  // when the debounced press began
    bool long_done;    // this press has already been taken as a long press
} sw[FOOTSWITCH_COUNT];

static bool panic_on;
static uint32_t last_poll_ms;

static bool read_pressed(unsigned i) {
    return !gpio_get(pins[i]);  // pulled up: the switch pulls the pin to ground
}

void footswitch_init(void) {
    for (unsigned i = 0; i < FOOTSWITCH_COUNT; i++) {
        gpio_init(pins[i]);
        gpio_set_dir(pins[i], GPIO_IN);
        gpio_pull_up(pins[i]);
    }
    sleep_ms(2);  // let the pull-ups charge the 100 nF before the first reading
    uint32_t now = to_ms_since_boot(get_absolute_time());
    for (unsigned i = 0; i < FOOTSWITCH_COUNT; i++) {
        // A switch held at power-up is taken as already down: it is not a press. Its release
        // still sends the cc's 0, which acts on nothing (the service acts on the press).
        sw[i].raw = sw[i].pressed = read_pressed(i);
        sw[i].since_ms = now;
        sw[i].down_ms = now;
        sw[i].long_done = true;
    }
    last_poll_ms = now;
    printf("fs: footswitches on GP%u/GP%u/GP%u, panic is a %u ms press on %u\n", pins[0],
           pins[1], pins[2], LONG_PRESS_MS, PANIC_SWITCH + 1);
}

static void on_change(unsigned i, bool pressed, uint32_t now_ms) {
    uint8_t cc = (uint8_t)(CC_FIRST + i);
    printf("fs: %u %s\n", i + 1, pressed ? "down" : "up");
    if (pressed) {
        sw[i].down_ms = now_ms;
        sw[i].long_done = false;
        proto_send_event(PROTO_EV_CC, cc, 127, PROTO_SRC_FOOTSWITCH);
    } else {
        proto_send_event(PROTO_EV_CC, cc, 0, PROTO_SRC_FOOTSWITCH);
    }
}

void footswitch_poll(uint32_t now_ms) {
    if (now_ms == last_poll_ms) {
        return;  // once a millisecond is plenty
    }
    last_poll_ms = now_ms;

    for (unsigned i = 0; i < FOOTSWITCH_COUNT; i++) {
        bool raw = read_pressed(i);
        if (raw != sw[i].raw) {
            sw[i].raw = raw;
            sw[i].since_ms = now_ms;
        } else if (raw != sw[i].pressed && now_ms - sw[i].since_ms >= DEBOUNCE_MS) {
            sw[i].pressed = raw;
            on_change(i, raw, now_ms);
        }

        if (i == PANIC_SWITCH && sw[i].pressed && !sw[i].long_done &&
            now_ms - sw[i].down_ms >= LONG_PRESS_MS) {
            // Taken while the switch is still down, so the player hears it without letting go.
            // The relay is local and comes with step 6; until then this is the service's word.
            sw[i].long_done = true;
            panic_on = !panic_on;
            printf("fs: panic bypass %s\n", panic_on ? "on" : "off");
            proto_send_event(PROTO_EV_BYPASS_SET, panic_on ? 1 : 0, 0, PROTO_SRC_FOOTSWITCH);
        }
    }
}

bool footswitch_pressed(unsigned index) {
    return index < FOOTSWITCH_COUNT && sw[index].pressed;
}

bool footswitch_panic(void) {
    return panic_on;
}
