#include "protocol.h"

#include <stdio.h>
#include <string.h>

#include "pico/stdlib.h"

#define LINK_DOWN_MS 1000u
#define HELLO_EVERY_MS 1000u
#define RETRY_EVERY_MS 20u
#define RETRY_MAX 5u
#define NAME_MAX 48u

static proto_send_fn send_bytes;
static uint16_t caps;
static char fw_version[16];

static uint32_t now_ms;
static uint32_t last_rx_ms;
static uint32_t last_tx_ms;
static uint32_t next_hello_ms;
static bool session_up;
static uint16_t heartbeat_ms = 250;
static uint8_t ping_nonce;

static uint32_t frames_ok;
static uint32_t frames_bad;
static uint32_t events_lost;

static struct {
    bool pending;
    uint8_t seq;
    uint8_t kind;
    uint8_t a;
    uint8_t b;
    uint8_t source;
    uint8_t tries;
    uint32_t due_ms;
} ev;
static uint8_t next_seq;

static uint8_t state_flags;
static int8_t state_rig = -1;
static int8_t state_bank = -1;
static uint8_t state_bank_size;
static char state_name[NAME_MAX + 1];

static uint16_t crc16(const uint8_t *data, size_t len) {
    uint16_t crc = 0xFFFF;
    for (size_t i = 0; i < len; i++) {
        crc ^= (uint16_t)data[i] << 8;
        for (int bit = 0; bit < 8; bit++) {
            crc = (crc & 0x8000u) ? (uint16_t)((crc << 1) ^ 0x1021u) : (uint16_t)(crc << 1);
        }
    }
    return crc;
}

static void send_frame(uint8_t type, const uint8_t *payload, uint8_t len) {
    uint8_t frame[4 + PROTO_MAX_PAYLOAD + 2];
    frame[0] = PROTO_SYNC0;
    frame[1] = PROTO_SYNC1;
    frame[2] = type;
    frame[3] = len;
    if (len) {
        memcpy(&frame[4], payload, len);
    }
    uint16_t crc = crc16(&frame[2], (size_t)len + 2);
    frame[4 + len] = (uint8_t)(crc & 0xFF);
    frame[5 + len] = (uint8_t)(crc >> 8);
    send_bytes(frame, (size_t)len + 6);
    last_tx_ms = now_ms;
}

static void send_hello(void) {
    uint8_t payload[4 + 1 + sizeof(fw_version)];
    payload[0] = PROTO_VERSION_MAJOR;
    payload[1] = PROTO_VERSION_MINOR;
    payload[2] = (uint8_t)(caps & 0xFF);
    payload[3] = (uint8_t)(caps >> 8);
    size_t n = strlen(fw_version);
    if (n > sizeof(fw_version) - 1) {
        n = sizeof(fw_version) - 1;
    }
    payload[4] = (uint8_t)n;  // str8: one length byte, then the bytes (draft 2, U2)
    memcpy(&payload[5], fw_version, n);
    send_frame(PROTO_MSG_HELLO, payload, (uint8_t)(5 + n));
    printf("proto: hello sent (v%u.%u caps=0x%04x)\n", PROTO_VERSION_MAJOR, PROTO_VERSION_MINOR,
           (unsigned)caps);
}

// ERROR carries a code and a str8 text (docs/uart-protocol.md, Messages). Long text is cut
// on a byte boundary: everything this end says in one is ASCII.
static void send_error(uint8_t code, const char *text) {
    uint8_t payload[1 + 48];
    size_t n = strlen(text);
    if (n > sizeof(payload) - 2) {
        n = sizeof(payload) - 2;
    }
    payload[0] = code;
    payload[1] = (uint8_t)n;
    memcpy(&payload[2], text, n);
    send_frame(PROTO_MSG_ERROR, payload, (uint8_t)(2 + n));
}

static void send_event(void) {
    uint8_t payload[5] = {ev.seq, ev.source, ev.kind, ev.a, ev.b};
    send_frame(PROTO_MSG_EVENT, payload, sizeof(payload));
}

