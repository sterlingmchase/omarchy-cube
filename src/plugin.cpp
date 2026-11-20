#include "cube.hpp"
#include "sky.hpp"
#include "label.hpp"
#include <hyprland/src/config/shared/complex/ComplexDataTypes.hpp>
#include <array>
#include <chrono>
#include <filesystem>
#include <hyprland/src/config/ConfigValue.hpp>
#include <hyprland/src/config/values/types/BoolValue.hpp>
#include <hyprland/src/config/values/types/FloatValue.hpp>
#include <hyprland/src/config/values/types/IntValue.hpp>
#include <hyprland/src/config/values/types/StringValue.hpp>
#include <hyprland/src/desktop/Workspace.hpp>
#include <hyprland/src/desktop/view/Window.hpp>
#include <hyprland/src/desktop/state/WindowState.hpp>
#include <hyprland/src/desktop/state/GlobalWindowController.hpp>
#include <hyprland/src/managers/input/InputManager.hpp>
#include <hyprland/src/desktop/state/FocusState.hpp>
#include <hyprland/src/event/EventBus.hpp>
#include <hyprland/src/managers/SessionLockManager.hpp>
#include <hyprland/src/managers/eventLoop/EventLoopManager.hpp>
#include <hyprland/src/output/Monitor.hpp>
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <hyprland/src/pointer/PointerManager.hpp>
#include <hyprland/src/render/OpenGL.hpp>
#include <hyprland/src/render/Renderer.hpp>
#include <hyprland/src/state/WorkspaceState.hpp>
#include <linux/input-event-codes.h>
#include <lua.hpp>
#include <xkbcommon/xkbcommon-keysyms.h>
#include <stdexcept>
#include <unordered_set>
using namespace Render;
using namespace Render::GL;
namespace {
HANDLE handle;
CFunctionHook *hook = nullptr, *layerHook = nullptr, *keyboardHook = nullptr;
SP<IKeyboard> eventKeyboard;
bool capturing = false;
CShader shader, skyShader;
struct Settings {
    SP<Config::Values::CBoolValue> enabled, skyEnabled, trackpad, carryWindows;
    SP<Config::Values::CBoolValue> labels, highlight, invertHorizontal, invertVertical, momentum;
    SP<Config::Values::CIntValue> duration, count;
    SP<Config::Values::CFloatValue> zoom, brightness, curvature;
    SP<Config::Values::CFloatValue> horizontalSensitivity, verticalSensitivity;
    SP<Config::Values::CStringValue> path;
    SP<Config::Values::CStringValue> skyMode;
    std::array<SP<Config::Values::CStringValue>, 20> names;
} cfg;
SP<ITexture> sky;
std::string loadedSkyPath, skyError;
std::filesystem::file_time_type loadedSkyTime;
GLint radiusUniform, skyAspect, skyParallaxUniform, skyBrightness, skyImage, skySampler, skySourceAspect;
double turnDuration = 280, turnZoom = .7, turnRadius = 1, turnStep = Cube::pi / 2;
size_t lastFaceCount = 0;
GLuint vao = 0, vbo = 0;
GLint faceUniform, distanceUniform, angleUniform, shadeUniform, pitchUniform, interiorUniform, curveUniform;
GLint labelUniform, showLabelUniform, labelSpanUniform, detailOpacityUniform, selectedUniform, accentUniform;
double captureMs = 0, drawUsTotal = 0, drawUsMax = 0;
double intervalTotal = 0, intervalMax = 0;
uint64_t intervals = 0, lateFrames = 0;
std::chrono::steady_clock::time_point previousFrame;
CHyprSignalListener pre, reload, props, mouseMove, mouseButton, mouseAxis, keyboard, swipeBegin, swipeUpdate, swipeEnd;
SP<CEventLoopTimer> expiry;
struct WindowHit { PHLWINDOWREF window; CBox box; };
struct Face {
    SP<IFramebuffer> fb;
    int offset;
    SP<ITexture> label;
    std::vector<WindowHit> windows;
};
std::vector<Face> faces;
struct Carry { PHLWINDOWREF window; PHLWORKSPACEREF source; std::string title; };
std::optional<Carry> carry;
SP<ITexture> carryLabel;
int carryLabelDestination = 0;
PHLMONITORREF monitor;
PHLWORKSPACE destination;
std::chrono::steady_clock::time_point started;
std::chrono::steady_clock::time_point overviewStarted;
double overviewDuration = 220;
int faceCount = 10, baseWorkspace = 1;
bool overview = false, dragging = false, moved = false, selectOnRelease = false, settling = false;
double angleFrom = 0, angleTo = 0, zoomFrom = 0, pressAngle = 0;
double pitchFrom = 0, pitchTo = 0, pressPitch = 0;
Vector2D pressPosition;
std::chrono::steady_clock::time_point lastMotion;
double dragVelocity = 0;
bool swipeOwned = false, swiping = false, swipeSelect = false;
std::unordered_set<uint32_t> swallowedButtons, swallowedKeys;

double phase() {
    return Cube::progress(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count(),
                          turnDuration);
}
double angleNow() {
    return angleFrom + (angleTo - angleFrom) * Cube::ease(phase());
}
double pitchNow() {
    return pitchFrom + (pitchTo - pitchFrom) * Cube::ease(phase());
}
double overviewPhase() {
    if (overviewDuration == 0)
        return 1;
    return Cube::progress(std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - overviewStarted).count(),
                          overviewDuration);
}
double detailNow() {
    return overview ? Cube::ease(overviewPhase()) : settling ? 1 - Cube::ease(phase()) : std::sin(Cube::pi * phase());
}
double curveNow() {
    const double value = cfg.curvature->value();
    return (std::isfinite(value) ? std::clamp(value, -1.0, 1.0) : 0.0) * detailNow();
}
double zoomNow() {
    if (overview)
        return turnZoom * Cube::ease(overviewPhase());
    const double p = Cube::ease(phase());
    if (settling)
        return zoomFrom * (1 - p);
    return zoomFrom * (1 - p) + (turnZoom - zoomFrom) * std::sin(Cube::pi * p);
}
bool moving() {
    return !overview || overviewPhase() < 1 || (angleFrom != angleTo && phase() < 1);
}
int selected() {
    return Cube::next(baseWorkspace, static_cast<int>(std::round(angleNow())), faceCount);
}
bool active = false;
uint64_t draws = 0;
SP<SHyprCtlCommand> status;
using WorkspaceFn = void (*)(IHyprRenderer *, PHLMONITOR, PHLWORKSPACE, const Time::steady_tp &, const CBox &);
using KeyboardFn = void (*)(CInputManager *, const IKeyboard::SKeyEvent &, SP<IKeyboard>);
using LayerFn = void (*)(IHyprRenderer *, PHLLS, PHLMONITOR, const Time::steady_tp &, bool, bool);

void stop() {
    if (!faces.empty() && g_pHyprOpenGL)
        g_pHyprOpenGL->makeEGLCurrent();
    active = false;
    overview = dragging = moved = selectOnRelease = settling = swiping = false;
    pitchFrom = pitchTo = 0;
    if (expiry)
        expiry->updateTimeout(std::nullopt);
    if (auto m = monitor.lock()) {
        g_pHyprRenderer->damageMonitor(m);
        m->recheckSolitary();
    }
    faces.clear();
    carry.reset();
    carryLabel.reset();
    carryLabelDestination = 0;
    destination.reset();
    monitor.reset();
}

