#include "footswitch.h"

#include <stdio.h>

#include "pico/stdlib.h"
#include "protocol.h"

// The control board's pins, which the cut-down board keeps (stripboard/module_boards.py), in the
// order the player numbers the switches, left to right. The box's loom does not follow the
// board's FS1-FS3 labels: the left switch is on GP12 (FS pin 4), the middle one on GP10 (FS pin
// 2) and the right one on GP11 (FS pin 3). Found on the bench 2026-11-07
// (docs/build-footswitches.md, "As built in the box").
static const uint8_t pins[FOOTSWITCH_COUNT] = {12, 10, 11};

// The box's switches are wired COM to NC: closed at rest, open while pressed. So a press lets the
// pull-up win and the pin reads high. Set this to 0 for a loom wired COM to NO, as the design
// first drew it, where a press pulls the pin to ground.
#define PRESS_OPENS 1

// Footswitches 1-3 send the general-purpose switch controllers (U8, decided 2026-10-06).
#define CC_FIRST 80u

// A reading has to hold this long to count. The 100 nF at each switch takes the fastest bounce;
// footswitches bounce far worse than panel buttons, and 10-20 ms is the handoff's window. Ten
// keeps the press inside D10's 50 ms with room for the link and the switch.
#define DEBOUNCE_MS 10u

// A press is taken when the switch is released, not when it goes down: a hold is then a hold,
// and not a tap followed by a hold. A short release sends the press message (cc 127) and then its
// release (0); a release after the hold sends only 0, so a hold never also taps.
//
// The bypass hold is a long press on the right-hand switch (index 0, GP12, cc 80). It sends one
// `bypass_toggle` while the switch is still down, which the pedal service turns into its tuner
// (the tuner node mutes the rig; there is no relay yet). The other two step rigs, so a long press
// on either would step one before it did anything else.
#define BYPASS_SWITCH 0u
#define LONG_PRESS_MS 1000u

static struct {
    bool raw;          // the last sample, true while pressed
    bool pressed;      // the debounced state
    uint32_t since_ms; // when raw last changed
    uint32_t down_ms;  // when the debounced press began
    bool long_done;    // this press has already been taken as a long press
} sw[FOOTSWITCH_COUNT];

static uint32_t last_poll_ms;

static bool read_pressed(unsigned i) {
#if PRESS_OPENS
    // Pulled up, and grounded by the switch at rest: a press opens it and the pin goes high. A
    // loom that comes unplugged reads as all three held. At power-up that is no press at all
    // (footswitch_init), but pulled out while running it is three releases and, a second later,
    // the bypass hold.
    return gpio_get(pins[i]);
#else
    return !gpio_get(pins[i]);  // pulled up: the switch pulls the pin to ground
#endif
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
        // still sends the cc's 0, which acts on nothing.
        sw[i].raw = sw[i].pressed = read_pressed(i);
        sw[i].since_ms = now;
        sw[i].down_ms = now;
        sw[i].long_done = true;
    }
    last_poll_ms = now;
    printf("fs: footswitches 1/2/3 on GP%u/GP%u/GP%u, a press %s, the hold is a %u ms press on %u\n",
           pins[0], pins[1], pins[2], PRESS_OPENS ? "opens" : "closes", LONG_PRESS_MS,
           BYPASS_SWITCH + 1);
}

static void on_change(unsigned i, bool pressed, uint32_t now_ms) {
    uint8_t cc = (uint8_t)(CC_FIRST + i);
    printf("fs: %u %s\n", i + 1, pressed ? "down" : "up");
    if (pressed) {
        // A press is only recorded here. It is registered on release, so a hold is a hold and
        // not a tap followed by one.
        sw[i].down_ms = now_ms;
        sw[i].long_done = false;
        return;
    }
    if (!sw[i].long_done) {
        // The short release is the press: the same pair a MIDI switch sends, 127 then 0.
        proto_send_event(PROTO_EV_CC, cc, 127, PROTO_SRC_FOOTSWITCH);
    }
    proto_send_event(PROTO_EV_CC, cc, 0, PROTO_SRC_FOOTSWITCH);
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

        if (i == BYPASS_SWITCH && sw[i].pressed && !sw[i].long_done &&
            now_ms - sw[i].down_ms >= LONG_PRESS_MS) {
            // Taken while the switch is still down, so the player hears it without letting go.
            // The service turns this into its tuner, whose node a client mounts to mute the rig;
            // a relay comes with step 6. The release that follows this sends 0 only, so the hold
            // is not also a tap.
            sw[i].long_done = true;
            printf("fs: hold on %u -> bypass_toggle\n", i + 1);
            proto_send_event(PROTO_EV_BYPASS_TOGGLE, 0, 0, PROTO_SRC_FOOTSWITCH);
        }
    }
}

bool footswitch_pressed(unsigned index) {
    return index < FOOTSWITCH_COUNT && sw[index].pressed;
}
