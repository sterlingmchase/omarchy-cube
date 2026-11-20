#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <optional>
#include <vector>
namespace Cube {
constexpr double pi = 3.141592653589793;
inline int next(int workspace, int direction, int count = 4) {
    return ((workspace - 1 + direction) % count + count) % count + 1;
}
inline double progress(double ms, double duration = 280) {
    return std::clamp(ms / duration, 0.0, 1.0);
}
inline double ease(double t) {
    return t * t * (3.0 - 2.0 * t);
}
// Fractions of the available overscan margin; never reveal a texture edge.
inline std::array<double, 2> backdropParallax(double yaw, double pitch, bool motion) {
    if (!motion || !std::isfinite(yaw) || !std::isfinite(pitch)) return {0, 0};
    return {-.65 * std::sin(yaw), -.65 * std::clamp(pitch / (pi / 4), -1.0, 1.0)};
}
inline double releaseTarget(double angle, double velocity, double age, bool momentum) {
    const double nearest = std::round(angle);
    if (!momentum || age > .12 || std::abs(velocity) < 1.8)
        return nearest;
    return std::clamp(std::round(angle + std::clamp(velocity * .12, -1.0, 1.0)), nearest - 1, nearest + 1);
}
inline double radius(int count) {
    return 1.0 / std::tan(pi / count);
}
constexpr int curveSegments = 24;
inline double curveDepth(int count, double curvature) {
    if (!std::isfinite(curvature)) return 0;
    // Keep adjacent prism walls from crossing, including on twenty-face prisms.
    return .24 * std::clamp(curvature, -1.0, 1.0) * std::min(1.0, 1.0 / radius(count));
}
// x bounds, slope and intercept for the exact piecewise-linear rendered strip.
inline std::array<double, 4> curveStrip(int strip, double depth) {
    const double left = -1.0 + 2.0 * strip / curveSegments;
    const double right = -1.0 + 2.0 * (strip + 1) / curveSegments;
    const double slope = -depth * (left + right);
    return {left, right, slope, depth * (1.0 + left * right)};
}
inline double zoomDistance(int count, double zoom) {
    return zoom * std::max(1.0, 2 * radius(count) - 1);
}
// Conservative visibility over the whole turn, so each needed face is captured only once.
inline std::vector<int> visibleFaces(int count, int direction, double zoom) {
    const double step = 2 * pi / count;
    const double limit = std::acos(radius(count) / (radius(count) + 2 + zoom));
    std::vector<int> result;
    for (int i = -count / 2; i <= (count - 1) / 2; ++i) {
        const double a = i * step, b = (i - direction) * step;
        if (std::min(a, b) <= limit && std::max(a, b) >= -limit)
            result.push_back(i);
    }
    return result;
}
inline bool frontFacing(double angle, double radius, double distance, double pitch = 0, double depth = 0) {
    if (depth == 0) return distance * std::cos(pitch) * std::cos(angle) > radius;
    const double cameraX = -distance * std::cos(pitch) * std::sin(angle);
    const double cameraZ = distance * std::cos(pitch) * std::cos(angle);
    for (int strip = 0; strip < curveSegments; ++strip) {
        const auto plane = curveStrip(strip, depth);
        if (cameraZ - plane[2] * cameraX > radius + plane[3]) return true;
    }
    return false;
}
// Conservative rectangle inside one opaque face; skip backdrop fragments covered by it.
inline std::array<double, 4> coveredRect(int count, double rotation, double distance, double pitch = 0, int face = -1) {
    std::array<double, 4> best{};
    double area = 0;
    const double r = radius(count), cp = std::cos(pitch), sp = std::sin(pitch);
    for (int i = face < 0 ? 0 : face; i < (face < 0 ? count : face + 1); ++i) {
        const double a = (i - rotation) * 2 * pi / count, c = std::cos(a), s = std::sin(a);
        if (!frontFacing(a, r, distance, pitch)) continue;
        std::array<double, 4> x{}, y{};
        for (int v = 0; v < 4; ++v) {
            const double lx = (v & 1) ? 1 : -1, ly = (v & 2) ? 1 : -1;
            const double z = -lx * s + r * c;
            const double w = distance - (ly * sp + z * cp);
            x[v] = 2 * (lx * c + r * s) / w;
            y[v] = 2 * (ly * cp - z * sp) / w;
        }
        std::array<double, 4> rect{std::max({-1., x[0], x[2]}), std::max({-1., y[0], y[1]}),
                                   std::min({1., x[1], x[3]}), std::min({1., y[2], y[3]})};
        const double candidate = std::max(0., rect[2] - rect[0]) * std::max(0., rect[3] - rect[1]);
        if (candidate > area) { area = candidate; best = rect; }
    }
    return best;
}
// Ray against the same face planes used by the vertex shader; x/y are NDC coordinates.
struct FaceHit { int face; double u, v; };
inline std::optional<FaceHit> hitFacePoint(int count, double rotation, double distance, double x, double y, double pitch = 0, double curvature = 0) {
    std::optional<FaceHit> result;
    double nearest = std::numeric_limits<double>::infinity();
    const double r = radius(count), depth = curveDepth(count, curvature);
    const double cp = std::cos(pitch), sp = std::sin(pitch);
    // Undo the shader's X rotation on the camera and ray before intersecting the walls.
    const double cameraY = distance * sp, cameraZ = distance * cp;
    const double rayY = y * cp / 2 - sp, rayZ = -y * sp / 2 - cp;
    for (int i = 0; i < count; ++i) {
        const double angle = (i - rotation) * 2 * pi / count;
        const double c = std::cos(angle), s = std::sin(angle);
        const double localCameraX = -cameraZ * s, localCameraZ = cameraZ * c;
        const double localRayX = x * c / 2 - rayZ * s, localRayZ = x * s / 2 + rayZ * c;
        for (int strip = 0; strip < (depth == 0 ? 1 : curveSegments); ++strip) {
            const auto plane = depth == 0 ? std::array<double,4>{-1,1,0,0} : curveStrip(strip, depth);
            if (localCameraZ - plane[2] * localCameraX <= r + plane[3]) continue;
            const double denominator = localRayZ - plane[2] * localRayX;
            if (std::abs(denominator) < 1e-9) continue;
            const double t = (r + plane[3] + plane[2] * localCameraX - localCameraZ) / denominator;
            const double px = localCameraX + t * localRayX, py = cameraY + t * rayY;
            if (t > 0 && t < nearest && px >= plane[0] - 1e-9 && px <= plane[1] + 1e-9 && std::abs(py) <= 1) {
                nearest = t;
                result = FaceHit{i, (px + 1) / 2, (py + 1) / 2};
            }
        }
    }
    return result;
}
inline std::optional<int> hitFace(int count, double rotation, double distance, double x, double y, double pitch = 0, double curvature = 0) {
    auto hit = hitFacePoint(count, rotation, distance, x, y, pitch, curvature);
    return hit ? std::optional<int>(hit->face) : std::nullopt;
}
} // namespace Cube