SP<IFramebuffer> capture(PHLMONITOR m, PHLWORKSPACE workspace) {
    auto &r = *g_pHyprRenderer;
    auto fb = r.createFB("omarchy-cube face");
    if (!fb->alloc(m->m_pixelSize.x, m->m_pixelSize.y, DRM_FORMAT_ABGR8888))
        throw std::runtime_error("Cube framebuffer allocation failed");
    fb->setImageDescription(m->workBufferImageDescription());
    struct Saved {
        PHLWORKSPACE ws;
        float alpha;
        Vector2D offset;
        bool force;
    };
    std::vector<Saved> saved;
    for (auto ws : State::workspaceState()->workspaces()) {
        if (ws->m_monitor != m)
            continue;
        saved.push_back({ws.lock(), ws->m_alpha->value(), ws->m_renderOffset->value(), ws->m_forceRendering});
        // value() changes only the current sample; goals and callbacks stay untouched.
        ws->m_alpha->value() = ws == workspace ? 1.f : 0.f;
        ws->m_renderOffset->value() = {};
        ws->m_forceRendering = ws == workspace;
    }
    CScopeGuard restore([&] {
        for (auto &s : saved) {
            s.ws->m_alpha->value() = s.alpha;
            s.ws->m_renderOffset->value() = s.offset;
            s.ws->m_forceRendering = s.force;
        }
    });
    CRegion damage(0, 0, m->m_pixelSize.x, m->m_pixelSize.y);
    if (!r.beginFullFakeRender(m, damage, fb))
        throw std::runtime_error("Cube capture failed");
    r.draw(CClearPassElement::SClearData{CHyprColor(0, 0, 0, 1)});
    r.startRenderPass();
    // Dock pixels follow the active workspace, not the workspace being captured.
    const bool wasCapturing = capturing;
    capturing = true;
    CScopeGuard restoreCapturing([wasCapturing] { capturing = wasCapturing; });
    reinterpret_cast<WorkspaceFn>(hook->m_original)(&r, m, workspace, Time::steadyNow(),
                                                    {0, 0, m->m_pixelSize.x, m->m_pixelSize.y});
    r.endRender();
    return fb;
}

void syncFaces() {
    auto m = monitor.lock();
    if (!m)
        return;
    const double rotation = angleNow(), distance = turnRadius + 2 + zoomNow();
    std::array<bool, 20> needed{};
    for (int i = 0; i < faceCount; ++i)
        needed[i] = Cube::frontFacing((i - rotation) * turnStep, turnRadius, distance, pitchNow(), Cube::curveDepth(faceCount, curveNow()));
    std::erase_if(faces, [&](const auto &face) { return !needed[face.offset]; });
    for (int i = 0; i < faceCount; ++i) {
        if (!needed[i] || std::ranges::any_of(faces, [&](const auto &f) { return f.offset == i; }))
            continue;
        g_pHyprOpenGL->makeEGLCurrent();
        const auto begin = std::chrono::steady_clock::now();
        auto ws = State::workspaceState()->query().id(Cube::next(baseWorkspace, i, faceCount)).run();
        if (ws && ws->m_monitor != m)
            ws.reset();
        const int id = Cube::next(baseWorkspace, i, faceCount);
        const auto name = cfg.names[id - 1]->value();
        auto label = cfg.labels->value() ? makeWorkspaceLabel(id, name.empty() && ws ? ws->m_name : name) : nullptr;
        std::vector<WindowHit> windows;
        if (cfg.carryWindows->value() && ws) {
            // Reverse compositor stacking order, with floating surfaces above tiled ones.
            const auto &all = Desktop::windowState()->windows();
            for (bool floating : {true, false})
                for (auto it = all.rbegin(); it != all.rend(); ++it) {
                    const auto &w = *it;
                    if (Desktop::View::validMapped(w) && !w->isHidden() && (w->m_workspace == ws || w->m_pinned) &&
                        w->m_monitor == m && w->m_isFloating == floating && !w->isBlockedByFullscreen())
                        windows.push_back({w, w->getWindowMainSurfaceBox()});
                }
        }
        faces.push_back({capture(m, ws), i, label, std::move(windows)});
        captureMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - begin).count();
    }
    if (carry && carryLabelDestination != selected()) {
        const int id = selected();
        const auto name = cfg.names[id - 1]->value();
        const auto target = State::workspaceState()->query().id(id).run();
        const bool available = !target || target->m_monitor == m;
        carryLabel = makeWorkspaceLabel(id, (name.empty() ? "" : name + " · ") + (available ? "Drop: " : "Unavailable: ") + carry->title);
        carryLabelDestination = id;
    }
    lastFaceCount = std::max(lastFaceCount, faces.size());
}
void changeWorkspace(int id) {
    auto m = monitor.lock();
    if (!m)
        throw std::runtime_error("Cube monitor disappeared");
    auto target = State::workspaceState()->query().id(id).run();
    if (target && target->m_monitor != m)
        throw std::runtime_error("Destination belongs to another monitor");
    if (!target)
        target = State::workspaceState()->create(id, m->m_id);
    const auto source = m->m_activeWorkspace;
    destination = target;
    m->changeWorkspace(target);
    if (source) {
        source->m_renderOffset->setValueAndWarp(source->m_renderOffset->goal());
        source->m_alpha->setValueAndWarp(source->m_alpha->goal());
    }
    target->m_renderOffset->setValueAndWarp({});
    target->m_alpha->setValueAndWarp(1.f);
}
void preview(double target) {
    previousFrame = {};
    angleFrom = angleNow();
    angleTo = target;
    turnDuration = 150;
    started = std::chrono::steady_clock::now();
    static auto animations = CConfigValue<Config::BOOL>("animations:enabled");
    if (!*animations)
        angleFrom = angleTo;
    if (auto m = monitor.lock())
        g_pHyprRenderer->damageMonitor(m);
}
SDispatchResult accept(int id, std::optional<double> target = std::nullopt) {
    const double from = angleNow(), zoom = zoomNow(), pitch = pitchNow();
    try {
        changeWorkspace(id);
    } catch (const std::exception &error) {
        return {.success = false, .error = error.what()};
    }
    static auto animations = CConfigValue<Config::BOOL>("animations:enabled");
    if (!*animations) {
        stop();
        return {};
    }
    overview = dragging = selectOnRelease = false;
    settling = true;
    previousFrame = {}; // Idle overview time is not an animation frame interval.
    angleFrom = from;
    angleTo = target.value_or(from + std::remainder(static_cast<double>(id - baseWorkspace) - from, faceCount));
    zoomFrom = zoom;
    pitchFrom = pitch;
    pitchTo = 0;
    turnDuration = 220;
    started = std::chrono::steady_clock::now();
    expiry->updateTimeout(std::chrono::milliseconds(220));
    if (auto m = monitor.lock())
        g_pHyprRenderer->damageMonitor(m);
    return {};
}

