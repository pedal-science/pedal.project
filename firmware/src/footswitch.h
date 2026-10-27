// The three footswitches (plan Phase 3, step 5; docs/build-footswitches.md).
//
// GP10, GP11 and GP12 (physical pins 14, 15 and 16), each pulled up by the Pico and pulled to
// ground by its switch. A press sends cc 80, 81 or 82 with 127 and its release the same cc with
// 0 (docs/uart-protocol.md, U8). A long press on the panic switch sets the panic bypass, and
// another takes it off; it is sent as bypass_set.

#ifndef PEDAL_FOOTSWITCH_H
#define PEDAL_FOOTSWITCH_H

#include <stdbool.h>
#include <stdint.h>

#define FOOTSWITCH_COUNT 3u

void footswitch_init(void);
void footswitch_poll(uint32_t now_ms);

bool footswitch_pressed(unsigned index);
bool footswitch_panic(void);

#endif
