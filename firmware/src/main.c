// Pedal Pico firmware.
//
// Phase 3 of the plan. Today this is step 1's echo: every byte that arrives on
// the link UART goes straight back, which proves the UART and the wiring to the
// Debug Probe. It grows into firmware v1 (step 5): footswitches, DIN MIDI, the
// relay, LEDs, and the protocol in docs/uart-protocol.md.
//
// The link is UART0 on GP0 (TX) and GP1 (RX) while it is on the bench. The
// Debug Probe's UART bridge is the other end, on its U port with the 0.1-inch
// header (female) cable: probe RX (yellow) <- GP0/pin 1, probe TX (orange) ->
// GP1/pin 2, GND (black) <-> pin 3. Orange is the probe's output; yellow its
// input. USB stdio stays on for the heartbeat, so the console proves the board
// is alive without a UART peer.

#include <stdio.h>

#include "hardware/uart.h"
#include "pico/stdlib.h"

#define LINK_UART   uart0
#define LINK_BAUD   115200
#define LINK_TX_PIN 0
#define LINK_RX_PIN 1

int main(void) {
    stdio_init_all();

    uart_init(LINK_UART, LINK_BAUD);
    gpio_set_function(LINK_TX_PIN, UART_FUNCSEL_NUM(LINK_UART, LINK_TX_PIN));
    gpio_set_function(LINK_RX_PIN, UART_FUNCSEL_NUM(LINK_UART, LINK_RX_PIN));
    gpio_pull_up(LINK_RX_PIN);  // UART idle is high; a floating RX invents bytes
    uart_set_format(LINK_UART, 8, 1, UART_PARITY_NONE);
    uart_set_fifo_enabled(LINK_UART, true);

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
