-- Source from hyprland.lua after your normal Omarchy configuration.
local path = os.getenv("HOME") .. "/.local/lib/hypr/omarchy-cube.so"
hl.permission({ binary = "\\Q" .. path .. "\\E", type = "plugin", mode = "allow" })
hl.plugin.load(path)

-- Check for conflicts in your bindings before enabling these example shortcuts.
hl.bind("SUPER + CTRL + ALT + Left", function() hl.plugin.cube.rotate("left") end)
hl.bind("SUPER + CTRL + ALT + Right", function() hl.plugin.cube.rotate("right") end)
hl.bind("SUPER + CTRL + ALT + Up", function() hl.plugin.cube.rotate("overview") end)
hl.bind("SUPER + CTRL + ALT + mouse:272", function() hl.plugin.cube.rotate("drag") end)

-- Native settings (the optional GUI bridge appended by tools/install-gui overrides these).
for _, plugin in ipairs(hl.get_loaded_plugins()) do
  if plugin.name == "Omarchy Cube" then
    hl.config({ plugin = { cube = {
      enabled = true,
      duration_ms = 280,
      zoom = 0.7,
      workspace_count = 10,
      show_labels = true,
      trackpad_enabled = true,
      carry_windows = false, -- Optional Shift-drag window transfers inside mouse mode.
      workspace_name_1 = "", -- Optional cube display name; likewise workspace_name_2 through _20.
      highlight_selected = true,
      horizontal_sensitivity = 1.0, -- drag multiplier, 0.25–3
      vertical_sensitivity = 1.0,
      invert_horizontal = false,
      invert_vertical = false,
      momentum = false, -- optional quick-release advance, at most one extra face
      skydome_enabled = true,
      skydome_path = "", -- absolute PNG or JPEG panorama path; empty uses the generated sky
      skydome_brightness = 0.65,
      skydome_mode = "auto", -- auto, photo or panorama
    } } })
  end
end