class CubePass : public IPassElement {
  public:
    bool needsLiveBlur() override {
        return false;
    }
    bool needsPrecomputeBlur() override {
        return false;
    }
    bool undiscardable() override {
        return true;
    }
    bool disableSimplification() override {
        return true;
    }
    const char *passName() override {
        return "OmarchyCube";
    }
    ePassElementType type() override {
        return EK_CUSTOM;
    }
    std::vector<UP<IPassElement>> draw() override {
        auto m = monitor.lock();
        if (!active || !m || g_pSessionLockManager->isSessionLocked())
            return {};
        const auto drawStart = std::chrono::steady_clock::now();
        if (previousFrame.time_since_epoch().count() && moving()) {
            const double ms = std::chrono::duration<double, std::milli>(drawStart - previousFrame).count();
            intervalTotal += ms;
            intervalMax = std::max(intervalMax, ms);
            ++intervals;
            if (ms > 1500.0 / std::max(1.f, m->m_refreshRate))
                ++lateFrames;
        }
        previousFrame = drawStart;
        const double rotation = angleNow();
        // Save raw GL state because this pass shares the compositor's context.
        GLint oldProgram, oldVao, oldBuffer, oldActive, oldTexture, oldLabelTexture, oldFrontFace;
        GLint oldScissor[4];
        glGetIntegerv(GL_SCISSOR_BOX, oldScissor);
        GLboolean colorMask[4];
        glGetBooleanv(GL_COLOR_WRITEMASK, colorMask);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glGetIntegerv(GL_CURRENT_PROGRAM, &oldProgram);
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &oldVao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &oldBuffer);
        glGetIntegerv(GL_ACTIVE_TEXTURE, &oldActive);
        glActiveTexture(GL_TEXTURE1);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &oldLabelTexture);
        glActiveTexture(GL_TEXTURE0);
        glGetIntegerv(GL_TEXTURE_BINDING_2D, &oldTexture);
        const bool blend = glIsEnabled(GL_BLEND), scissor = glIsEnabled(GL_SCISSOR_TEST), depthTest = glIsEnabled(GL_DEPTH_TEST),
                   cull = glIsEnabled(GL_CULL_FACE);
        glDisable(GL_BLEND);
        glDisable(GL_SCISSOR_TEST);
        glDisable(GL_DEPTH_TEST);
        glDisable(GL_CULL_FACE);
        glGetIntegerv(GL_FRONT_FACE, &oldFrontFace);
        glFrontFace(GL_CCW);
        GLfloat clear[4];
        glGetFloatv(GL_COLOR_CLEAR_VALUE, clear);
        glClearColor(.025f, .025f, .035f, 1);
        glClear(GL_COLOR_BUFFER_BIT);
        glBindVertexArray(vao);
        if (cfg.skyEnabled->value()) {
            glUseProgram(skyShader.program());
            glUniform1i(skySampler, 0);
            glUniform1i(skyImage, sky ? 1 : 0);
            glUniform1f(skyAspect, m->m_pixelSize.x / m->m_pixelSize.y);
            glUniform1f(skySourceAspect, sky ? sky->m_size.x / sky->m_size.y : 2.f);
            static auto animations = CConfigValue<Config::BOOL>("animations:enabled");
            const auto parallax = Cube::backdropParallax(rotation * turnStep, pitchNow(), *animations);
            glUniform2f(skyParallaxUniform, parallax[0], parallax[1]);
            glUniform1f(skyBrightness,
                        (std::isfinite(cfg.brightness->value()) ? std::clamp(cfg.brightness->value(), .1f, 1.f) : .65f));
            if (sky)
                sky->bind();
            std::array<double, 4> covered{};
            double coveredArea = 0;
            // Flat-face occlusion bounds are not conservative for bent surfaces.
            for (const auto &face : faces) {
                if (curveNow() != 0) break;
                const auto rect = Cube::coveredRect(faceCount, rotation, turnRadius + 2 + zoomNow(), pitchNow(), face.offset);
                const double area = std::max(0., rect[2]-rect[0]) * std::max(0., rect[3]-rect[1]);
                if (area > coveredArea) { coveredArea = area; covered = rect; }
            }
            const int width = m->m_pixelSize.x, height = m->m_pixelSize.y;
            const int left = std::ceil((covered[0] + 1) * width / 2) + 2;
            const int bottom = std::ceil((covered[1] + 1) * height / 2) + 2;
            const int right = std::floor((covered[2] + 1) * width / 2) - 2;
            const int top = std::floor((covered[3] + 1) * height / 2) - 2;
            if (right > left && top > bottom) {
                glEnable(GL_SCISSOR_TEST);
                for (auto rect : {std::array<int,4>{0, 0, left, height}, {right, 0, width-right, height},
                                  {left, 0, right-left, bottom}, {left, top, right-left, height-top}}) {
                    glScissor(rect[0], rect[1], rect[2], rect[3]);
                    glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
                }
                glDisable(GL_SCISSOR_TEST);
            } else
                glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
        }
        glUseProgram(shader.program());
        glUniform1i(faceUniform, 0);
        glUniform1i(labelUniform, 1);
        glUniform2f(labelSpanUniform, .5f, .5f * m->m_pixelSize.x / m->m_pixelSize.y * 80.f / 768.f);
        const double detail = detailNow();
        const double depth = Cube::curveDepth(faceCount, curveNow());
        glUniform1f(curveUniform, depth);
        const auto drawFace = [depth] {
            if (depth == 0) glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
            else glDrawArrays(GL_TRIANGLES, 4, Cube::curveSegments * 6);
        };
        glUniform1f(detailOpacityUniform, detail);
        static auto border = CConfigValue<Config::IComplexConfigValue>("general:col.active_border");
        const auto gradient = border.good() ? dynamic_cast<Config::CGradientValueData *>(border.ptr()) : nullptr;
        const auto accent = gradient && !gradient->m_colors.empty() ? gradient->m_colors.front() : CHyprColor(0.3f, .65f, 1.f, 1.f);
        glUniform3f(accentUniform, accent.r, accent.g, accent.b);
        const double distance = turnRadius + 2 + zoomNow();
        glUniform1f(distanceUniform, distance);
        glUniform1f(radiusUniform, turnRadius);
        const double pitch = pitchNow();
        glUniform1f(pitchUniform, pitch);
        if (std::abs(pitch) > .001 || depth != 0) {
            // Shade the inside without capturing workspaces that face away from the camera.
            std::array<int, 20> order{};
            for (int i = 0; i < faceCount; ++i) order[i] = i;
            std::sort(order.begin(), order.begin() + faceCount, [&](int a, int b) {
                return std::cos((a - rotation) * turnStep) < std::cos((b - rotation) * turnStep);
            });
            glUniform1i(interiorUniform, 1);
            for (int n = 0; n < faceCount; ++n) {
                const double angle = (order[n] - rotation) * turnStep;
                if (depth == 0 && Cube::frontFacing(angle, turnRadius, distance, pitch)) continue;
                glUniform1f(angleUniform, angle);
                glUniform1f(shadeUniform, .65f + .35f * std::abs(std::cos(angle)));
                drawFace();
            }
        }
        glUniform1i(interiorUniform, 0);
        for (const auto &face : faces) {
            const float angle = (face.offset - rotation) * turnStep;
            if (!Cube::frontFacing(angle, turnRadius, distance, pitch, depth))
                continue;
            glUniform1f(angleUniform, angle);
            glUniform1f(shadeUniform, .65f + .35f * std::cos(angle));
            const int chosen = settling ? Cube::next(baseWorkspace, static_cast<int>(std::round(angleTo)), faceCount) : selected();
            const bool isSelected = Cube::next(baseWorkspace, face.offset, faceCount) == chosen;
            const auto label = carry && isSelected ? carryLabel : face.label;
            glUniform1i(selectedUniform, (cfg.highlight->value() || carry.has_value()) && isSelected);
            glUniform1i(showLabelUniform, (cfg.labels->value() || carry.has_value()) && bool(label));
            if (label) {
                glActiveTexture(GL_TEXTURE1);
                label->bind();
                glActiveTexture(GL_TEXTURE0);
            }
            face.fb->getTexture()->bind();
            drawFace();
        }
        glBindTexture(GL_TEXTURE_2D, oldTexture);
        glActiveTexture(GL_TEXTURE1);
        glBindTexture(GL_TEXTURE_2D, oldLabelTexture);
        glActiveTexture(oldActive);
        glBindVertexArray(oldVao);
        glBindBuffer(GL_ARRAY_BUFFER, oldBuffer);
        glUseProgram(oldProgram);
        glFrontFace(oldFrontFace);
        if (blend)
            glEnable(GL_BLEND);
        glScissor(oldScissor[0], oldScissor[1], oldScissor[2], oldScissor[3]);
        if (scissor)
            glEnable(GL_SCISSOR_TEST);
        if (depthTest)
            glEnable(GL_DEPTH_TEST);
        if (cull)
            glEnable(GL_CULL_FACE);
        glClearColor(clear[0], clear[1], clear[2], clear[3]);
        glColorMask(colorMask[0], colorMask[1], colorMask[2], colorMask[3]);
        ++draws;
        const double us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - drawStart).count();
        drawUsTotal += us;
        drawUsMax = std::max(drawUsMax, us);
        if (moving())
            g_pHyprRenderer->damageMonitor(m);
        return {};
    }
};

