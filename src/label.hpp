#pragma once
#include <algorithm>
#include <hyprland/src/render/Renderer.hpp>
#include <pango/pangocairo.h>
#include <stdexcept>
#include <string>

inline SP<Render::ITexture> makeWorkspaceLabel(int id, const std::string &name) {
    const auto number = std::to_string(id);
    auto valid = g_utf8_make_valid(name.data(), std::min<size_t>(name.size(), 1024));
    Render::CScopeGuard freeName([&] { g_free(valid); });
    const std::string text = name.empty() || name == number ? "Workspace " + number : number + " · " + valid;
    auto surface = cairo_image_surface_create(CAIRO_FORMAT_ARGB32, 768, 80);
    Render::CScopeGuard destroySurface([&] { cairo_surface_destroy(surface); });
    if (cairo_surface_status(surface) != CAIRO_STATUS_SUCCESS)
        throw std::runtime_error("Cannot allocate workspace label surface");
    auto cr = cairo_create(surface);
    Render::CScopeGuard destroyContext([&] { cairo_destroy(cr); });
    cairo_set_operator(cr, CAIRO_OPERATOR_CLEAR);
    cairo_paint(cr);
    cairo_set_operator(cr, CAIRO_OPERATOR_OVER);
    cairo_set_source_rgba(cr, 0.035, 0.045, 0.065, 0.82);
    cairo_arc(cr, 40, 40, 40, 1.5707963267948966, 4.71238898038469);
    cairo_arc(cr, 728, 40, 40, 4.71238898038469, 7.853981633974483);
    cairo_close_path(cr);
    cairo_fill(cr);
    auto layout = pango_cairo_create_layout(cr);
    Render::CScopeGuard destroyLayout([&] { g_object_unref(layout); });
    auto font = pango_font_description_from_string("Sans Bold 28px");
    Render::CScopeGuard destroyFont([&] { pango_font_description_free(font); });
    pango_layout_set_font_description(layout, font);
    pango_layout_set_text(layout, text.c_str(), -1);
    pango_layout_set_width(layout, 704 * PANGO_SCALE);
    pango_layout_set_ellipsize(layout, PANGO_ELLIPSIZE_END);
    pango_layout_set_single_paragraph_mode(layout, true);
    pango_layout_set_alignment(layout, PANGO_ALIGN_CENTER);
    int height = 0;
    pango_layout_get_pixel_size(layout, nullptr, &height);
    cairo_move_to(cr, 32, (80 - height) / 2.0);
    cairo_set_source_rgba(cr, 1, 1, 1, 1);
    pango_cairo_show_layout(cr, layout);
    if (cairo_status(cr) != CAIRO_STATUS_SUCCESS)
        throw std::runtime_error("Cannot render workspace label");
    return g_pHyprRenderer->createTexture(surface);
}
