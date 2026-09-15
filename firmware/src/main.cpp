#include <Arduino.h>

#include "display.h"
#include "protocol.h"
#include "types.h"

static const int PIN_BTN_NEXT = 0;
static const int PIN_BTN_PAUSE = 14;

static AppState state;
static uint32_t last_rotate_ms = 0;
static uint32_t last_hello_ms = 0;
static bool last_next = true;
static bool last_pause = true;
static uint32_t last_btn_ms = 0;

static void defaults() {
  memset(&state, 0, sizeof(state));
  state.interval_ms = 5000;
  state.brightness = 180;
  state.n_order = 4;
  strncpy(state.order[0], "claude", sizeof(state.order[0]) - 1);
  strncpy(state.order[1], "codex", sizeof(state.order[1]) - 1);
  strncpy(state.order[2], "grok", sizeof(state.order[2]) - 1);
  strncpy(state.order[3], "zai", sizeof(state.order[3]) - 1);
  state.dirty = true;
}

void setup() {
  defaults();
  pinMode(PIN_BTN_NEXT, INPUT_PULLUP);
  pinMode(PIN_BTN_PAUSE, INPUT_PULLUP);
  display_begin(state.brightness);
  protocol_begin();
  protocol_send_hello();
  last_hello_ms = millis();
  last_rotate_ms = millis();
}

void loop() {
  protocol_poll(state);

  uint32_t now = millis();
  if (now - last_hello_ms > 5000 && !state.has_quota) {
    protocol_send_hello();
    last_hello_ms = now;
  }

  bool next = digitalRead(PIN_BTN_NEXT);
  bool pause = digitalRead(PIN_BTN_PAUSE);
  if (now - last_btn_ms > 180) {
    if (last_next && !next && state.n_order > 0) {
      state.page = (state.page + 1) % state.n_order;
      last_rotate_ms = now;
      state.dirty = true;
      protocol_send_event("next");
      last_btn_ms = now;
    }
    if (last_pause && !pause) {
      state.paused = !state.paused;
      state.dirty = true;
      protocol_send_event("pause");
      last_btn_ms = now;
    }
  }
  last_next = next;
  last_pause = pause;

  if (!state.paused && state.has_quota && state.n_order > 0 &&
      now - last_rotate_ms >= state.interval_ms) {
    state.page = (state.page + 1) % state.n_order;
    last_rotate_ms = now;
    state.dirty = true;
  }

  static uint8_t last_brightness = 0;
  if (state.brightness != last_brightness) {
    display_set_brightness(state.brightness);
    last_brightness = state.brightness;
  }

  if (state.dirty) {
    display_render(state);
    state.dirty = false;
  }

  delay(10);
}
