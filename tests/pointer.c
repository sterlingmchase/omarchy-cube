#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <linux/input-event-codes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <wayland-client.h>
#include "pointer-protocol.h"

static struct zwlr_virtual_pointer_manager_v1 *manager;
static void global(void *data, struct wl_registry *registry, uint32_t name,
                   const char *interface, uint32_t version) {
    (void)data;
    (void)version;
    if (!strcmp(interface, zwlr_virtual_pointer_manager_v1_interface.name))
        manager = wl_registry_bind(registry, name, &zwlr_virtual_pointer_manager_v1_interface, 1);
}
static void removed(void *data, struct wl_registry *registry, uint32_t name) {
    (void)data; (void)registry; (void)name;
}
static long number(const char *value, long min, long max) {
    char *end;
    errno = 0;
    long n = strtol(value, &end, 10);
    if (errno || !*value || *end || n < min || n > max) {
        fprintf(stderr, "invalid bounded integer: %s\n", value);
        exit(2);
    }
    return n;
}
static uint32_t now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}
int main(int argc, char **argv) {
    if (argc < 3) {
        fprintf(stderr, "usage: pointer DISPLAY [move X Y WIDTH HEIGHT|down|up|rightdown|rightup|scroll DELTA|wait MS]...\n");
        return 2;
    }
    struct wl_display *display = wl_display_connect(argv[1]);
    if (!display) { perror("connect explicit test display"); return 1; }
    struct wl_registry *registry = wl_display_get_registry(display);
    static const struct wl_registry_listener listener = {global, removed};
    wl_registry_add_listener(registry, &listener, NULL);
    if (wl_display_roundtrip(display) < 0 || !manager) {
        fprintf(stderr, "virtual pointer unavailable\n"); return 1;
    }
    struct zwlr_virtual_pointer_v1 *pointer = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(manager, NULL);
    if (wl_display_roundtrip(display) < 0) return 1;
    for (int i = 2; i < argc; i++) {
        const char *command = argv[i];
        if (!strcmp(command, "move") && i + 4 < argc) {
            uint32_t x = number(argv[++i], 0, 32768), y = number(argv[++i], 0, 32768);
            uint32_t w = number(argv[++i], 1, 32768), h = number(argv[++i], 1, 32768);
            if (x > w || y > h) return 2;
            zwlr_virtual_pointer_v1_motion_absolute(pointer, now(), x, y, w, h);
        } else if (!strcmp(command, "down") || !strcmp(command, "up") ||
                   !strcmp(command, "rightdown") || !strcmp(command, "rightup")) {
            zwlr_virtual_pointer_v1_button(pointer, now(), !strncmp(command, "right", 5) ? BTN_RIGHT : BTN_LEFT,
                strstr(command, "down") ? WL_POINTER_BUTTON_STATE_PRESSED : WL_POINTER_BUTTON_STATE_RELEASED);
        } else if (!strcmp(command, "scroll") && i + 1 < argc) {
            int delta = number(argv[++i], -120, 120);
            zwlr_virtual_pointer_v1_axis_source(pointer, WL_POINTER_AXIS_SOURCE_WHEEL);
            zwlr_virtual_pointer_v1_axis_discrete(pointer, now(), WL_POINTER_AXIS_VERTICAL_SCROLL,
                wl_fixed_from_int(delta * 15), delta);
        } else if (!strcmp(command, "wait") && i + 1 < argc) {
            long ms = number(argv[++i], 0, 1000);
            struct timespec duration = {.tv_sec = ms / 1000, .tv_nsec = ms % 1000 * 1000000};
            nanosleep(&duration, NULL);
        } else { fprintf(stderr, "invalid command: %s\n", command); return 2; }
        zwlr_virtual_pointer_v1_frame(pointer);
        if (wl_display_roundtrip(display) < 0) return 1;
    }
    zwlr_virtual_pointer_v1_destroy(pointer);
    zwlr_virtual_pointer_manager_v1_destroy(manager);
    wl_registry_destroy(registry);
    if (wl_display_roundtrip(display) < 0) return 1;
    wl_display_disconnect(display);
    return 0;
}
