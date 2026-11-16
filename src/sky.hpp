#pragma once
#include <cairo/cairo.h>
#include <bit>
#include <turbojpeg.h>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <hyprland/src/render/Renderer.hpp>
#include <stdexcept>

inline SP<Render::ITexture> loadSky(const std::string &path) {
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error))
        throw std::runtime_error("Skydome must be a regular PNG or JPEG file");
    std::ifstream input(path, std::ios::binary | std::ios::ate);
    const auto size = input.tellg();
    if (!input || size < 24 || size > 32 * 1024 * 1024)
        throw std::runtime_error("Skydome must be a readable PNG or JPEG smaller than 32 MiB");
    std::vector<unsigned char> bytes(static_cast<size_t>(size));
    input.seekg(0);
    if (!input.read(reinterpret_cast<char *>(bytes.data()), size))
        throw std::runtime_error("Cannot read skydome");
    if (bytes[0] == 0xff && bytes[1] == 0xd8) {
        auto decoder = tj3Init(TJINIT_DECOMPRESS);
        if (!decoder)
            throw std::runtime_error("Cannot initialize JPEG decoder");
        Render::CScopeGuard destroyDecoder([&] { tj3Destroy(decoder); });
        tj3Set(decoder, TJPARAM_STOPONWARNING, 1);
        if (tj3DecompressHeader(decoder, bytes.data(), bytes.size()) < 0)
            throw std::runtime_error("Invalid skydome JPEG header");
        int w = tj3Get(decoder, TJPARAM_JPEGWIDTH), h = tj3Get(decoder, TJPARAM_JPEGHEIGHT);
        if (w <= 0 || h <= 0 || w > 16384 || h > 16384 || uint64_t(w) * h > 64 * 1024 * 1024)
            throw std::runtime_error("JPEG source is limited to 16384 pixels per side and 64 megapixels");
        const int sourceWidth = w, sourceHeight = h;
        int count = 0;
        const auto factors = tj3GetScalingFactors(&count);
        tjscalingfactor scale{0, 1};
        for (int i = 0; factors && i < count; ++i) {
            const auto candidate = factors[i];
            const int width = TJSCALED(sourceWidth, candidate), height = TJSCALED(sourceHeight, candidate);
            if (candidate.num <= candidate.denom && width <= 8192 && height <= 8192 &&
                uint64_t(width) * height <= 16 * 1024 * 1024 &&
                candidate.num * scale.denom > scale.num * candidate.denom)
                scale = candidate;
        }
        if (!scale.num || (tj3Get(decoder, TJPARAM_LOSSLESS) && scale.num != scale.denom))
            throw std::runtime_error("JPEG cannot be scaled within skydome texture limits");
        w = TJSCALED(sourceWidth, scale);
        h = TJSCALED(sourceHeight, scale);
        // Decode at the smaller size instead of allocating the full-resolution texture.
        if (tj3SetScalingFactor(decoder, scale) < 0)
            throw std::runtime_error("Cannot scale skydome JPEG");
        auto surface = cairo_image_surface_create(CAIRO_FORMAT_RGB24, w, h);
        Render::CScopeGuard destroySurface([&] { cairo_surface_destroy(surface); });
        if (cairo_surface_status(surface) != CAIRO_STATUS_SUCCESS)
            throw std::runtime_error("Cannot allocate skydome JPEG surface");
        cairo_surface_flush(surface);
        const int format = std::endian::native == std::endian::little ? TJPF_BGRX : TJPF_XRGB;
        if (tj3Decompress8(decoder, bytes.data(), bytes.size(), cairo_image_surface_get_data(surface),
                          cairo_image_surface_get_stride(surface), format) < 0)
            throw std::runtime_error("Invalid skydome JPEG");
        cairo_surface_mark_dirty(surface);
        return g_pHyprRenderer->createTexture(surface);
    }
    constexpr unsigned char signature[] = {137, 80, 78, 71, 13, 10, 26, 10};
    if (std::memcmp(bytes.data(), signature, 8) || std::memcmp(bytes.data() + 12, "IHDR", 4))
        throw std::runtime_error("Skydome must be a PNG or JPEG image");
    auto integer = [&](size_t i) {
        return uint32_t(bytes[i]) << 24 | uint32_t(bytes[i + 1]) << 16 | uint32_t(bytes[i + 2]) << 8 | bytes[i + 3];
    };
    const auto w = integer(16), h = integer(20);
    if (!w || !h || w > 8192 || h > 8192 || uint64_t(w) * h > 16 * 1024 * 1024)
        throw std::runtime_error("Skydome is limited to 8192 pixels per side and 16 megapixels");
    struct Reader {
        const std::vector<unsigned char> &bytes;
        size_t at = 0;
    } reader{bytes};
    auto surface = cairo_image_surface_create_from_png_stream(
        [](void *closure, unsigned char *out, unsigned int length) {
            auto &r = *static_cast<Reader *>(closure);
            if (length > r.bytes.size() - r.at)
                return CAIRO_STATUS_READ_ERROR;
            std::memcpy(out, r.bytes.data() + r.at, length);
            r.at += length;
            return CAIRO_STATUS_SUCCESS;
        },
        &reader);
    Render::CScopeGuard destroy([&] { cairo_surface_destroy(surface); });
    if (cairo_surface_status(surface) != CAIRO_STATUS_SUCCESS)
        throw std::runtime_error("Invalid skydome PNG");
    return g_pHyprRenderer->createTexture(surface);
}
