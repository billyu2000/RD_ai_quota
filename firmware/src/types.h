#pragma once

#include <Arduino.h>

static const uint8_t MAX_PROVIDERS = 4;
static const uint8_t MAX_WINDOWS = 3;
static const uint8_t MAX_ORDER = 4;

struct QuotaWindow {
  char label[12];
  float used_pct;
  int32_t resets_in_s;
  char resets_at[16];
};

struct Provider {
  char id[16];
  char name[16];
  char status[16];
  QuotaWindow windows[MAX_WINDOWS];
  uint8_t n_windows;
};

struct AppState {
  Provider providers[MAX_PROVIDERS];
  uint8_t n_providers;
  char order[MAX_ORDER][16];
  uint8_t n_order;
  uint32_t interval_ms;
  uint8_t brightness;
  bool paused;
  bool has_quota;
  uint32_t last_quota_ms;
  uint8_t page;
  bool dirty;
  bool portal_mode;
  bool wifi_up;
  bool server_up;
};
