#pragma once

#include "types.h"

void display_begin(uint8_t brightness);
void display_set_brightness(uint8_t brightness);
void display_render(const AppState &state);
void draw_transport_badge(const AppState &state);
