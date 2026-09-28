#pragma once

#include "types.h"

void protocol_begin();
void protocol_poll(AppState &state);
void protocol_feed(AppState &state, char *line);
void protocol_send_hello();
void protocol_send_event(const char *name);
