// Pedal Pico firmware.
//
// Phase 3 of the plan. The link speaks the protocol in docs/uart-protocol.md
// (version 1.0): framing, the HELLO/WELCOME session, PING/PONG, EVENTs with
// ACK/retry, and STATE. Footswitches, DIN MIDI, the relay and LEDs arrive in
// step 5; until then the USB console stands in for the controls:
//
//   e   send a rig_up EVENT
//   d   send a rig_down EVENT
//   b   send a bypass_toggle EVENT
//   ?   print the protocol counters and the last STATE
//
// Build with -DFW_ECHO=ON (or FW_ECHO=1 firmware/build.sh) to get step 1's
// byte echo back, for firmware/tools/echo-test.py.
//
// The link is UART0 on GP0 (TX) and GP1 (RX). The Debug Probe's UART bridge is
// the other end, on its U port with the 0.1-inch header (female) cable: probe
// RX (yellow) <- GP0/pin 1, probe TX (orange) -> GP1/pin 2, GND (black) <-> pin
// 3. USB stdio stays on: it is the console, and the bench's control stand-in.

#include <stdio.h>

#include "hardware/uart.h"
#include "pico/stdlib.h"
#include "protocol.h"

#define LINK_UART   uart0
#define LINK_BAUD   115200
#define LINK_TX_PIN 0
#define LINK_RX_PIN 1

#define FW_VERSION "0.1"

static void link_setup(void) {
    uart_init(LINK_UART, LINK_BAUD);
    gpio_set_function(LINK_TX_PIN, UART_FUNCSEL_NUM(LINK_UART, LINK_TX_PIN));
    gpio_set_function(LINK_RX_PIN, UART_FUNCSEL_NUM(LINK_UART, LINK_RX_PIN));
    gpio_pull_up(LINK_RX_PIN);  // UART idle is high; a floating RX invents bytes
    uart_set_format(LINK_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(LINK_UART, true);
}

#ifdef PEDAL_FW_ECHO

int main(void) {
    stdio_init_all();
    link_setup();

    uart_puts(LINK_UART, "pico: link echo ready\r\n");
    printf("echo: UART0 on GP%d/GP%d at %u baud\n", LINK_TX_PIN, LINK_RX_PIN, LINK_BAUD);

    uint32_t echoed = 0;
    absolute_time_t next_beat = make_timeout_time_ms(5000);

    while (true) {
        while (uart_is_readable(LINK_UART)) {
            uart_putc(LINK_UART, (char)uart_getc(LINK_UART));
            echoed++;
        }
        if (time_reached(next_beat)) {
            printf("echo: up %llu s, %lu bytes\n",
                   (unsigned long long)(to_ms_since_boot(get_absolute_time()) / 1000),
                   (unsigned long)echoed);
            next_beat = make_timeout_time_ms(5000);
        }
        tight_loop_contents();
    }
}

#else

static void link_send(const uint8_t *data, size_t len) {
    uart_write_blocking(LINK_UART, data, len);
}

int main(void) {
    stdio_init_all();
    link_setup();

    // No relay, MIDI, display or expression jack is wired yet, and no
    // footswitches: the capabilities are honest until step 5 fills them in.
    proto_init(link_send, 0x0000, FW_VERSION);
    printf("fw: protocol %u.%u on UART0 GP%d/GP%d at %u baud\n", PROTO_VERSION_MAJOR,
           PROTO_VERSION_MINOR, LINK_TX_PIN, LINK_RX_PIN, LINK_BAUD);

    absolute_time_t next_beat = make_timeout_time_ms(5000);

    while (true) {
        while (uart_is_readable(LINK_UART)) {
            proto_on_byte((uint8_t)uart_getc(LINK_UART));
        }

        proto_tick(to_ms_since_boot(get_absolute_time()));

        // The bench's stand-in for the controls.
        int c = getchar_timeout_us(0);
        switch (c) {
            case 'e':
                proto_send_event(PROTO_EV_RIG_UP, 0, 0, PROTO_SRC_UNKNOWN);
                break;
            case 'd':
                proto_send_event(PROTO_EV_RIG_DOWN, 0, 0, PROTO_SRC_UNKNOWN);
                break;
            case 'b':
                proto_send_event(PROTO_EV_BYPASS_TOGGLE, 0, 0, PROTO_SRC_UNKNOWN);
                break;
            case '?':
                printf("proto: frames ok=%lu bad=%lu events lost=%lu session=%u rig=%d name='%s'\n",
                       (unsigned long)proto_frames_ok(), (unsigned long)proto_frames_bad(),
                       (unsigned long)proto_events_lost(), (unsigned)proto_session_up(),
                       (int)proto_state_rig_index(), proto_state_rig_name());
                break;
            default:
                break;
        }

        if (time_reached(next_beat)) {
            printf("fw: up %llu s, session=%u, frames ok=%lu bad=%lu\n",
                   (unsigned long long)(to_ms_since_boot(get_absolute_time()) / 1000),
                   (unsigned)proto_session_up(), (unsigned long)proto_frames_ok(),
                   (unsigned long)proto_frames_bad());
            next_beat = make_timeout_time_ms(5000);
        }

        tight_loop_contents();
    }
}

#endif
