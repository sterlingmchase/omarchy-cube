// Test-only compositor bus driver; never installed with the cube plugin.
#include <hyprland/src/plugins/PluginAPI.hpp>
#include <lua.hpp>
#include <stdexcept>

namespace {
HANDLE handle;
int begin(lua_State* L) {
    Event::SCallbackInfo info;
    Event::bus()->m_events.gesture.swipe.begin.emit(
        IPointer::SSwipeBeginEvent{.fingers = static_cast<uint32_t>(luaL_checkinteger(L, 1))}, info);
    lua_pushboolean(L, info.cancelled);
    return 1;
}
int update(lua_State* L) {
    const double x = luaL_checknumber(L, 1), y = luaL_checknumber(L, 2);
    Event::SCallbackInfo info;
    Event::bus()->m_events.gesture.swipe.update.emit(
        IPointer::SSwipeUpdateEvent{.fingers = 4, .delta = {x, y}}, info);
    lua_pushboolean(L, info.cancelled);
    return 1;
}
int end(lua_State* L) {
    Event::SCallbackInfo info;
    Event::bus()->m_events.gesture.swipe.end.emit(
        IPointer::SSwipeEndEvent{.cancelled = bool(lua_toboolean(L, 1))}, info);
    lua_pushboolean(L, info.cancelled);
    return 1;
}
}
APICALL EXPORT std::string PLUGIN_API_VERSION() { return HYPRLAND_API_VERSION; }
APICALL EXPORT PLUGIN_DESCRIPTION_INFO PLUGIN_INIT(HANDLE h) {
    handle = h;
    if (std::string(__hyprland_api_get_hash()) != __hyprland_api_get_client_hash())
        throw std::runtime_error("Gesture driver headers/runtime mismatch");
    if (!HyprlandAPI::addLuaFunction(handle, "cube_test_gesture", "begin", begin) ||
        !HyprlandAPI::addLuaFunction(handle, "cube_test_gesture", "update", update) ||
        !HyprlandAPI::addLuaFunction(handle, "cube_test_gesture", "finish", end))
        throw std::runtime_error("Could not register gesture test driver");
    return {"Cube Gesture Test Driver", "Test-only swipe bus emitter", "Cube tests", "1"};
}
APICALL EXPORT void PLUGIN_EXIT() {
    for (const auto* name : {"begin", "update", "finish"})
        HyprlandAPI::removeLuaFunction(handle, "cube_test_gesture", name);
}
