#include "display.h"

#include <TFT_eSPI.h>

#include "icons.h"

static const int PIN_POWER_ON = 15;
static const int PIN_BL = 38;

static TFT_eSPI tft;

static uint16_t rgb(uint8_t r, uint8_t g, uint8_t b) {
  return tft.color565(r, g, b);
}

static uint16_t brand_color(const char *id) {
  if (strcmp(id, "claude") == 0) return rgb(217, 119, 87);
  if (strcmp(id, "codex") == 0) return rgb(16, 163, 127);
  if (strcmp(id, "grok") == 0) return rgb(230, 230, 230);
  if (strcmp(id, "zai") == 0) return rgb(59, 130, 246);
  return rgb(160, 160, 160);
}

static uint16_t pct_color(float used) {
  if (used < 70.0f) return rgb(52, 211, 153);
  if (used < 90.0f) return rgb(251, 191, 36);
  return rgb(248, 113, 113);
}

static const uint16_t *icon_for(const char *id) {
  if (strcmp(id, "claude") == 0) return icon_claude;
  if (strcmp(id, "codex") == 0) return icon_codex;
  if (strcmp(id, "grok") == 0) return icon_grok;
  if (strcmp(id, "zai") == 0) return icon_zai;
  return nullptr;
}

static void draw_icon(const char *id, int x, int y) {
  const uint16_t *img = icon_for(id);
  if (!img) return;
  tft.setSwapBytes(true);
  tft.pushImage(x, y, ICON_SIZE, ICON_SIZE, img);
  tft.setSwapBytes(false);
}

static const Provider *find_provider(const AppState &state, const char *id) {
  for (uint8_t i = 0; i < state.n_providers; i++) {
    if (strcmp(state.providers[i].id, id) == 0) return &state.providers[i];
  }
  return nullptr;
}

static void fmt_reset(int32_t seconds, char *out, size_t n) {
  if (seconds < 0) {
    out[0] = 0;
    return;
  }
  int days = seconds / 86400;
  int hours = (seconds % 86400) / 3600;
  int mins = (seconds % 3600) / 60;
  if (days > 0) snprintf(out, n, "resets %dd %dh", days, hours);
  else if (hours > 0) snprintf(out, n, "resets %dh %dm", hours, mins);
  else snprintf(out, n, "resets %dm", mins);
}

static void draw_bar(int x, int y, int w, int h, float used, uint16_t col) {
  if (used < 0) used = 0;
  if (used > 100) used = 100;
  tft.drawRect(x, y, w, h, rgb(60, 60, 68));
  int fill = (int)((w - 2) * used / 100.0f);
  if (fill > 0) tft.fillRect(x + 1, y + 1, fill, h - 2, col);
}

static void draw_waiting() {
  tft.fillScreen(rgb(12, 12, 16));
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(rgb(220, 220, 220), rgb(12, 12, 16));
  tft.drawString("AI Quota", 160, 64, 4);
  tft.setTextColor(rgb(140, 140, 150), rgb(12, 12, 16));
  tft.drawString("waiting for Mac", 160, 104, 2);
  tft.setTextColor(rgb(90, 90, 100), rgb(12, 12, 16));
  tft.drawString("hold BOOT 3s = wifi setup", 160, 150, 1);
}

static void draw_portal_screen() {
  tft.fillScreen(rgb(12, 12, 16));
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(rgb(220, 220, 220), rgb(12, 12, 16));
  tft.drawString("AI Quota Setup", 160, 38, 4);
  tft.setTextColor(rgb(120, 200, 160), rgb(12, 12, 16));
  tft.drawString("join WiFi:", 160, 76, 2);
  tft.setTextColor(rgb(240, 240, 245), rgb(12, 12, 16));
  tft.drawString("AI-Quota-Setup", 160, 98, 2);
  tft.setTextColor(rgb(120, 200, 160), rgb(12, 12, 16));
  tft.drawString("then open", 160, 124, 2);
  tft.setTextColor(rgb(240, 240, 245), rgb(12, 12, 16));
  tft.drawString("http://192.168.4.1", 160, 148, 2);
}

void draw_transport_badge(const AppState &state) {
  if (state.portal_mode) return;
  int x = 316;
  if (state.server_up) {
    tft.fillCircle(x, 17, 4, rgb(52, 211, 153));
    tft.drawCircle(x, 17, 6, rgb(52, 211, 153));
  } else if (state.wifi_up) {
    tft.fillCircle(x, 17, 4, rgb(251, 191, 36));
  }
}

static void draw_stale_badge() {
  tft.fillRoundRect(252, 8, 56, 18, 3, rgb(90, 70, 20));
  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(rgb(255, 220, 140), rgb(90, 70, 20));
  tft.drawString("STALE", 280, 17, 2);
}

void display_begin(uint8_t brightness) {
  pinMode(PIN_POWER_ON, OUTPUT);
  digitalWrite(PIN_POWER_ON, HIGH);
  delay(20);
  tft.init();
  tft.setRotation(1);
  tft.fillScreen(rgb(12, 12, 16));
  ledcSetup(0, 5000, 8);
  ledcAttachPin(PIN_BL, 0);
  display_set_brightness(brightness);
  draw_waiting();
}

