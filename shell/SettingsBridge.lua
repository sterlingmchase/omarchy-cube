
-- Omarchy Cube GUI bridge v2
do
  local function parse(data)
    local header = "-- Omarchy Cube GUI settings v1\nreturn {\n"
    assert(data:sub(1, #header) == header and data:sub(-2) == "}\n", "Unrecognized cube-gui.lua")
    local ranges = {
      face_curvature = {-1, 1}, duration_ms = {120, 600}, workspace_count = {4, 20}, zoom = {0, 1.5},
      horizontal_sensitivity = {.25, 3}, vertical_sensitivity = {.25, 3}, skydome_brightness = {.1, 1},
    }
    local bools = {
      enabled = true, trackpad_enabled = true, carry_windows = true, show_labels = true,
      highlight_selected = true, invert_horizontal = true, invert_vertical = true,
      momentum = true, skydome_enabled = true,
    }
    local values = {}
    local body = data:sub(#header + 1, -3)
    assert(body:sub(-1) == "\n", "Invalid cube settings body")
    for line in body:gmatch("[^\n]*\n") do
      local key, raw = line:match("^  ([a-z_0-9]+) = (.+),\n$")
      assert(key and values[key] == nil, "Invalid or duplicate cube setting")
      if bools[key] then
        assert(raw == "true" or raw == "false", "Invalid cube boolean")
        values[key] = raw == "true"
      elseif ranges[key] then
        local n = tonumber(raw)
        local range = ranges[key]
        assert(n and n >= range[1] and n <= range[2], "Invalid cube number")
        if key == "workspace_count" or key == "duration_ms" then
          n = assert(math.tointeger(n), "Invalid cube integer")
        end
        values[key] = n
      else
        local index = tonumber(key:match("^workspace_name_(%d%d?)$"))
        local name = index and index >= 1 and index <= 20 and key == "workspace_name_" .. index
        assert(name or key == "skydome_path" or key == "skydome_mode", "Unknown cube setting")
        local escaped = assert(raw:match('^"(.*)"$'), "Invalid cube string")
        local decoded, count = escaped:gsub("\\(%d%d%d)", function(byte)
          return string.char(tonumber(byte))
        end)
        assert(count * 4 == #escaped and utf8.len(decoded) and not decoded:find("%z"), "Invalid cube string bytes")
        if name then
          assert(utf8.len(decoded) <= 80 and not decoded:find("[%c]"), "Invalid workspace name")
          for _, cp in utf8.codes(decoded) do
            assert(not (cp >= 128 and cp <= 159 or cp == 8232 or cp == 8233), "Invalid workspace name")
          end
        elseif key == "skydome_path" then
          local ext = decoded:lower():match("%.([a-z]+)$")
          assert(#decoded <= 4096 and (decoded == "" or decoded:sub(1, 1) == "/" and
            (ext == "png" or ext == "jpg" or ext == "jpeg")), "Invalid skydome path")
        else
          assert(decoded == "auto" or decoded == "photo" or decoded == "panorama", "Invalid skydome mode")
        end
        values[key] = decoded
      end
    end
    assert(next(values), "Empty cube settings")
    return values
  end

  for _, plugin in ipairs(hl.get_loaded_plugins()) do
    if plugin.name == "Omarchy Cube" then
      local data = hl.plugin.cube.read_settings()
      if data then
        hl.config({ plugin = { cube = parse(data) } })
      end
      break
    end
  end
end
-- End Omarchy Cube GUI bridge v2
