// The Pico end of docs/uart-protocol.md, protocol version 1.0.
//
// Framing, the HELLO/WELCOME session, PING/PONG, EVENTs with ACK and retry,
// and STATE. main.c feeds it bytes from the link UART and calls proto_tick().

#ifndef PEDAL_PROTOCOL_H
#define PEDAL_PROTOCOL_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define PROTO_VERSION_MAJOR 1u
#define PROTO_VERSION_MINOR 0u

#define PROTO_SYNC0 0xA5u
#define PROTO_SYNC1 0x5Au
#define PROTO_MAX_PAYLOAD 64u

enum proto_msg {
    PROTO_MSG_HELLO = 0x01,
    PROTO_MSG_WELCOME = 0x02,
    PROTO_MSG_EVENT = 0x03,
    PROTO_MSG_ACK = 0x04,
    PROTO_MSG_STATE = 0x05,
    PROTO_MSG_PING = 0x06,
    PROTO_MSG_PONG = 0x07,
    PROTO_MSG_ERROR = 0x08,
    PROTO_MSG_LOG = 0x09,
    PROTO_MSG_CFG = 0x0A,
};

enum proto_event_kind {
    PROTO_EV_RIG_UP = 0x01,
    PROTO_EV_RIG_DOWN = 0x02,
    PROTO_EV_RIG_SELECT = 0x03,
    PROTO_EV_BANK_UP = 0x04,
    PROTO_EV_BANK_DOWN = 0x05,
    PROTO_EV_BANK_SELECT = 0x06,
    PROTO_EV_BYPASS_SET = 0x07,
    PROTO_EV_BYPASS_TOGGLE = 0x08,
    PROTO_EV_CC = 0x10,
    PROTO_EV_PC = 0x11,
    PROTO_EV_EXPRESSION = 0x12,
};

enum proto_event_source {
    PROTO_SRC_UNKNOWN = 0,
    PROTO_SRC_FOOTSWITCH = 1,
    PROTO_SRC_MIDI = 2,
    PROTO_SRC_PANEL = 3,
    PROTO_SRC_SERVICE = 4,
};

#define PROTO_STATE_AUDIO_READY (1u << 0)
#define PROTO_STATE_ENGINE_BYPASS (1u << 1)
#define PROTO_STATE_HEALTH_MASK (3u << 2)

typedef void (*proto_send_fn)(const uint8_t *data, size_t len);

void proto_init(proto_send_fn send, uint16_t caps, const char *fw_version);
void proto_on_byte(uint8_t byte);
void proto_tick(uint32_t now_ms);

bool proto_session_up(void);
bool proto_send_event(uint8_t kind, uint8_t a, uint8_t b, uint8_t source);

uint8_t proto_state_flags(void);
int8_t proto_state_rig_index(void);
const char *proto_state_rig_name(void);

uint32_t proto_frames_ok(void);
uint32_t proto_frames_bad(void);
uint32_t proto_events_lost(void);

#endif