void display_set_brightness(uint8_t brightness) {
  ledcWrite(0, brightness);
}

void display_render(const AppState &state) {
  if (state.portal_mode) {
    draw_portal_screen();
    return;
  }
  if (!state.has_quota || state.n_order == 0) {
    draw_waiting();
    draw_transport_badge(state);
    return;
  }

  uint32_t age = millis() - state.last_quota_ms;
  if (age > 60000 && state.last_quota_ms != 0) {
    draw_waiting();
    return;
  }

  uint8_t page = state.page % state.n_order;
  const char *id = state.order[page];
  const Provider *p = find_provider(state, id);

  tft.fillScreen(rgb(16, 16, 20));
  uint16_t brand = p ? brand_color(p->id) : rgb(90, 90, 90);
  tft.fillRect(0, 0, 10, 170, brand);

  const char *name = p ? p->name : id;
  const char *icon_id = p ? p->id : id;
  draw_icon(icon_id, 16, 6);
  tft.setTextDatum(TL_DATUM);
  tft.setTextColor(rgb(245, 245, 245), rgb(16, 16, 20));
  tft.drawString(name, 54, 10, 4);

  if (state.paused) {
    tft.fillRoundRect(190, 8, 54, 18, 3, rgb(50, 50, 60));
    tft.setTextDatum(MC_DATUM);
    tft.setTextColor(rgb(210, 210, 220), rgb(50, 50, 60));
    tft.drawString("PAUSE", 217, 17, 2);
  }

  if (age > 15000) draw_stale_badge();

  if (!p || strcmp(p->status, "ok") != 0) {
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(rgb(248, 180, 120), rgb(16, 16, 20));
    const char *msg = "no data";
    if (p && strcmp(p->status, "no_creds") == 0) msg = "no key";
    else if (p && strcmp(p->status, "error") == 0) msg = "error";
    else if (p && p->status[0]) msg = p->status;
    tft.drawString(msg, 22, 78, 4);
  } else {
    float hero = p->n_windows ? p->windows[0].used_pct : 0;
    int32_t reset = p->n_windows ? p->windows[0].resets_in_s : -1;
    const char *reset_at = p->n_windows ? p->windows[0].resets_at : "";

    char pct[16];
    snprintf(pct, sizeof(pct), "%.0f", hero);
    tft.setTextDatum(TL_DATUM);
    tft.setTextColor(pct_color(hero), rgb(16, 16, 20));
    tft.drawString(pct, 22, 42, 6);
    int x = 22 + tft.textWidth(pct, 6);
    tft.setTextColor(rgb(160, 160, 170), rgb(16, 16, 20));
    tft.drawString("%", x + 2, 62, 4);
    x += tft.textWidth("%", 4) + 8;

    if (p->n_windows >= 2) {
      char extra[20];
      snprintf(extra, sizeof(extra), "(%.0f%%)", p->windows[1].used_pct);
      tft.setTextColor(pct_color(p->windows[1].used_pct), rgb(16, 16, 20));
      tft.drawString(extra, x, 66, 2);
    }

    int bar_x = 22;
    int bar_w = 286;
    int label_w = 52;
    int y = 94;
    uint8_t shown = p->n_windows < 2 ? p->n_windows : 2;
    for (uint8_t i = 0; i < shown; i++) {
      const QuotaWindow &w = p->windows[i];
      tft.setTextDatum(TL_DATUM);
      tft.setTextColor(rgb(170, 170, 180), rgb(16, 16, 20));
      tft.drawString(w.label, bar_x, y - 2, 2);
      draw_bar(bar_x + label_w, y, bar_w - label_w - 40, 12, w.used_pct, pct_color(w.used_pct));
      char used[12];
      snprintf(used, sizeof(used), "%.0f%%", w.used_pct);
      tft.setTextDatum(TR_DATUM);
      tft.setTextColor(rgb(210, 210, 215), rgb(16, 16, 20));
      tft.drawString(used, bar_x + bar_w, y, 2);
      y += 20;
    }

    char reset_s[24];
    fmt_reset(reset, reset_s, sizeof(reset_s));
    int text_y = 134;
    tft.setTextDatum(TL_DATUM);
    if (reset_at && reset_at[0]) {
      tft.setTextColor(rgb(220, 220, 225), rgb(16, 16, 20));
      tft.drawString(reset_at, 22, text_y, 2);
      text_y += 14;
    }
    tft.setTextColor(rgb(150, 150, 160), rgb(16, 16, 20));
    tft.drawString(reset_s, 22, text_y, 2);
  }

  int dots = state.n_order;
  int start = 248;
  for (uint8_t i = 0; i < dots; i++) {
    uint16_t c = (i == page) ? brand : rgb(60, 60, 68);
    tft.fillCircle(start + i * 12, 158, 3, c);
  }

  draw_transport_badge(state);
}
