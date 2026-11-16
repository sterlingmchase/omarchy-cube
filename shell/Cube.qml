pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Shapes
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui

Panel {
  id: root
  moduleName: "local.cube"
  ipcTarget: "local.cube"
  implicitWidth: icon.implicitWidth
  implicitHeight: icon.implicitHeight
  property var values: ({})
  property bool ready: false
  property bool dirty: false
  property string messageKey: "read"
  property string errorMessage: ""
  readonly property bool busy: bridge.running || picker.running || presetBridge.running
  property bool namesOpen: false
  property bool presetsOpen: false
  property var presetNames: []
  property string presetAction: "list"
  property bool preserveOnOpen: false
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("control.py").toString().replace(/^file:\/\//, ""))
  property string operation: "read"
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }

  function imageUrl(path) {
    // Encode every path segment: punctuation must never become a URL query or fragment.
    if (typeof path !== "string" || !path.startsWith("/") || !/\.(png|jpe?g)$/i.test(path)) return ""
    return "file://" + path.replace(/^\/+/, "/").split("/").map(encodeURIComponent).join("/")
  }

  function change(key, value) {
    let next = Object.assign({}, values)
    next[key] = value
    values = next
    dirty = true
    messageKey = "unsaved"
    errorMessage = ""
  }
  function run(action) {
    if (busy) return
    operation = action
    messageKey = action === "apply" ? "applying" : "read"
    errorMessage = ""
    bridge.command = action === "apply"
      ? ["python3", helper, "apply", JSON.stringify(values)]
      : ["python3", helper, "read"]
    bridge.running = true
  }
  function navigate(action) {
    if (busy) return
    operation = "navigate"
    errorMessage = ""
    root.close()
    bridge.command = ["python3", helper, "navigate", action]
    bridge.running = true
  }
  function preset(action) {
    if (busy) return
    presetAction = action
    errorMessage = ""
    let command = ["python3", helper, "presets", action]
    if (action !== "list") command.push(presetName.text)
    if (action === "save") command.push(JSON.stringify(values))
    presetBridge.command = command
    presetBridge.running = true
  }
  onOpenedChanged: if (opened) {
    if (preserveOnOpen) preserveOnOpen = false
    else if (!busy) { ready = false; dirty = false; viewport.contentY = 0; run("read") }
  }
  Process {
    id: presetBridge
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          let result = JSON.parse(text)
          if (!result.ok) root.errorMessage = String(result.error).slice(0, 2048)
          else {
            root.presetNames = result.presets
            if (root.presetAction === "load") {
              root.values = Object.assign({}, root.values, result.values)
              root.dirty = true
              root.messageKey = "presetLoaded"
            } else if (root.presetAction === "save") root.messageKey = "presetSaved"
            else if (root.presetAction === "delete") root.messageKey = "presetDeleted"
          }
        } catch (error) { root.messageKey = "responseError" }
      }
    }
  }
  Process {
    id: picker
    command: ["python3", root.helper, "pick"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          let result = JSON.parse(text)
          if (!result.ok) root.errorMessage = String(result.error).slice(0, 2048)
          else if (result.path !== null) root.change("skydome_path", result.path)
        } catch (error) { root.messageKey = "responseError" }
        if (!root.opened) { root.preserveOnOpen = true; root.toggle() }
      }
    }
  }
  Process {
    id: bridge
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          let result = JSON.parse(text)
          if (result.ok) {
            root.errorMessage = String(result.warning || "").slice(0, 2048)
            root.values = result.values
            root.ready = true
            root.dirty = false
            root.messageKey = root.operation === "apply" ? "saved" : "instructions"
          } else {
            root.errorMessage = String(result.error).slice(0, 2048)
            if (root.operation === "navigate" && !root.opened) root.toggle()
          }
        } catch (error) {
          root.messageKey = "responseError"
        }
      }
    }
  }
  BarIconButton {
    id: icon
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component {
      Shape {
        width: 24; height: 26
        preferredRendererType: Shape.CurveRenderer
        ShapePath {
          strokeWidth: 0
          strokeColor: "transparent"
          fillColor: Commons.Color.accent
          PathSvg { path: "M 12,0 L 24,6 L 12,12 L 0,6 Z" }
        }
        ShapePath {
          strokeWidth: 0
          strokeColor: "transparent"
          fillColor: icon.foreground
          PathSvg { path: "M 0,9 L 10,14 L 10,26 L 0,21 Z M 13,14 L 24,8.5 L 24,13.5 L 13,19 Z M 13,22 L 24,16.5 L 24,20.5 L 13,26 Z" }
        }
      }
    }
    tooltipText: strings.t("title")
    onPressed: root.toggle()
  }
  KeyboardPanel {
    id: popup
    anchorItem: icon
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: viewport
    contentWidth: popup.fittedContentWidth(Style.space(420))
    contentHeight: popup.fittedContentHeight(column.implicitHeight + footer.implicitHeight + Style.space(12), Style.space(570))
    Flickable {
      id: viewport
      anchors { top: parent.top; left: parent.left; right: parent.right; bottom: footer.top; bottomMargin: Style.space(12) }
      clip: true
      contentHeight: column.implicitHeight
      boundsBehavior: Flickable.StopAtBounds
      Keys.onEscapePressed: root.close()
      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)
        PlainText { text: strings.t("title"); font.pixelSize: Style.font.display; font.bold: true }
        PlainText { width: parent.width; text: strings.t("about"); wrapMode: Text.WordWrap }
        Column {
          width: parent.width
          spacing: Style.space(12)
          visible: root.ready
          enabled: !root.busy
          Row {
            width: parent.width
            spacing: Style.space(6)
            Button {
              width: (parent.width - Style.space(12)) / 3
              text: strings.t("previous")
              bordered: true; focusable: true
              onClicked: root.navigate("left")
            }
            Button {
              width: (parent.width - Style.space(12)) / 3
              text: strings.t("mouseControls")
              bordered: true; focusable: true
              onClicked: root.navigate("overview")
            }
            Button {
              width: (parent.width - Style.space(12)) / 3
              text: strings.t("next")
              bordered: true; focusable: true
              onClicked: root.navigate("right")
            }
          }
          PlainText { width: parent.width; text: strings.t("mouseHelp"); wrapMode: Text.WordWrap }
          PlainText { text: strings.t("appearance"); font.bold: true }
          Toggle {
            width: parent.width
            label: strings.t("enabled")
            checked: root.values.enabled === true
            onClicked: root.change("enabled", !root.values.enabled)
          }
          Repeater {
            model: ["show_labels", "highlight_selected"]
            Toggle {
              required property string modelData
              width: parent.width
              label: strings.t(modelData)
              checked: root.values[modelData] === true
              onClicked: root.change(modelData, !root.values[modelData])
            }
          }
          Repeater {
            model: [
              {key: "duration_ms", title: "duration", min: 120, max: 600, step: 10, decimals: 0, unit: " ms"},
              {key: "zoom", title: "zoom", min: 0, max: 1.5, step: .05, decimals: 2, unit: ""},
              {key: "workspace_count", title: "workspaces", min: 4, max: 20, step: 1, decimals: 0, unit: ""}
            ]
            ValueRow {
              required property var modelData
              width: parent.width
              title: strings.t(modelData.title)
              minimum: modelData.min; maximum: modelData.max; step: modelData.step
              decimals: modelData.decimals; unit: modelData.unit
              value: root.values[modelData.key] || 0
              onEdited: function(number) { root.change(modelData.key, Number(number.toFixed(4))) }
            }
          }
          PlainText { width: parent.width; text: strings.t("workspaceHelp"); wrapMode: Text.WordWrap }
          Button {
            width: parent.width
            text: strings.t("workspaceNames")
            selected: root.namesOpen
            bordered: true; focusable: true
            onClicked: root.namesOpen = !root.namesOpen
          }
          Column {
            width: parent.width
            spacing: Style.space(6)
            visible: root.namesOpen
            PlainText { width: parent.width; text: strings.t("workspaceNamesHelp"); wrapMode: Text.WordWrap }
            Repeater {
              model: root.namesOpen ? (root.values.workspace_count || 0) : 0
              Column {
                required property int index
                readonly property string setting: "workspace_name_" + (index + 1)
                width: parent.width
                PlainText { text: strings.t("workspaceName").arg(Commons.I18n.formatNumber(parent.index + 1)) }
                TextField {
                  width: parent.width
                  text: root.values[parent.setting] || ""
                  maximumLength: 160 // UTF-16 code units; the helper enforces 80 Unicode characters.
                  placeholderText: strings.t("workspaceNamePlaceholder")
                  Accessible.name: strings.t("workspaceName").arg(Commons.I18n.formatNumber(parent.index + 1))
                  onTextEdited: root.change(parent.setting, text)
                }
              }
            }
          }
          PlainText { text: strings.t("dragControls"); font.bold: true }
          Toggle {
            width: parent.width
            label: strings.t("trackpad_enabled")
            checked: root.values.trackpad_enabled === true
            onClicked: root.change("trackpad_enabled", !root.values.trackpad_enabled)
          }
          PlainText { width: parent.width; text: strings.t("trackpadHelp"); wrapMode: Text.WordWrap }
          Toggle {
            width: parent.width
            label: strings.t("carry_windows")
            checked: root.values.carry_windows === true
            onClicked: root.change("carry_windows", !root.values.carry_windows)
          }
          PlainText { width: parent.width; text: strings.t("carryWindowsHelp"); wrapMode: Text.WordWrap }
          Repeater {
            model: [
              {key: "horizontal_sensitivity", title: "horizontalSensitivity", min: .25, max: 3, step: .05, decimals: 2, unit: ""},
              {key: "vertical_sensitivity", title: "verticalSensitivity", min: .25, max: 3, step: .05, decimals: 2, unit: ""}
            ]
            ValueRow {
              required property var modelData
              width: parent.width
              title: strings.t(modelData.title)
              minimum: modelData.min; maximum: modelData.max; step: modelData.step
              decimals: modelData.decimals; unit: modelData.unit
              value: root.values[modelData.key] || 0
              onEdited: function(number) { root.change(modelData.key, Number(number.toFixed(4))) }
            }
          }
          Repeater {
            model: ["invert_horizontal", "invert_vertical", "momentum"]
            Toggle {
              required property string modelData
              width: parent.width
              label: strings.t(modelData)
              checked: root.values[modelData] === true
              onClicked: root.change(modelData, !root.values[modelData])
            }
          }
          PlainText { width: parent.width; text: strings.t("momentumHelp"); wrapMode: Text.WordWrap }
          PlainText { text: strings.t("background"); font.bold: true }
          Toggle {
            width: parent.width
            label: strings.t("sky")
            checked: root.values.skydome_enabled === true
            onClicked: root.change("skydome_enabled", !root.values.skydome_enabled)
          }
          ValueRow {
            width: parent.width
            title: strings.t("brightness")
            minimum: .1; maximum: 1; step: .05; decimals: 2
            value: root.values.skydome_brightness || .65
            onEdited: function(number) { root.change("skydome_brightness", Number(number.toFixed(4))) }
          }
          PlainText { text: strings.t("image") }
          TextField {
            width: parent.width
            text: root.values.skydome_path || ""
            placeholderText: strings.t("imagePlaceholder")
            maximumLength: 4096
            Accessible.name: strings.t("image")
            onTextEdited: root.change("skydome_path", text)
          }
          PlainText { width: parent.width; text: strings.t("imageHelp"); wrapMode: Text.WordWrap }
          Row {
            width: parent.width
            spacing: Style.space(6)
            Repeater {
              model: ["auto", "photo", "panorama"]
              Button {
                required property string modelData
                width: (parent.width - Style.space(12)) / 3
                text: strings.t(modelData)
                selected: root.values.skydome_mode === modelData
                bordered: true; focusable: true
                onClicked: root.change("skydome_mode", modelData)
              }
            }
          }
          Image {
            id: preview
            width: parent.width
            height: visible ? Style.space(150) : 0
            visible: source.toString() !== ""
            source: root.imageUrl(root.values.skydome_path)
            sourceSize.width: 640
            sourceSize.height: 300
            fillMode: Image.PreserveAspectFit
            asynchronous: true
            cache: false
          }
          PlainText {
            width: parent.width
            visible: !!root.values.skydome_path && (preview.source.toString() === "" || preview.status === Image.Error)
            text: strings.t("previewError")
            wrapMode: Text.WordWrap
          }
          Button {
            width: parent.width
            text: strings.t("browse")
            bordered: true; focusable: true
            onClicked: { root.close(); picker.running = true }
          }
          Button {
            width: parent.width
            text: strings.t("presets")
            selected: root.presetsOpen
            bordered: true; focusable: true
            onClicked: {
              root.presetsOpen = !root.presetsOpen
              if (root.presetsOpen) root.preset("list")
            }
          }
          Column {
            width: parent.width
            spacing: Style.space(8)
            visible: root.presetsOpen
            PlainText { width: parent.width; text: strings.t("presetsHelp"); wrapMode: Text.WordWrap }
            Dropdown {
              width: parent.width
              label: strings.t("savedPresets")
              options: root.presetNames
              value: presetName.text
              onChanged: function(value) { presetName.text = value }
            }
            TextField {
              id: presetName
              width: parent.width
              maximumLength: 128
              placeholderText: strings.t("presetName")
              Accessible.name: strings.t("presetName")
            }
            Row {
              width: parent.width
              spacing: Style.space(6)
              Repeater {
                model: ["save", "load", "delete"]
                Button {
                  required property string modelData
                  width: (parent.width - Style.space(12)) / 3
                  text: strings.t("preset_" + modelData)
                  bordered: true; focusable: true
                  enabled: presetName.text.trim() !== "" && (modelData === "save" || root.presetNames.indexOf(presetName.text) >= 0)
                  onClicked: root.preset(modelData)
                }
              }
            }
          }
        }
      }
    }
    Column {
      id: footer
      anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
      spacing: Style.space(8)
      Button {
        width: parent.width
        visible: root.ready
        text: strings.t(root.busy ? "applying" : "apply")
        selected: root.dirty
        bordered: true; focusable: true
        enabled: root.dirty && !root.busy
        onClicked: root.run("apply")
      }
      PlainText {
        width: parent.width
        text: root.errorMessage || strings.t(root.messageKey)
        wrapMode: Text.WordWrap
        maximumLineCount: 5
        elide: Text.ElideRight
      }
      Button {
        width: parent.width
        text: strings.t("refresh")
        bordered: true; focusable: true
        enabled: !root.busy
        onClicked: root.run("read")
      }
    }
  }
}
