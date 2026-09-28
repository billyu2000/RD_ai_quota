#include "net.h"

#include <DNSServer.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>

static const char *kApSsid = "AI-Quota-Setup";

static Preferences prefs;
static WebServer *portal = nullptr;
static DNSServer *dns = nullptr;
static WiFiClient client;

static bool portal_mode = false;
static bool sta_started = false;

static char cfg_ssid[33] = "";
static char cfg_pass[65] = "";
static char cfg_host[64] = "";
static uint16_t cfg_port = 8788;

static uint32_t last_wifi_retry = 0;
static uint32_t last_tcp_retry = 0;
static uint32_t last_stale_check = 0;

static const size_t kNetLineMax = 2048;
static char net_line[kNetLineMax];
static size_t net_line_len = 0;

static void load_prefs() {
  prefs.begin("aiquota", true);
  prefs.getString("ssid", cfg_ssid, sizeof(cfg_ssid));
  prefs.getString("pass", cfg_pass, sizeof(cfg_pass));
  prefs.getString("host", cfg_host, sizeof(cfg_host));
  cfg_port = prefs.getUShort("port", 8788);
  prefs.end();
}

static void save_wifi(const char *ssid, const char *pass, const char *host, uint16_t port) {
  prefs.begin("aiquota", false);
  prefs.putString("ssid", ssid);
  prefs.putString("pass", pass);
  prefs.putString("host", host);
  prefs.putUShort("port", port);
  prefs.putUChar("force_portal", 0);
  prefs.end();
}

static void clear_force_flag() {
  prefs.begin("aiquota", false);
  prefs.putUChar("force_portal", 0);
  prefs.end();
}

static void portal_done_page(const char *msg) {
  portal->send(200, "text/html", String("<!DOCTYPE html><html><head><meta charset='utf-8'>"
                                       "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                                       "<title>AI Quota</title></head><body style='font-family:sans-serif;"
                                       "background:#0c0c10;color:#e8e8ee;padding:24px'><h2>") +
                                       msg + "</h2><p>device is rebooting...</p></body></html>");
}