void renderWorkspace(IHyprRenderer *r, PHLMONITOR m, PHLWORKSPACE ws, const Time::steady_tp &now, const CBox &box) {
    if (active && monitor == m && !g_pSessionLockManager->isSessionLocked()) {
        r->addPassElement(makeUnique<CubePass>());
        return;
    }
    reinterpret_cast<WorkspaceFn>(hook->m_original)(r, m, ws, now, box);
}

void renderLayer(IHyprRenderer *r, PHLLS layer, PHLMONITOR m, const Time::steady_tp &now, bool popups, bool lockscreen) {
    if (capturing && layer && (layer->m_namespace == "omarchy-dock" || layer->m_namespace == "omarchy-dock-apps"))
        return;
    reinterpret_cast<LayerFn>(layerHook->m_original)(r, layer, m, now, popups, lockscreen);
}

SDispatchResult rotate(std::string arg) {
    if (arg == "drag") {
        const bool opening = !overview;
        if (!overview) {
            auto result = rotate("overview");
            if (!result.success)
                return result;
        }
        dragging = true;
        selectOnRelease = opening;
        moved = false;
        pressPosition = Pointer::mgr()->position();
        pressAngle = angleNow();
        pressPitch = pitchNow();
        dragVelocity = 0;
        lastMotion = std::chrono::steady_clock::now();
        angleFrom = angleTo = pressAngle;
        swallowedButtons.insert(BTN_LEFT);
        return {};
    }
    if (arg == "cancel") {
        stop();
        return {};
    }
    if (arg == "accept") {
        if (carry)
            return {.success = false, .error = "Release the grabbed window to move it, or cancel"};
        if (!overview)
            return {.success = false, .error = "Open mouse controls first"};
        return accept(selected());
    }
    if (arg != "left" && arg != "right" && arg != "overview")
        return {.success = false, .error = "Use left, right, overview, drag, accept, or cancel"};
    if (g_pSessionLockManager->isSessionLocked()) {
        stop();
        return {.success = false, .error = "Session is locked"};
    }
    if (active && !overview && phase() >= 1)
        stop();
    const int direction = arg == "left" ? -1 : 1;
    if (overview) {
        if (arg == "overview") {
            stop();
            return {};
        }
        preview(std::round(angleTo) + direction);
        return {};
    }
    try {
        if (active && arg != "overview") {
            const double from = angleNow(), zoom = zoomNow(), to = angleTo + direction;
            const double pitch = pitchNow();
            changeWorkspace(Cube::next(baseWorkspace, static_cast<int>(std::round(to)), faceCount));
            settling = false;
            angleFrom = from;
            angleTo = to;
            zoomFrom = zoom;
            pitchFrom = pitch;
            pitchTo = 0;
            started = std::chrono::steady_clock::now();
            expiry->updateTimeout(std::chrono::milliseconds(static_cast<int>(turnDuration)));
            g_pHyprRenderer->damageMonitor(monitor.lock());
            return {};
        }
        if (active)
            stop();
        auto m = Desktop::focusState()->monitor();
        if (!m || !m->m_activeWorkspace)
            throw std::runtime_error("No workspace available");
        faceCount = std::clamp<int>(cfg.count->value(), 4, 20);
        if (m->m_transform != WL_OUTPUT_TRANSFORM_NORMAL || m->m_activeSpecialWorkspace || m->m_activeWorkspace->m_id < 1 ||
            m->m_activeWorkspace->m_id > faceCount)
            throw std::runtime_error(
                "Close the console/special workspace and use a configured numbered workspace on an unrotated monitor");
        static auto animations = CConfigValue<Config::BOOL>("animations:enabled");
        if (arg != "overview" && (!*animations || !cfg.enabled->value())) {
            const int id = Cube::next(m->m_activeWorkspace->m_id, direction, faceCount);
            auto target = State::workspaceState()->query().id(id).run();
            if (target && target->m_monitor != m)
                throw std::runtime_error("Destination belongs to another monitor");
            m->changeWorkspace(id);
            return {};
        }
        if (!cfg.enabled->value())
            throw std::runtime_error("Enable the cube before opening mouse controls");
        monitor = m;
        destination = m->m_activeWorkspace;
        baseWorkspace = destination->m_id;
        overview = arg == "overview";
        overviewStarted = std::chrono::steady_clock::now();
        overviewDuration = *animations ? 220 : 0;
        turnDuration = std::clamp<double>(cfg.duration->value(), 120, 600);
        turnZoom =
            Cube::zoomDistance(faceCount, std::isfinite(cfg.zoom->value()) ? std::clamp<double>(cfg.zoom->value(), 0, 1.5) : .7);
        // A usable selection view still needs space around the faces when transition zoom is zero.
        if (overview)
            turnZoom = std::max(turnZoom, Cube::zoomDistance(faceCount, .5));
        turnRadius = Cube::radius(faceCount);
        turnStep = 2 * Cube::pi / faceCount;
        angleFrom = 0;
        angleTo = overview ? 0 : direction;
        zoomFrom = 0;
        started = std::chrono::steady_clock::now();
        previousFrame = {};
        captureMs = 0;
        lastFaceCount = 0;
        faces.reserve(20);
        syncFaces();
        if (!overview)
            changeWorkspace(Cube::next(baseWorkspace, direction, faceCount));
        started = std::chrono::steady_clock::now();
        active = true;
        overviewStarted = started;
        if (!overview)
            expiry->updateTimeout(std::chrono::milliseconds(static_cast<int>(turnDuration)));
        m->m_solitaryClient.reset();
        g_pHyprRenderer->damageMonitor(m);
        return {};
    } catch (const std::exception &e) {
        stop();
        return {.success = false, .error = e.what()};
    }
}
void beginCarry() {
    auto m = monitor.lock();
    if (!m || !cfg.carryWindows->value())
        return;
    const auto pos = Pointer::mgr()->position() - m->m_position;
    const auto hit = Cube::hitFacePoint(faceCount, angleNow(), turnRadius + 2 + zoomNow(),
        2 * pos.x / m->m_size.x - 1, 2 * pos.y / m->m_size.y - 1, pitchNow(), curveNow());
    if (!hit)
        return;
    const Vector2D point = m->m_position + Vector2D{hit->u * m->m_size.x, hit->v * m->m_size.y};
    const auto face = std::ranges::find_if(faces, [&](const Face &f) { return f.offset == hit->face; });
    if (face == faces.end())
        return;
    for (const auto &entry : face->windows) {
        if (!entry.box.containsPoint(point))
            continue;
        auto w = entry.window.lock();
        if (!Desktop::View::validMapped(w) || w->isHidden() || w->m_monitor != m || !w->m_workspace ||
            w->m_workspace->m_id != Cube::next(baseWorkspace, hit->face, faceCount))
            return;
        if (w->m_pinned || w->m_group) {
            HyprlandAPI::addNotification(handle, "Cube: pinned or grouped windows cannot be moved", CHyprColor(1.f, .6f, .2f, 1.f), 2500);
            return;
        }
        carry = Carry{w, w->m_workspace, w->m_title.empty() ? "Window" : w->m_title.substr(0, 512)};
        carryLabelDestination = 0;
        g_pHyprRenderer->damageMonitor(m);
        return;
    }
}
void dropCarry(double target) {
    auto m = monitor.lock();
    auto w = carry ? carry->window.lock() : nullptr;
    if (!cfg.carryWindows->value() || !m || !Desktop::View::validMapped(w) || w->isHidden() || w->m_pinned || w->m_group ||
        w->m_monitor != m || !carry->source || w->m_workspace != carry->source.lock() || g_pSessionLockManager->isSessionLocked()) {
        stop();
        return;
    }
    const int id = Cube::next(baseWorkspace, static_cast<int>(target), faceCount);
    auto dest = State::workspaceState()->query().id(id).run();
    if (dest && dest->m_monitor != m) {
        HyprlandAPI::addNotification(handle, "Cube: destination belongs to another monitor", CHyprColor(1.f, .6f, .2f, 1.f), 2500);
        stop();
        return;
    }
    try {
        if (!dest)
            dest = State::workspaceState()->create(id, m->m_id);
        if (w->m_workspace != dest)
            Desktop::globalWindowController()->moveWindowToWorkspace(w, dest);
        carry.reset();
        carryLabel.reset();
        faces.clear();
        if (accept(id, target).success)
            Desktop::focusState()->fullWindowFocus(w, Desktop::FOCUS_REASON_OTHER);
    } catch (const std::exception &) {
        stop();
    }
}
void keyboardEvent(CInputManager *manager, const IKeyboard::SKeyEvent &event, SP<IKeyboard> device) {
    // The public key event omits its originating keyboard; retain its actual keymap during dispatch.
    auto previous = eventKeyboard;
    eventKeyboard = device;
    CScopeGuard restore([previous] { eventKeyboard = previous; });
    reinterpret_cast<KeyboardFn>(keyboardHook->m_original)(manager, event, device);
}
void installInput() {
    swipeBegin = Event::bus()->m_events.gesture.swipe.begin.listen([](IPointer::SSwipeBeginEvent e, Event::SCallbackInfo &info) {
        swipeOwned = swiping = false;
        if (info.cancelled || e.fingers != 4 || !cfg.trackpad->value() || dragging || g_pSessionLockManager->isSessionLocked())
            return;
        const bool opening = !overview;
        if (opening && !rotate("overview").success)
            return;
        swipeOwned = swiping = true;
        swipeSelect = opening;
        pressAngle = angleNow();
        pressPitch = pitchNow();
        angleFrom = angleTo = pressAngle;
        dragVelocity = 0;
        lastMotion = std::chrono::steady_clock::now();
        previousFrame = {};
        info.cancelled = true;
    });
    swipeUpdate = Event::bus()->m_events.gesture.swipe.update.listen([](IPointer::SSwipeUpdateEvent e, Event::SCallbackInfo &info) {
        if (!swipeOwned)
            return;
        info.cancelled = true;
        if (!swiping || !overview || g_pSessionLockManager->isSessionLocked())
            return;
        if (!std::isfinite(e.delta.x) || !std::isfinite(e.delta.y))
            return;
        const double h = cfg.horizontalSensitivity->value(), v = cfg.verticalSensitivity->value();
        const double next = angleNow() - e.delta.x * (std::isfinite(h) ? std::clamp(h, .25, 3.) : 1.) * (cfg.invertHorizontal->value() ? -1 : 1) / 300.;
        const auto now = std::chrono::steady_clock::now();
        const double dt = std::chrono::duration<double>(now - lastMotion).count();
        if (dt > .001) {
            dragVelocity = dt > .15 ? 0 : .65 * dragVelocity + .35 * std::clamp((next - angleNow()) / dt, -10., 10.);
            lastMotion = now;
        }
        previousFrame = {};
        angleFrom = angleTo = next;
        pitchFrom = pitchTo = std::clamp(pitchNow() - e.delta.y * (std::isfinite(v) ? std::clamp(v, .25, 3.) : 1.) * (cfg.invertVertical->value() ? -1 : 1) / 500., -Cube::pi / 4, Cube::pi / 4);
        if (auto m = monitor.lock())
            g_pHyprRenderer->damageMonitor(m);
    });
    swipeEnd = Event::bus()->m_events.gesture.swipe.end.listen([](IPointer::SSwipeEndEvent e, Event::SCallbackInfo &info) {
        if (!swipeOwned)
            return;
        swipeOwned = false;
        info.cancelled = true;
        if (!swiping || !overview)
            return;
        swiping = false;
        if (e.cancelled || g_pSessionLockManager->isSessionLocked()) {
            stop();
            return;
        }
        const double target = Cube::releaseTarget(angleNow(), dragVelocity,
            std::chrono::duration<double>(std::chrono::steady_clock::now() - lastMotion).count(), cfg.momentum->value());
        if (swipeSelect)
            accept(Cube::next(baseWorkspace, static_cast<int>(target), faceCount), target);
        else
            preview(target);
    });
    mouseMove = Event::bus()->m_events.input.mouse.move.listen([](Vector2D, Event::SCallbackInfo &info) {
        if (!overview || g_pSessionLockManager->isSessionLocked())
            return;
        info.cancelled = true;
        auto m = monitor.lock();
        if (!m || !dragging)
            return;
        const auto delta = Pointer::mgr()->position() - pressPosition;
        if (std::abs(delta.x) > 6 || std::abs(delta.y) > 6)
            moved = true;
        if (!moved)
            return;
        const double horizontal = std::clamp<double>(cfg.horizontalSensitivity->value(), .25, 3);
        const double vertical = std::clamp<double>(cfg.verticalSensitivity->value(), .25, 3);
        const double next = pressAngle - delta.x * horizontal * (cfg.invertHorizontal->value() ? -1 : 1) / std::max(1.0, m->m_size.x * .35);
        const auto now = std::chrono::steady_clock::now();
        const double dt = std::chrono::duration<double>(now - lastMotion).count();
        if (dt > .001) {
            dragVelocity = dt > .15 ? 0 : .65 * dragVelocity + .35 * std::clamp((next - angleNow()) / dt, -10.0, 10.0);
            lastMotion = now;
        }
        angleFrom = angleTo = next;
        pitchFrom = pitchTo = std::clamp(pressPitch - delta.y * vertical * (cfg.invertVertical->value() ? -1 : 1) / std::max(1.0, m->m_size.y * .5), -Cube::pi / 4, Cube::pi / 4);
        g_pHyprRenderer->damageMonitor(m);
    });
    mouseButton = Event::bus()->m_events.input.mouse.button.listen([](IPointer::SButtonEvent e, Event::SCallbackInfo &info) {
        if (g_pSessionLockManager->isSessionLocked()) {
            swallowedButtons.clear();
            return;
        }
        const bool pressed = e.state == WL_POINTER_BUTTON_STATE_PRESSED;
        const bool consumed = !pressed && swallowedButtons.erase(e.button);
        if (!overview) {
            if (consumed)
                info.cancelled = true;
            return;
        }
        info.cancelled = true;
        if (pressed)
            swallowedButtons.insert(e.button);
        if (e.button == BTN_RIGHT && !pressed) {
            stop();
            return;
        }
        if (e.button != BTN_LEFT)
            return;
        if (pressed) {
            dragging = true;
            selectOnRelease = false;
            moved = false;
            pressPosition = Pointer::mgr()->position();
            pressAngle = angleNow();
            pressPitch = pitchNow();
            dragVelocity = 0;
            lastMotion = std::chrono::steady_clock::now();
            angleFrom = angleTo = pressAngle;
            if (cfg.carryWindows->value() && (g_pInputManager->getModsFromAllKBs() & HL_MODIFIER_SHIFT))
                beginCarry();
        } else if (dragging) {
            dragging = false;
            const double target = Cube::releaseTarget(angleNow(), dragVelocity,
                std::chrono::duration<double>(std::chrono::steady_clock::now() - lastMotion).count(), cfg.momentum->value());
            if (carry) {
                dropCarry(target);
                return;
            }
            if (selectOnRelease) {
                selectOnRelease = false;
                accept(Cube::next(baseWorkspace, static_cast<int>(target), faceCount), target);
                return;
            }
            if (moved) {
                preview(target);
                return;
            }
            auto m = monitor.lock();
            if (!m) {
                stop();
                return;
            }
            const auto pos = Pointer::mgr()->position() - m->m_position;
            const auto face = Cube::hitFace(faceCount, angleNow(), turnRadius + 2 + zoomNow(), 2 * pos.x / m->m_size.x - 1,
                                            2 * pos.y / m->m_size.y - 1, pitchNow(), curveNow());
            if (face)
                accept(Cube::next(baseWorkspace, *face, faceCount));
        }
    });
    mouseAxis = Event::bus()->m_events.input.mouse.axis.listen([](IPointer::SAxisEvent e, Event::SCallbackInfo &info) {
        if (!overview || g_pSessionLockManager->isSessionLocked())
            return;
        info.cancelled = true;
        if (e.deltaDiscrete)
            preview(std::round(angleTo) + (e.deltaDiscrete > 0 ? 1 : -1));
        else if (std::isfinite(e.delta) && e.delta)
            preview(angleTo + std::clamp(e.delta / 30.0, -1.0, 1.0));
    });
    keyboard = Event::bus()->m_events.input.keyboard.key.listen([](IKeyboard::SKeyEvent e, Event::SCallbackInfo &info) {
        if (g_pSessionLockManager->isSessionLocked()) {
            swallowedKeys.clear();
            return;
        }
        const bool pressed = e.state == WL_KEYBOARD_KEY_STATE_PRESSED;
        const bool consumed = !pressed && swallowedKeys.erase(e.keycode);
        if (!overview) {
            if (consumed)
                info.cancelled = true;
            return;
        }
        if (!pressed && !consumed)
            return; // Deliver releases for keys held before opening the overview.
        info.cancelled = true;
        const auto symbol = eventKeyboard && eventKeyboard->m_xkbState ?
            xkb_state_key_get_one_sym(eventKeyboard->m_xkbState, e.keycode + 8) : XKB_KEY_NoSymbol;
        if (pressed) {
            swallowedKeys.insert(e.keycode);
            if (symbol == XKB_KEY_Left)
                preview(std::round(angleTo) - 1);
            if (symbol == XKB_KEY_Right)
                preview(std::round(angleTo) + 1);
        } else {
            if (symbol == XKB_KEY_Escape)
                stop();
            else if (!carry && (symbol == XKB_KEY_Return || symbol == XKB_KEY_KP_Enter))
                accept(selected());
        }
    });
}
int luaReadSettings(lua_State *L) {
    const char *config = std::getenv("XDG_CONFIG_HOME");
    const char *home = std::getenv("HOME");
    if (!config && !home)
        return luaL_error(L, "Cannot locate cube-gui.lua");
    try {
        const auto directory = config ? std::string(config) : std::string(home) + "/.config";
        const auto bytes = readBoundedFile(directory + "/hypr/cube-gui.lua", 1, 32768, true);
        if (bytes.empty())
            lua_pushnil(L);
        else
            lua_pushlstring(L, reinterpret_cast<const char *>(bytes.data()), bytes.size());
        return 1;
    } catch (const std::exception &) {
        return luaL_error(L, "Cannot safely read cube-gui.lua");
    }
}
int luaRotate(lua_State *L) {
    const char *arg = luaL_checkstring(L, 1);
    const auto result = rotate(arg);
    lua_pushboolean(L, result.success);
    lua_pushlstring(L, result.error.data(), result.error.size());
    return 2;
}
void cleanup() {
    pre.reset();
    reload.reset();
    props.reset();
    mouseMove.reset();
    mouseButton.reset();
    mouseAxis.reset();
    keyboard.reset();
    swipeBegin.reset();
    swipeUpdate.reset();
    swipeEnd.reset();
    swipeOwned = false;
    swallowedButtons.clear();
    swallowedKeys.clear();
    stop();
    if (expiry)
        g_pEventLoopManager->removeTimer(expiry);
    expiry.reset();
    // Queued pass objects must die while their plugin vtable is still loaded.
    g_pHyprRenderer->m_renderPass.removeAllOfType("OmarchyCube");
    if (hook) {
        HyprlandAPI::removeFunctionHook(handle, hook);
        hook = nullptr;
    }
    if (layerHook) {
        HyprlandAPI::removeFunctionHook(handle, layerHook);
        layerHook = nullptr;
    }
    if (keyboardHook) {
        HyprlandAPI::removeFunctionHook(handle, keyboardHook);
        keyboardHook = nullptr;
    }
    eventKeyboard.reset();
    HyprlandAPI::removeLuaFunction(handle, "cube", "rotate");
    HyprlandAPI::removeLuaFunction(handle, "cube", "read_settings");
    if (status)
        HyprlandAPI::unregisterHyprCtlCommand(handle, status);
    status.reset();
    if (g_pHyprOpenGL)
        g_pHyprOpenGL->makeEGLCurrent();
    if (vao)
        glDeleteVertexArrays(1, &vao);
    if (vbo)
        glDeleteBuffers(1, &vbo);
    vao = vbo = 0;
    shader.destroy();
    skyShader.destroy();
    sky.reset();
}
template <typename T, typename... Args> SP<T> option(Args &&...args) {
    auto value = makeShared<T>(std::forward<Args>(args)...);
    if (!HyprlandAPI::addConfigValueV2(handle, value))
        throw std::runtime_error("Cube option registration failed");
    return value;
}
void configure() {
    using namespace Config::Values;
    cfg.enabled = option<CBoolValue>("plugin:cube:enabled", "Enable cube animation", true);
    cfg.carryWindows = option<CBoolValue>("plugin:cube:carry_windows", "Shift-drag windows between cube faces", false);
    cfg.trackpad = option<CBoolValue>("plugin:cube:trackpad_enabled", "Four-finger cube swipe", true);
    static const auto nameKeys = [] {
        std::array<std::string, 20> keys;
        for (size_t i = 0; i < keys.size(); ++i)
            keys[i] = "plugin:cube:workspace_name_" + std::to_string(i + 1);
        return keys;
    }();
    for (size_t i = 0; i < cfg.names.size(); ++i)
        cfg.names[i] = option<CStringValue>(nameKeys[i].c_str(), "Cube workspace display name", "");
    cfg.skyEnabled = option<CBoolValue>("plugin:cube:skydome_enabled", "Show skydome", true);
    cfg.labels = option<CBoolValue>("plugin:cube:show_labels", "Show workspace numbers and names", true);
    cfg.highlight = option<CBoolValue>("plugin:cube:highlight_selected", "Theme-colored selected workspace edge glow", true);
    cfg.invertHorizontal = option<CBoolValue>("plugin:cube:invert_horizontal", "Invert horizontal drag", false);
    cfg.invertVertical = option<CBoolValue>("plugin:cube:invert_vertical", "Invert vertical drag", false);
    cfg.momentum = option<CBoolValue>("plugin:cube:momentum", "Allow flicks to carry up to one extra face", false);
    cfg.horizontalSensitivity = option<CFloatValue>("plugin:cube:horizontal_sensitivity", "Horizontal drag sensitivity", 1.f,
                                                   SFloatValueOptions{.min = .25, .max = 3});
    cfg.verticalSensitivity = option<CFloatValue>("plugin:cube:vertical_sensitivity", "Vertical drag sensitivity", 1.f,
                                                 SFloatValueOptions{.min = .25, .max = 3});
    cfg.skyMode = option<CStringValue>("plugin:cube:skydome_mode", "Legacy mapping setting (all values now use a parallax backdrop)", "photo");
    cfg.duration = option<CIntValue>("plugin:cube:duration_ms", "Turn duration", 280, SIntValueOptions{.min = 120, .max = 600});
    cfg.count =
        option<CIntValue>("plugin:cube:workspace_count", "Numbered workspace faces", 10, SIntValueOptions{.min = 4, .max = 20});
    cfg.curvature = option<CFloatValue>("plugin:cube:face_curvature", "Face bow: -1 concave, 0 flat, +1 convex (experimental)", 0.f,
                                        SFloatValueOptions{.min = -1, .max = 1});
    cfg.zoom = option<CFloatValue>("plugin:cube:zoom", "Zoom out distance", .7f, SFloatValueOptions{.min = 0, .max = 1.5});
    cfg.brightness = option<CFloatValue>("plugin:cube:skydome_brightness", "Skydome brightness", .65f,
                                         SFloatValueOptions{.min = .1, .max = 1});
    cfg.path = option<CStringValue>("plugin:cube:skydome_path", "Absolute PNG or JPEG panorama path, empty for gradient", "");
}
void refreshSky() {
    if (!cfg.enabled->value() || (carry && !cfg.carryWindows->value()) || (active && cfg.count->value() != faceCount))
        stop();
    const std::string path = cfg.skyEnabled->value() ? cfg.path->value() : "";
    std::error_code error;
    const auto modified = path.empty() ? std::filesystem::file_time_type{} : std::filesystem::last_write_time(path, error);
    if (path == loadedSkyPath && modified == loadedSkyTime && skyError.empty())
        return;
    stop();
    loadedSkyTime = modified;
    g_pHyprOpenGL->makeEGLCurrent();
    sky.reset();
    loadedSkyPath = path;
    skyError.clear();
    if (path.empty())
        return;
    try {
        if (path.size() > 4096 || path.front() != '/' || path.find('\0') != std::string::npos)
            throw std::runtime_error("Skydome requires an absolute PNG or JPEG path");
        sky = loadSky(path);
        if (!sky || !sky->ok())
            throw std::runtime_error("Skydome texture allocation failed");
    } catch (const std::exception &e) {
        sky.reset();
        skyError = e.what();
    }
}
} // namespace
APICALL EXPORT std::string PLUGIN_API_VERSION() {
    return HYPRLAND_API_VERSION;
}
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle = h;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash() ||
        std::string_view(GIT_COMMIT_HASH) != "efb50993780079460b0cbed1363e2166a2de1d9f")
        throw std::runtime_error("Omarchy Cube requires matching Hyprland 0.56.2 headers and runtime");
    try {
        configure();
        if (!g_pHyprOpenGL)
            throw std::runtime_error("OpenGL renderer required");
        g_pHyprOpenGL->makeEGLCurrent();
        if (!shader.createProgram(R"(#version 300 es
precision highp float;
layout(location=0) in vec2 pos;
out vec2 uv;
uniform float angle;
uniform float distance;
uniform float radius;
uniform float pitch;
uniform float curve_depth;
void main() {
    float wall = radius + curve_depth*(1.0-pos.x*pos.x);
    float x = pos.x*cos(angle) + wall*sin(angle);
    float z = -pos.x*sin(angle) + wall*cos(angle);
    float y = pos.y*cos(pitch)-z*sin(pitch);
    z = pos.y*sin(pitch)+z*cos(pitch);
    gl_Position = vec4(2.0*x, 2.0*y, 0.0, distance-z);
    uv = (pos+1.0)*0.5;
}
)",
                                  R"(#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D face;
uniform float shade;
uniform bool interior;
uniform sampler2D workspace_label;
uniform bool show_label;
uniform vec2 label_span;
uniform float detail_opacity;
uniform bool selected_face;
uniform vec3 accent;
uniform float curve_depth;
out vec4 color;
void main() {
    // The inverse side of each bent strip belongs to the interior pass.
    // Hit testing intersects these same piecewise-linear strips.
    if (curve_depth != 0.0 && gl_FrontFacing == interior) discard;
    if (interior) {
        float rim = step(0.982,abs(uv.y*2.0-1.0));
        color = vec4(mix(vec3(0.055,0.07,0.10)*shade,vec3(0.22,0.29,0.40),rim),1.0);
    } else {
        vec3 rgb=texture(face,uv).rgb*shade;
        vec2 labelUV=(uv-vec2((1.0-label_span.x)*0.5,0.025))/label_span;
        if (show_label && all(greaterThanEqual(labelUV,vec2(0))) && all(lessThanEqual(labelUV,vec2(1)))) {
            vec4 label=texture(workspace_label,labelUV)*detail_opacity;
            rgb=label.rgb+rgb*(1.0-label.a);
        }
        if (selected_face) {
            vec2 edge=min(uv,1.0-uv)/max(fwidth(uv),vec2(0.00001));
            float pixels=min(edge.x,edge.y);
            float line=1.0-smoothstep(1.0,2.5,pixels);
            // Soft inward halo in the existing face pass: no blur, extra texture,
            // geometry, or idle animation. Keep the workspace center untouched.
            float glow=(1.0-smoothstep(2.5,18.0,pixels));
            glow=glow*glow*.38;
            rgb=mix(rgb,accent,max(line,glow)*detail_opacity);
        }
        color=vec4(rgb,1.0);
    }
}
)"))
            throw std::runtime_error("Cube shader compilation failed");
        if (!skyShader.createProgram(R"(#version 300 es
precision highp float;
layout(location=0) in vec2 pos;
out vec2 uv;
void main() { uv=(pos+1.0)*0.5; gl_Position=vec4(pos,0.0,1.0); }
)",
                                     R"(#version 300 es
precision highp float;
in vec2 uv;
uniform sampler2D panorama;
uniform bool has_image;
uniform float aspect;
uniform float source_aspect;
uniform vec2 parallax;
uniform float brightness;
out vec4 color;
void main() {
    vec3 skyColor;
    if (has_image) {
        // Aspect-correct cover with 10% overscan. Offsets consume only 65% of
        // the available margin, including at maximum tilt or extreme aspect ratios.
        vec2 span=vec2(min(1.0,aspect/source_aspect),min(1.0,source_aspect/aspect))/1.10;
        vec2 sampleUV=vec2(0.5)+(uv-0.5)*span+parallax*(1.0-span)*0.5;
        skyColor=texture(panorama,sampleUV).rgb;
    }
    else {
        vec3 ray=normalize(vec3((uv.x*2.0-1.0)*aspect, uv.y*2.0-1.0, 1.5));
        skyColor=mix(vec3(0.035,0.055,0.12),vec3(0.25,0.36,0.5),pow(1.0-abs(ray.y),3.0));
    }
    color=vec4(skyColor*brightness,1.0);
}
)"))
            throw std::runtime_error("Skydome shader compilation failed");
        skyAspect = glGetUniformLocation(skyShader.program(), "aspect");
        skySourceAspect = glGetUniformLocation(skyShader.program(), "source_aspect");
        skyParallaxUniform = glGetUniformLocation(skyShader.program(), "parallax");
        skyBrightness = glGetUniformLocation(skyShader.program(), "brightness");
        skyImage = glGetUniformLocation(skyShader.program(), "has_image");
        skySampler = glGetUniformLocation(skyShader.program(), "panorama");
        reload = Event::bus()->m_events.config.reloaded.listen([] { stop(); refreshSky(); });
        props = Event::bus()->m_events.config.props_refreshed.listen([](bool) { refreshSky(); });
        refreshSky();
        radiusUniform = glGetUniformLocation(shader.program(), "radius");
        faceUniform = glGetUniformLocation(shader.program(), "face");
        distanceUniform = glGetUniformLocation(shader.program(), "distance");
        angleUniform = glGetUniformLocation(shader.program(), "angle");
        shadeUniform = glGetUniformLocation(shader.program(), "shade");
        pitchUniform = glGetUniformLocation(shader.program(), "pitch");
        interiorUniform = glGetUniformLocation(shader.program(), "interior");
        labelUniform = glGetUniformLocation(shader.program(), "workspace_label");
        showLabelUniform = glGetUniformLocation(shader.program(), "show_label");
        labelSpanUniform = glGetUniformLocation(shader.program(), "label_span");
        detailOpacityUniform = glGetUniformLocation(shader.program(), "detail_opacity");
        selectedUniform = glGetUniformLocation(shader.program(), "selected_face");
        accentUniform = glGetUniformLocation(shader.program(), "accent");
        curveUniform = glGetUniformLocation(shader.program(), "curve_depth");
        std::vector<float> vertices{-1, -1, 1, -1, -1, 1, 1, 1};
        for (int strip = 0; strip < Cube::curveSegments; ++strip) {
            const float left = -1.f + 2.f * strip / Cube::curveSegments;
            const float right = -1.f + 2.f * (strip + 1) / Cube::curveSegments;
            for (float value : {left,-1.f,right,-1.f,left,1.f, left,1.f,right,-1.f,right,1.f}) vertices.push_back(value);
        }
        GLint oldVao, oldBuffer;
        glGetIntegerv(GL_VERTEX_ARRAY_BINDING, &oldVao);
        glGetIntegerv(GL_ARRAY_BUFFER_BINDING, &oldBuffer);
        glGenVertexArrays(1, &vao);
        glGenBuffers(1, &vbo);
        glBindVertexArray(vao);
        glBindBuffer(GL_ARRAY_BUFFER, vbo);
        glBufferData(GL_ARRAY_BUFFER, vertices.size() * sizeof(float), vertices.data(), GL_STATIC_DRAW);
        glEnableVertexAttribArray(0);
        glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, nullptr);
        glBindVertexArray(oldVao);
        glBindBuffer(GL_ARRAY_BUFFER, oldBuffer);
        for (const auto &f : HyprlandAPI::findFunctionsByName(handle, "renderWorkspace")) {
            if (!f.demangled.starts_with("Render::IHyprRenderer::renderWorkspace("))
                continue;
            if (hook)
                throw std::runtime_error("Ambiguous workspace renderer");
            hook = HyprlandAPI::createFunctionHook(handle, f.address, reinterpret_cast<void *>(&renderWorkspace));
        }
        if (!hook || !hook->hook())
            throw std::runtime_error("Workspace render hook unavailable");
        for (const auto &f : HyprlandAPI::findFunctionsByName(handle, "renderLayer")) {
            if (!f.demangled.starts_with("Render::IHyprRenderer::renderLayer("))
                continue;
            if (layerHook)
                throw std::runtime_error("Ambiguous layer renderer");
            layerHook = HyprlandAPI::createFunctionHook(handle, f.address, reinterpret_cast<void *>(&renderLayer));
        }
        if (!layerHook || !layerHook->hook())
            throw std::runtime_error("Layer render hook unavailable");
        for (const auto &f : HyprlandAPI::findFunctionsByName(handle, "onKeyboardKey")) {
            if (!f.demangled.starts_with("CInputManager::onKeyboardKey(")) continue;
            if (keyboardHook) throw std::runtime_error("Ambiguous keyboard handler");
            keyboardHook = HyprlandAPI::createFunctionHook(handle, f.address, reinterpret_cast<void *>(&keyboardEvent));
        }
        if (!keyboardHook || !keyboardHook->hook())
            throw std::runtime_error("Keyboard origin hook unavailable");
        if (!HyprlandAPI::addLuaFunction(handle, "cube", "rotate", luaRotate))
            throw std::runtime_error("Cube dispatcher unavailable");
        if (!HyprlandAPI::addLuaFunction(handle, "cube", "read_settings", luaReadSettings))
            throw std::runtime_error("Cube settings reader unavailable");
        // One deadline releases snapshots even when a hidden output stops receiving frames.
        expiry = makeShared<CEventLoopTimer>(std::nullopt, [](SP<CEventLoopTimer>, void *) { stop(); }, nullptr);
        g_pEventLoopManager->addTimer(expiry);
        installInput();
        pre = Event::bus()->m_events.render.preChecks.listen([](PHLMONITOR m) {
            if (active && !monitor) {
                stop();
                return;
            }
            if (!active || monitor != m)
                return;
            if (g_pSessionLockManager->isSessionLocked() || m->m_activeWorkspace != destination || m->m_activeSpecialWorkspace ||
                (!faces.empty() && faces[0].fb->m_size != m->m_pixelSize) || m->m_transform != WL_OUTPUT_TRANSFORM_NORMAL ||
                (!overview && phase() >= 1)) {
                stop();
                return;
            }
            try {
                syncFaces();
            } catch (const std::exception &) {
                stop();
                return;
            }
            m->m_solitaryClient.reset();
            if (moving())
                g_pHyprRenderer->damageMonitor(m);
        });
        status = HyprlandAPI::registerHyprCtlCommand(
            handle, {"omarchy-cube:status", true, [](eHyprCtlOutputFormat, std::string) {
                         return std::format("active={} draws={} capture_ms={:.3f} draw_cpu_us_avg={:.3f} draw_cpu_us_max={:.3f} "
                                            "interval_ms_avg={:.3f} interval_ms_max={:.3f} late_frames={} intervals={} faces={} "
                                            "carrying={} overview={} selected={} angle={:.4f} target={:.4f} pitch={:.4f} zoom={:.4f} sky_width={} sky_height={} sky_loaded={} sky_error={}\n",
                                            active, draws, captureMs, draws ? drawUsTotal / draws : 0, drawUsMax,
                                            intervals ? intervalTotal / intervals : 0, intervalMax, lateFrames, intervals,
                                            lastFaceCount, carry.has_value(), overview, selected(), angleNow(), angleTo, pitchNow(), zoomNow(),
                                            sky ? static_cast<int>(sky->m_size.x) : 0, sky ? static_cast<int>(sky->m_size.y) : 0, bool(sky),
                                            skyError.empty() ? "none" : skyError);
                     }});
        return {"Omarchy Cube", "Workspace cube/prism with parallax backgrounds and optional curved faces", "Omarchy Cube contributors", "0.3.0"};
    } catch (...) {
        cleanup();
        throw;
    }
}
APICALL EXPORT void PLUGIN_EXIT() {
    cleanup();
}
