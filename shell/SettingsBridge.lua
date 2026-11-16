
-- Omarchy Cube GUI bridge v1
-- Load GUI overrides only after the native plugin has registered its options.
for _, plugin in ipairs(hl.get_loaded_plugins()) do
  if plugin.name == "Omarchy Cube" then
    local directory = (os.getenv("XDG_CONFIG_HOME") or (os.getenv("HOME") .. "/.config")) .. "/hypr/"
    local file = io.open(directory .. "cube-gui.lua", "r")
    if file then
      file:close()
      hl.config({ plugin = { cube = dofile(directory .. "cube-gui.lua") } })
    end
    break
  end
end
