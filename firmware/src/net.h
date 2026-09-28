#pragma once

#include <Arduino.h>

#include "types.h"

void net_begin(AppState &state);
void net_poll(AppState &state, void (*on_line)(AppState &, char *));
bool net_send_line(const char *line);
void net_enter_portal();
bool net_portal_active();
bool net_wifi_configured();
