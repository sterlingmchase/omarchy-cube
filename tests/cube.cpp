#include "../src/cube.hpp"
#include <cassert>
int main() {
    assert((Cube::backdropParallax(1, .5, false) == std::array<double, 2>{0, 0}));
    assert((Cube::backdropParallax(std::numeric_limits<double>::infinity(), 0, true) == std::array<double, 2>{0, 0}));
    assert(Cube::backdropParallax(.5, .2, true)[0] < 0);
    assert(Cube::backdropParallax(.5, .2, true)[1] < 0);
    for (double yaw = -40; yaw < 40; yaw += .13)
        for (double pitch : {-10., -Cube::pi/4, 0., Cube::pi/4, 10.}) {
            auto p = Cube::backdropParallax(yaw, pitch, true);
            for (double value : p) assert(std::isfinite(value) && std::abs(value) <= .65);
            for (double aspect : {.25, 9./16, 16./9, 32./9, 8.})
                for (double source : {.25, 1., 2., 4.}) {
                    std::array<double,2> span{std::min(1., aspect/source)/1.10, std::min(1., source/aspect)/1.10};
                    for (int axis = 0; axis < 2; ++axis)
                        for (double edge : {0., 1.}) {
                            double uv = .5 + (edge-.5)*span[axis] + p[axis]*(1-span[axis])*.5;
                            assert(uv > 0 && uv < 1); // no exposed borders, including ultrawide/portrait
                        }
                }
        }
    for (int count : {4, 5, 8, 12, 20})
        for (double curvature : {-1., -.5, 0., .5, 1.})
            for (double rotation : {-.2, 0., .2})
                for (double pitch : {-Cube::pi/4, -.35, 0., .35, Cube::pi/4}) {
                    const double r = Cube::radius(count), depth = Cube::curveDepth(count, curvature), distance = r + 3;
                    for (double u : {.08, .25, .5, .75, .92})
                        for (double v : {.1, .5, .9}) {
                            const double lx = u*2-1, ly = v*2-1;
                            const int strip = std::clamp(int(u*Cube::curveSegments), 0, Cube::curveSegments-1);
                            const auto plane = Cube::curveStrip(strip, depth);
                            assert(std::abs(plane[2]) < 1/r);
                            const double wall = r + plane[2]*lx + plane[3];
                            const double a = -rotation*2*Cube::pi/count, c = std::cos(a), s = std::sin(a);
                            const double px = lx*c + wall*s, z = -lx*s + wall*c;
                            const double py = ly*std::cos(pitch)-z*std::sin(pitch);
                            const double pz = ly*std::sin(pitch)+z*std::cos(pitch);
                            const double x = 2*px/(distance-pz), y = 2*py/(distance-pz);
                            auto hit = Cube::hitFacePoint(count,rotation,distance,x,y,pitch,curvature);
                            assert(hit && hit->face == 0);
                            assert(std::abs(hit->u-u)<1e-7 && std::abs(hit->v-v)<1e-7);
                        }
                }
    assert(Cube::curveDepth(4, 0) == 0);
    assert(Cube::curveDepth(4, 100) == Cube::curveDepth(4, 1));
    assert(Cube::curveDepth(4, std::numeric_limits<double>::quiet_NaN()) == 0);
    assert(Cube::releaseTarget(.7, 8, .01, false) == 1);
    assert(Cube::releaseTarget(.7, 8, .01, true) == 2);
    assert(Cube::releaseTarget(-.7, -8, .01, true) == -2);
    assert(Cube::releaseTarget(.7, 8, .2, true) == 1);
    assert(Cube::releaseTarget(.2, 1, .01, true) == 0);
    for (double angle = -40; angle < 40; angle += .13)
        for (double velocity : {-100.0, -5.0, 0.0, 5.0, 100.0})
            assert(std::abs(Cube::releaseTarget(angle, velocity, 0, true) - std::round(angle)) <= 1);
    for (int i = 1; i <= 4; ++i) {
        assert(Cube::next(Cube::next(i, 1), -1) == i);
        int ws = i;
        for (int n = 0; n < 4; ++n)
            ws = Cube::next(ws, 1);
        assert(ws == i);
    }
    assert(Cube::next(4, 1) == 1 && Cube::next(1, -1) == 4);
    assert(Cube::progress(-1) == 0 && Cube::progress(280) == 1 && Cube::progress(999) == 1);
    assert(Cube::ease(0) == 0 && Cube::ease(1) == 1);
    double previous = 0;
    for (int ms = 0; ms < 300; ++ms) {
        const double p = Cube::ease(Cube::progress(ms));
        assert(p >= previous && p <= 1);
        previous = p;
    }
    for (int count = 4; count <= 20; ++count) {
        for (int direction : {-1, 1}) {
            const auto faces = Cube::visibleFaces(count, direction, Cube::zoomDistance(count, .7));
            assert(faces.size() <= 10);
            for (int frame = 0; frame <= 280; ++frame) {
                const double p = Cube::ease(Cube::progress(frame));
                const double distance = Cube::radius(count) + 2 + Cube::zoomDistance(count, .7) * std::sin(Cube::pi * p);
                for (int i = -count / 2; i <= (count - 1) / 2; ++i) {
                    if (std::cos((i - direction * p) * 2 * Cube::pi / count) > Cube::radius(count) / distance)
                        assert(std::find(faces.begin(), faces.end(), i) != faces.end());
                }
            }
        }
        assert(Cube::next(count, 1, count) == 1);
        assert(Cube::next(1, -1, count) == count);
    }
    assert(Cube::visibleFaces(4, 1, .7).size() == 2);
    assert(Cube::progress(120, 120) == 1 && Cube::progress(300, 600) == .5);
    for (int n = 4; n <= 20; ++n) {
        const double d = Cube::radius(n) + 2 + Cube::zoomDistance(n, .7);
        for (int front = 0; front < n; ++front) {
            assert(Cube::hitFace(n, front, d, 0, 0) == front);
            assert(!Cube::hitFace(n, front, d, 0, 10));
            // Project an interior point of every visible face and invert it.
            for (int face = 0; face < n; ++face) {
                const double a = (face - front) * 2 * Cube::pi / n;
                if (std::cos(a) <= Cube::radius(n) / d)
                    continue;
                const double x = Cube::radius(n) * std::sin(a), z = Cube::radius(n) * std::cos(a);
                assert(Cube::hitFace(n, front, d, 2 * x / (d - z), .2 / (d - z)) == face);
            }
        }
    }
    for (int n = 4; n <= 20; ++n) {
        const double r = Cube::radius(n), d = r + 2 + Cube::zoomDistance(n, .7);
        for (double pitch : {-.65, .65}) {
            const double cp = std::cos(pitch), sp = std::sin(pitch);
            for (double rotation : {.19, 1.37, n - .29}) {
                for (int face = 0; face < n; ++face) {
                    const double angle = (face - rotation) * 2 * Cube::pi / n;
                    if (!Cube::frontFacing(angle, r, d, pitch))
                        continue;
                    const double x = r * std::sin(angle), z = r * std::cos(angle);
                    const double depth = d - z * cp;
                    assert(Cube::hitFace(n, rotation, d, 2 * x / depth, -2 * z * sp / depth, pitch) == face);
                    const double localX = .3, localY = -.4;
                    const double wx = localX * std::cos(angle) + r * std::sin(angle);
                    const double wz = -localX * std::sin(angle) + r * std::cos(angle);
                    const double wy = localY * cp - wz * sp;
                    const double perspective = d - (localY * sp + wz * cp);
                    const auto hit = Cube::hitFacePoint(n, rotation, d, 2 * wx / perspective, 2 * wy / perspective, pitch);
                    assert(hit && hit->face == face);
                    assert(std::abs(hit->u - .65) < 1e-9 && std::abs(hit->v - .3) < 1e-9);
                }
                // The far wall is visible through the open end, but its interior isn't selectable.
                assert(!Cube::hitFace(n, rotation, d, 0, 2 * r * sp / (d + r * cp), pitch));
                assert(!Cube::hitFace(n, rotation, d, 0, 10, pitch));
                assert(!Cube::hitFace(n, rotation, d, 0, -10, pitch));
            }
        }
    }
    for (int n = 4; n <= 20; ++n)
        for (double rotation = 0; rotation < 1; rotation += .07)
            for (double pitch : {-.78, -.3, 0., .3, .78}) {
                const double d = Cube::radius(n) + 2 + Cube::zoomDistance(n, .95);
                auto r = Cube::coveredRect(n, rotation, d, pitch);
                if (r[2] <= r[0] || r[3] <= r[1]) continue;
                const auto face = Cube::hitFace(n, rotation, d, (r[0]+r[2])/2, (r[1]+r[3])/2, pitch);
                assert(face);
                for (double u : {.001, .25, .5, .75, .999})
                    for (double v : {.001, .25, .5, .75, .999})
                        assert(Cube::hitFace(n, rotation, d, r[0] + u*(r[2]-r[0]), r[1] + v*(r[3]-r[1]), pitch) == face);
            }
    assert(Cube::frontFacing(0, 1, 4));
    assert(!Cube::frontFacing(Cube::pi, 1, 4));
    assert(!Cube::frontFacing(0, 1, 4, Cube::pi / 2));
}
