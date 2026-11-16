hl.monitor({ output = "", mode = "1280x800@60", position = "auto", scale = 1 })
hl.config({ misc = { disable_hyprland_logo = true, disable_splash_rendering = true }, decoration = { blur = { enabled = false } }, animations = { enabled = true } })
hl.permission({ binary = "/usr/bin/hyprctl", type = "plugin", mode = "allow" })

hl.monitor({ output = "CUBE-test", mode = "3840x2160@60", position = "1280x0", scale = 1 })