static void handle_state(const uint8_t *p, uint8_t len) {
    if (len < 5) {  // flags, rig i8, bank i8, bank size, then the name's length byte
        return;
    }
    state_flags = p[0];
    state_rig = (int8_t)p[1];
    state_bank = (int8_t)p[2];
    state_bank_size = p[3];
    // The name is a str8: one length byte, then that many bytes. Anything after it is
    // ignored, which is what lets STATE grow at its end (docs/uart-protocol.md, U2).
    size_t n = p[4];
    if (n > (size_t)(len - 5)) {
        n = (size_t)(len - 5);
    }
    if (n > NAME_MAX) {
        n = NAME_MAX;
    }
    memcpy(state_name, &p[5], n);
    state_name[n] = '\0';
    printf("proto: state audio_ready=%u muted=%u health=%u rig=%d bank=%d/%u name='%s'\n",
           (unsigned)(state_flags & PROTO_STATE_AUDIO_READY ? 1 : 0),
           (unsigned)(state_flags & PROTO_STATE_ENGINE_MUTED ? 1 : 0),
           (unsigned)((state_flags & PROTO_STATE_HEALTH_MASK) >> 2), (int)state_rig,
           (int)state_bank, (unsigned)state_bank_size, state_name);
}

static void handle_frame(uint8_t type, const uint8_t *p, uint8_t len) {
    last_rx_ms = now_ms;
    frames_ok++;

    // Everything but the handshake belongs to a session: with none, the Core's PINGs, STATEs
    // and ACKs are not answered. A Core we cannot talk to therefore sees the link go down
    // rather than a half-session it cannot use (docs/uart-protocol.md, Session).
    if (!session_up && type != PROTO_MSG_WELCOME && type != PROTO_MSG_ERROR) {
        printf("proto: ignoring type 0x%02x with no session\n", (unsigned)type);
        return;
    }

    switch (type) {
        case PROTO_MSG_WELCOME:
            if (len < 4) {
                printf("proto: short welcome\n");
                return;
            }
            if (p[0] != PROTO_VERSION_MAJOR) {
                // A protocol error, not a session: say so with ERROR and stay out of the
                // session, so a half-swapped or wrong service is visible at both ends.
                char text[48];
                snprintf(text, sizeof(text), "Pico speaks %u.%u, service %u.%u",
                         PROTO_VERSION_MAJOR, PROTO_VERSION_MINOR, (unsigned)p[0],
                         (unsigned)p[1]);
                printf("proto: version mismatch (%s)\n", text);
                session_up = false;
                send_error(PROTO_ERR_VERSION, text);
                return;
            }
            heartbeat_ms = (uint16_t)(p[2] | (p[3] << 8));
            if (heartbeat_ms == 0) {
                heartbeat_ms = 250;
            }
            session_up = true;
            last_tx_ms = now_ms;
            printf("proto: session up (service v%u.%u, heartbeat %u ms)\n", (unsigned)p[0],
                   (unsigned)p[1], (unsigned)heartbeat_ms);
            break;

        case PROTO_MSG_PING:
            if (len >= 1) {
                send_frame(PROTO_MSG_PONG, p, 1);
                printf("proto: ping %u -> pong\n", (unsigned)p[0]);
            }
            break;

        case PROTO_MSG_PONG:
            printf("proto: pong %u\n", len >= 1 ? (unsigned)p[0] : 0u);
            break;

        case PROTO_MSG_STATE:
            handle_state(p, len);
            break;

        case PROTO_MSG_ACK:
            if (len >= 1 && ev.pending && p[0] == ev.seq) {
                ev.pending = false;
                printf("proto: event %u acked after %u retries\n", (unsigned)ev.seq,
                       (unsigned)ev.tries);
            }
            break;

        case PROTO_MSG_ERROR: {
            // code, then a str8 text.
            size_t n = len >= 2 ? p[1] : 0u;
            if (n > (size_t)(len >= 2 ? len - 2 : 0u)) {
                n = (size_t)(len >= 2 ? len - 2 : 0u);
            }
            printf("proto: error code=%u text='%.*s'\n", len >= 1 ? (unsigned)p[0] : 0u, (int)n,
                   len >= 2 ? (const char *)&p[2] : "");
            break;
        }

        default:
            printf("proto: ignoring type 0x%02x len=%u\n", (unsigned)type, (unsigned)len);
            break;
    }
}

void proto_init(proto_send_fn send, uint16_t board_caps, const char *version) {
    send_bytes = send;
    caps = board_caps;
    snprintf(fw_version, sizeof(fw_version), "%s", version);
    next_hello_ms = 0;
    last_rx_ms = 0;
    last_tx_ms = 0;
    session_up = false;
}

// The bytes of the frame being assembled. After a bad length or a bad CRC the parser rescans
// them from the byte after the first sync byte (docs/uart-protocol.md, Framing), so a corrupted
// len cannot swallow the good frames behind it. A frame is never longer than this, so the
// buffer never holds more than one frame's worth.
static uint8_t rx[4 + PROTO_MAX_PAYLOAD + 2];
static size_t rx_len;