static void portal_root() {
  String options = "";
  int n = WiFi.scanComplete();
  if (n == WIFI_SCAN_FAILED || n == WIFI_SCAN_RUNNING) n = -1;
  if (n < 0) {
    WiFi.scanNetworks(true);
  } else {
    for (int i = 0; i < n && i < 15; i++) {
      String ssid = WiFi.SSID(i);
      ssid.replace("'", "&#39;");
      String sel = (ssid == String(cfg_ssid)) ? " selected" : "";
      options += "<option value='" + ssid + "'" + sel + ">" + ssid + " (" + WiFi.RSSI(i) + " dBm)</option>";
    }
  }
  char ip_buf[24];
  IPAddress ip = WiFi.softAPIP();
  snprintf(ip_buf, sizeof(ip_buf), "%u.%u.%u.%u", ip[0], ip[1], ip[2], ip[3]);
  String page = String(R"HTML(<!DOCTYPE html><html><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>AI Quota Setup</title><style>
body{font-family:-apple-system,sans-serif;background:#0c0c10;color:#e8e8ee;max-width:420px;margin:0 auto;padding:20px}
h1{font-size:1.3em}label{display:block;margin:14px 0 4px;font-size:.85em;color:#a0a0aa}
input,select{width:100%;box-sizing:border-box;padding:10px;border-radius:8px;border:1px solid #333;
background:#16161c;color:#e8e8ee;font-size:1em}
button{margin-top:18px;width:100%;padding:12px;border:0;border-radius:8px;background:#34d399;
color:#0c0c10;font-weight:600;font-size:1em}
.small{font-size:.75em;color:#70707a;margin-top:4px}
</style></head><body>
<h1>AI Quota — Display Setup</h1>
<form method='POST' action='/save'>
<label>WiFi network</label><select name='ssid'>)HTML") +
               options +
               R"HTML(</select>
<label>WiFi password</label><input name='pass' type='password' autocomplete='off'>
<label>Host — the Mac running ai_quota</label>
<input name='host' placeholder='e.g. 192.168.1.5' value=)HTML";
  page += String("'") + cfg_host + "'>";
  page += R"HTML(
<label>Port</label><input name='port' type='number' value=)HTML";
  page += String("'") + String(cfg_port) + "'>";
  page += R"HTML(
<button type='submit'>Save &amp; connect</button>
</form>
<form method='POST' action='/clear'><button type='submit' style='background:#444;color:#e8e8ee'>Use USB only</button></form>
<form method='POST' action='/cancel'><button type='submit' style='background:transparent;color:#70707a;border:1px solid #333'>Cancel</button></form>
<p class='small'>Join this setup network again anytime: hold BOOT on the device for 3 seconds.</p>
</body></html>)HTML";
  portal->send(200, "text/html", page);
}

static void portal_save() {
  String ssid = portal->arg("ssid");
  ssid.replace("'", "");
  String pass = portal->arg("pass");
  String host = portal->arg("host");
  host.trim();
  long port = portal->arg("port").toInt();
  if (port < 1 || port > 65535) port = 8788;
  if (host.length() == 0 || ssid.length() == 0) {
    portal->send(400, "text/html", "<html><body><h2>ssid and host are required</h2><a href='/'>back</a></body></html>");
    return;
  }
  save_wifi(ssid.c_str(), pass.c_str(), host.c_str(), (uint16_t)port);
  portal_done_page("Saved. Connecting to WiFi...");
  delay(1200);
  ESP.restart();
}

static void portal_clear() {
  save_wifi("", "", "", 0);
  portal_done_page("WiFi cleared. USB only mode...");
  delay(1200);
  ESP.restart();
}

static void portal_cancel() {
  clear_force_flag();
  portal_done_page("Setup cancelled...");
  delay(1200);
  ESP.restart();
}

static void start_portal() {
  portal_mode = true;
  WiFi.mode(WIFI_AP);
  WiFi.softAP(kApSsid);
  IPAddress ip = WiFi.softAPIP();
  dns = new DNSServer();
  dns->start(53, "*", ip);
  portal = new WebServer(80);
  portal->on("/", portal_root);
  portal->on("/save", HTTP_POST, portal_save);
  portal->on("/clear", HTTP_POST, portal_clear);
  portal->on("/cancel", HTTP_POST, portal_cancel);
  portal->onNotFound([]() { portal->sendHeader("Location", "http://" + WiFi.softAPIP().toString() + "/", true); portal->send(302, "text/plain", ""); });
  portal->begin();
}

void net_begin(AppState &state) {
  load_prefs();
  prefs.begin("aiquota", true);
  uint8_t force = prefs.getUChar("force_portal", 0);
  prefs.end();
  if (force) {
    start_portal();
    state.portal_mode = true;
    state.dirty = true;
    return;
  }
  if (cfg_ssid[0] == '\0') return;
  WiFi.mode(WIFI_STA);
  WiFi.setAutoReconnect(true);
  WiFi.begin(cfg_ssid, cfg_pass);
  sta_started = true;
  last_wifi_retry = millis();
}

void net_poll(AppState &state, void (*on_line)(AppState &, char *)) {
  if (portal_mode) {
    dns->processNextRequest();
    portal->handleClient();
    return;
  }
  if (!sta_started) return;

  uint32_t now = millis();
  bool wifi_up = WiFi.status() == WL_CONNECTED;
  if (!wifi_up && now - last_wifi_retry > 20000) {
    WiFi.reconnect();
    last_wifi_retry = now;
  }
  if (state.wifi_up != wifi_up) {
    state.wifi_up = wifi_up;
    state.dirty = true;
  }

  bool server_up = client.connected();
  if (wifi_up && !server_up && now - last_tcp_retry > 5000) {
    last_tcp_retry = now;
    client.stop();
    if (client.connect(cfg_host, cfg_port)) {
      client.println("{\"type\":\"hello\",\"board\":\"t-display-s3\",\"fw\":\"0.2.0\",\"via\":\"wifi\"}");
      server_up = true;
    } else {
      client.stop();
    }
  }
  if (state.server_up != server_up) {
    state.server_up = server_up;
    state.dirty = true;
  }
  if (last_stale_check == 0) last_stale_check = now;

  while (client.available() > 0) {
    char c = (char)client.read();
    if (c == '\r') continue;
    if (c == '\n') {
      net_line[net_line_len] = 0;
      if (net_line_len > 0 && on_line) on_line(state, net_line);
      net_line_len = 0;
      continue;
    }
    if (net_line_len + 1 < kNetLineMax) net_line[net_line_len++] = c;
    else net_line_len = 0;
  }
}

bool net_send_line(const char *line) {
  if (!client.connected()) return false;
  client.println(line);
  return true;
}

void net_enter_portal() {
  prefs.begin("aiquota", false);
  prefs.putUChar("force_portal", 1);
  prefs.end();
  delay(100);
  ESP.restart();
}

bool net_portal_active() { return portal_mode; }
bool net_wifi_configured() { return cfg_ssid[0] != '\0'; }
