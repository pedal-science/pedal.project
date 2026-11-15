// The three footswitches (plan Phase 3, step 5; docs/build-footswitches.md).
//
// On GP12, GP10 and GP11 in the box (footswitches 1, 2 and 3, left to right; physical pins 16, 14
// and 15), each pulled up by the Pico. The box's switches are wired COM to NC, so a press opens
// the switch and the pin reads high (PRESS_OPENS in footswitch.c). A **short press is registered
// on release**: the release sends cc 80, 81 or 82 with 127 and then the same cc with 0
// (docs/uart-protocol.md, U8). A hold on footswitch 3 (the right one) sends one `bypass_toggle`
// after a second and its release sends 0 only, so a hold is never also a tap; the service turns
// that into its tuner.

#ifndef PEDAL_FOOTSWITCH_H
#define PEDAL_FOOTSWITCH_H

#include <stdbool.h>
#include <stdint.h>

#define FOOTSWITCH_COUNT 3u

void footswitch_init(void);
void footswitch_poll(uint32_t now_ms);

bool footswitch_pressed(unsigned index);

#endif