static void rx_drop(size_t n) {
    memmove(rx, rx + n, rx_len - n);
    rx_len -= n;
}

void proto_on_byte(uint8_t byte) {
    if (rx_len == sizeof(rx)) {
        rx_drop(1);  // cannot happen: a frame is dealt with once it is complete
    }
    rx[rx_len++] = byte;

    for (;;) {
        // Skip to a sync pair, keeping a first sync byte that may be the start of one.
        size_t start = 0;
        while (start < rx_len && !(rx[start] == PROTO_SYNC0 &&
                                   (start + 1 == rx_len || rx[start + 1] == PROTO_SYNC1))) {
            start++;
        }
        if (start > 0) {
            rx_drop(start);
        }
        if (rx_len < 4) {
            return;
        }

        uint8_t type = rx[2];
        uint8_t len = rx[3];
        if (len > PROTO_MAX_PAYLOAD) {
            frames_bad++;
            printf("proto: bad length %u (type 0x%02x)\n", (unsigned)len, (unsigned)type);
            rx_drop(1);
            continue;
        }
        size_t total = 4u + len + 2u;
        if (rx_len < total) {
            return;
        }

        uint16_t want = (uint16_t)(rx[4 + len] | ((uint16_t)rx[5 + len] << 8));
        if (crc16(&rx[2], (size_t)len + 2) == want) {
            handle_frame(type, &rx[4], len);
            rx_drop(total);
        } else {
            frames_bad++;
            printf("proto: bad crc (type 0x%02x len %u)\n", (unsigned)type, (unsigned)len);
            rx_drop(1);
        }
    }
}

void proto_tick(uint32_t ms) {
    now_ms = ms;

    if (!session_up) {
        if ((int32_t)(now_ms - next_hello_ms) >= 0) {
            send_hello();
            next_hello_ms = now_ms + HELLO_EVERY_MS;
        }
        return;
    }

    if (ev.pending && (int32_t)(now_ms - ev.due_ms) >= 0) {
        if (ev.tries < RETRY_MAX) {
            send_event();
            ev.tries++;
            ev.due_ms = now_ms + RETRY_EVERY_MS;
            printf("proto: event %u retransmit %u\n", (unsigned)ev.seq, (unsigned)ev.tries);
        } else {
            ev.pending = false;
            events_lost++;
            printf("proto: event %u lost\n", (unsigned)ev.seq);
        }
    }

    if ((int32_t)(now_ms - last_rx_ms) > (int32_t)LINK_DOWN_MS) {
        session_up = false;
        next_hello_ms = now_ms + HELLO_EVERY_MS;
        // An event still pending goes with the session: sent after a reconnect, a press would act
        // seconds after it was made (docs/uart-protocol.md, Reliability).
        if (ev.pending) {
            ev.pending = false;
            events_lost++;
            printf("proto: event %u dropped with the link\n", (unsigned)ev.seq);
        }
        printf("proto: link down\n");
        return;
    }

    if ((int32_t)(now_ms - last_tx_ms) >= (int32_t)heartbeat_ms) {
        uint8_t nonce = ++ping_nonce;
        send_frame(PROTO_MSG_PING, &nonce, 1);
    }
}

bool proto_session_up(void) {
    return session_up;
}

bool proto_send_event(uint8_t kind, uint8_t a, uint8_t b, uint8_t source) {
    if (!session_up) {
        printf("proto: event refused, no session\n");
        return false;
    }
    if (ev.pending) {
        printf("proto: event refused, %u still pending\n", (unsigned)ev.seq);
        return false;
    }
    ev.seq = next_seq++;
    ev.kind = kind;
    ev.a = a;
    ev.b = b;
    ev.source = source;
    ev.tries = 0;
    ev.due_ms = now_ms + RETRY_EVERY_MS;
    ev.pending = true;
    send_event();
    printf("proto: event %u kind=0x%02x a=%u b=%u source=%u sent\n", (unsigned)ev.seq,
           (unsigned)kind, (unsigned)a, (unsigned)b, (unsigned)source);
    return true;
}

uint8_t proto_state_flags(void) {
    return state_flags;
}

int8_t proto_state_rig_index(void) {
    return state_rig;
}

const char *proto_state_rig_name(void) {
    return state_name;
}

uint32_t proto_frames_ok(void) {
    return frames_ok;
}

uint32_t proto_frames_bad(void) {
    return frames_bad;
}

uint32_t proto_events_lost(void) {
    return events_lost;
}
