import QtQuick
import Quickshell
import Quickshell.Wayland

ShellRoot {
  PanelWindow {
    implicitWidth: 180
    implicitHeight: 50
    anchors.bottom: true
    exclusiveZone: 0
    WlrLayershell.namespace: "omarchy-dock"
    WlrLayershell.layer: WlrLayer.Top
    color: "#ff00ff"
  }
  PanelWindow {
    implicitWidth: 180
    implicitHeight: 50
    anchors.top: true
    exclusiveZone: 0
    WlrLayershell.namespace: "omarchy-dock-apps"
    WlrLayershell.layer: WlrLayer.Top
    color: "#00ffff"
  }
}
