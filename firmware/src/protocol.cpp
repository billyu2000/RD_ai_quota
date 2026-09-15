#include "protocol.h"

#include <ArduinoJson.h>

static const size_t kLineMax = 2048;
static char line_buf[kLineMax];
static size_t line_len = 0;

static int window_rank(const char *label) {
  if (!label || !label[0]) return 9;
  if (strcmp(label, "5h") == 0) return 0;
  if (strcmp(label, "weekly") == 0 || strcmp(label, "7d") == 0 || strcmp(label, "wk") == 0) return 1;
  if (strcmp(label, "mo") == 0) return 2;
  return 9;
}

static void normalize_label(char *label, size_t n) {
  if (strcmp(label, "7d") == 0 || strcmp(label, "wk") == 0) {
    strncpy(label, "weekly", n - 1);
    label[n - 1] = 0;
  }
}

static void sort_windows(Provider &p) {
  for (uint8_t i = 0; i < p.n_windows; i++) {
    for (uint8_t j = i + 1; j < p.n_windows; j++) {
      if (window_rank(p.windows[j].label) < window_rank(p.windows[i].label)) {
        QuotaWindow tmp = p.windows[i];
        p.windows[i] = p.windows[j];
        p.windows[j] = tmp;
      }
    }
  }
}

static void copy_str(char *dst, size_t n, const char *src) {
  if (!src) {
    dst[0] = 0;
    return;
  }
  strncpy(dst, src, n - 1);
  dst[n - 1] = 0;
}

static void apply_quota(AppState &state, JsonDocument &doc) {
  JsonArray providers = doc["providers"].as<JsonArray>();
  if (providers.isNull()) return;

  state.n_providers = 0;
  for (JsonObject p : providers) {
    if (state.n_providers >= MAX_PROVIDERS) break;
    Provider &out = state.providers[state.n_providers++];
    copy_str(out.id, sizeof(out.id), p["id"] | "");
    copy_str(out.name, sizeof(out.name), p["name"] | out.id);
    copy_str(out.status, sizeof(out.status), p["status"] | "ok");
    out.n_windows = 0;
    JsonArray windows = p["windows"].as<JsonArray>();
    if (windows.isNull()) continue;
    for (JsonObject w : windows) {
      if (out.n_windows >= MAX_WINDOWS) break;
      QuotaWindow &win = out.windows[out.n_windows++];
      copy_str(win.label, sizeof(win.label), w["label"] | "");
      normalize_label(win.label, sizeof(win.label));
      win.used_pct = w["used_pct"] | 0.0f;
      win.resets_in_s = w["resets_in_s"] | -1;
      copy_str(win.resets_at, sizeof(win.resets_at), w["resets_at"] | "");
    }
    sort_windows(out);
  }

  if (state.n_order == 0) {
    state.n_order = state.n_providers;
    for (uint8_t i = 0; i < state.n_providers; i++) {
      copy_str(state.order[i], sizeof(state.order[i]), state.providers[i].id);
    }
  }

  state.has_quota = true;
  state.last_quota_ms = millis();
  if (state.page >= state.n_order && state.n_order > 0) state.page = 0;
  state.dirty = true;
}

static void apply_config(AppState &state, JsonDocument &doc) {
  if (!doc["interval_ms"].isNull()) {
    uint32_t ms = doc["interval_ms"].as<uint32_t>();
    if (ms < 1000) ms = 1000;
    if (ms > 60000) ms = 60000;
    state.interval_ms = ms;
  }
  if (!doc["brightness"].isNull()) {
    int b = doc["brightness"].as<int>();
    if (b < 10) b = 10;
    if (b > 255) b = 255;
    state.brightness = (uint8_t)b;
  }
  if (!doc["paused"].isNull()) state.paused = doc["paused"].as<bool>();

  JsonArray order = doc["order"].as<JsonArray>();
  if (!order.isNull()) {
    state.n_order = 0;
    for (JsonVariant v : order) {
      if (state.n_order >= MAX_ORDER) break;
      copy_str(state.order[state.n_order], sizeof(state.order[0]), v.as<const char *>());
      state.n_order++;
    }
    if (state.page >= state.n_order && state.n_order > 0) state.page = 0;
  }
  state.dirty = true;
}

static void handle_line(AppState &state, char *line) {
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, line);
  if (err) {
    Serial.print("{\"type\":\"err\",\"msg\":\"");
    Serial.print(err.c_str());
    Serial.println("\"}");
    return;
  }
  const char *type = doc["type"] | "";
  if (strcmp(type, "quota") == 0) {
    apply_quota(state, doc);
    Serial.println("{\"type\":\"ack\",\"what\":\"quota\"}");
  } else if (strcmp(type, "config") == 0) {
    apply_config(state, doc);
    Serial.println("{\"type\":\"ack\",\"what\":\"config\"}");
  } else if (strcmp(type, "ping") == 0) {
    Serial.println("{\"type\":\"pong\"}");
  }
}

void protocol_begin() {
  Serial.setRxBufferSize(4096);
  Serial.begin(115200);
  uint32_t start = millis();
  while (!Serial && millis() - start < 1500) {
    delay(10);
  }
  line_len = 0;
}

void protocol_send_hello() {
  Serial.println("{\"type\":\"hello\",\"board\":\"t-display-s3\",\"fw\":\"0.1.0\"}");
}

void protocol_send_event(const char *name) {
  Serial.print("{\"type\":\"event\",\"btn\":\"");
  Serial.print(name);
  Serial.println("\"}");
}

void protocol_poll(AppState &state) {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      line_buf[line_len] = 0;
      if (line_len > 0) handle_line(state, line_buf);
      line_len = 0;
      continue;
    }
    if (line_len + 1 < kLineMax) line_buf[line_len++] = c;
    else line_len = 0;
  }
}
