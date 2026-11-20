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
  readonly property bool busy: bridge.running || picker.running || presetBridge.running || builtinCatalog.running
  property bool namesOpen: false
  property string settingsPage: "cube"
  onSettingsPageChanged: {
    viewport.contentY = 0
    if (settingsPage === "presets" && ready && !busy) {
      preset("list")
      builtinCatalog.running = true
    }
  }
  property var presetNames: []
  property string presetDraft: ""
  // Hidden panels must not retain editable controls or their clipboard hooks.
  component OpenEditor: Loader {
    width: parent.width
    visible: active
  }
  property var builtinPresets: []
  property string builtinSelection: ""
  property string presetAction: "list"
  property bool preserveOnOpen: false
  readonly property string helper: decodeURIComponent(Qt.resolvedUrl("control.py").toString().replace(/^file:\/\//, ""))
  property string operation: "read"
  Commons.Translations { id: strings; directory: Qt.resolvedUrl("i18n") }
  component SettingToggle: Toggle {
    implicitHeight: Style.space(40)
  }

  function imageUrl(path) {
    // Encode every path segment: punctuation must never become a URL query or fragment.
    if (typeof path !== "string" || !path.startsWith("/") || !/\.(png|jpe?g)$/i.test(path)) return ""
    return "file://" + path.replace(/^\/+/, "/").split("/").map(encodeURIComponent).join("/")
  }

  function change(key, value) {
    builtinSelection = ""
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
  function preset(action, builtinId) {
    if (busy) return
    presetAction = action
    errorMessage = ""
    let command = ["python3", helper, "presets", action]
    if (action === "builtin") command.push(builtinId)
    else if (action !== "list") command.push(root.presetDraft)
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
            if (result.presets !== undefined) root.presetNames = result.presets
            if (root.presetAction === "load" || root.presetAction === "builtin") {
              root.builtinSelection = root.presetAction === "builtin" ? presetBridge.command[4] : ""
              root.values = Object.assign({}, root.values, result.values)
              root.dirty = true
              root.messageKey = root.presetAction === "builtin" ? "builtinLoaded" : "presetLoaded"
            } else if (root.presetAction === "save") root.messageKey = "presetSaved"
            else if (root.presetAction === "delete") root.messageKey = "presetDeleted"
          }
        } catch (error) { root.messageKey = "responseError" }
      }
    }
  }
  Process {
    id: builtinCatalog
    command: ["python3", root.helper, "presets", "builtins"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          let result = JSON.parse(text)
          if (result.ok) root.builtinPresets = result.builtins
          else root.errorMessage = String(result.error).slice(0, 2048)
        } catch (error) { root.messageKey = "responseError" }
      }
    }
  }
  Process {
    id: setupLauncher
    command: ["omarchy-launch-terminal", "python3",
      decodeURIComponent(Qt.resolvedUrl("../tools/setup").toString().replace(/^file:\/\//, ""))]
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
    contentWidth: popup.fittedContentWidth(Style.space(520))
    contentHeight: popup.fittedContentHeight(header.implicitHeight + column.implicitHeight + footer.implicitHeight + Style.space(24), Style.space(500))
    Column {
      id: header
      anchors { top: parent.top; left: parent.left; right: parent.right }
      spacing: Style.space(10)
      PlainText { text: strings.t("title"); font.pixelSize: Style.font.display; font.bold: true }
      PlainText { width: parent.width; text: strings.t(root.ready ? "description_" + root.settingsPage : "about"); wrapMode: Text.WordWrap }
      Row {
        width: parent.width
        spacing: Style.space(6)
        visible: root.ready
        Repeater {
          model: ["cube", "controls", "background", "presets"]
          Button {
            required property string modelData
            width: (parent.width - Style.space(18)) / 4
            text: strings.t("tab_" + modelData)
            selected: root.settingsPage === modelData
            bordered: true; focusable: true
            Accessible.name: text
            onClicked: root.settingsPage = modelData
          }
        }
      }
    }
    Flickable {
      id: viewport
      anchors { top: header.bottom; topMargin: Style.space(12); left: parent.left; right: parent.right; bottom: footer.top; bottomMargin: Style.space(12) }
      clip: true
      contentHeight: column.implicitHeight
      boundsBehavior: Flickable.StopAtBounds
      Keys.onEscapePressed: root.close()
      Column {
        id: column
        width: parent.width
        spacing: Style.space(12)
        Column {
          width: parent.width
          spacing: Style.space(12)
          visible: root.ready
          enabled: !root.busy
          Column {
            width: parent.width
            spacing: Style.space(10)
            visible: root.settingsPage === "cube"
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
          PlainText { text: strings.t("appearance"); font.bold: true }
          SettingToggle {
            width: parent.width
            label: strings.t("enabled")
            checked: root.values.enabled === true
            onClicked: root.change("enabled", !root.values.enabled)
          }
          Repeater {
            model: ["show_labels", "highlight_selected"]
            SettingToggle {
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
              {key: "workspace_count", title: "workspaces", min: 4, max: 20, step: 1, decimals: 0, unit: ""},
              {key: "face_curvature", title: "curvature", min: -1, max: 1, step: .05, decimals: 2, unit: ""}
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
          PlainText { width: parent.width; text: strings.t("curvatureHelp"); wrapMode: Text.WordWrap }
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
                OpenEditor {
                  id: nameEditor
                  readonly property string setting: parent.setting
                  readonly property int number: parent.index + 1
                  active: root.opened && root.ready && root.settingsPage === "cube" && root.namesOpen
                  sourceComponent: TextField {
                    text: root.values[nameEditor.setting] || ""
                    maximumLength: 160 // UTF-16 code units; the helper enforces 80 Unicode characters.
                    placeholderText: strings.t("workspaceNamePlaceholder")
                    Accessible.name: strings.t("workspaceName").arg(Commons.I18n.formatNumber(nameEditor.number))
                    onTextEdited: root.change(nameEditor.setting, text)
                  }
                }
              }
            }
          }
          }
          Column {
            width: parent.width
            spacing: Style.space(10)
            visible: root.settingsPage === "controls"
          PlainText { text: strings.t("dragControls"); font.bold: true }
          PlainText { width: parent.width; text: strings.t("mouseHelp"); wrapMode: Text.WordWrap }
          SettingToggle {
            width: parent.width
            label: strings.t("trackpad_enabled")
            checked: root.values.trackpad_enabled === true
            onClicked: root.change("trackpad_enabled", !root.values.trackpad_enabled)
          }
          PlainText { width: parent.width; text: strings.t("trackpadHelp"); wrapMode: Text.WordWrap }
          SettingToggle {
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
            SettingToggle {
              required property string modelData
              width: parent.width
              label: strings.t(modelData)
              checked: root.values[modelData] === true
              onClicked: root.change(modelData, !root.values[modelData])
            }
          }
          PlainText { width: parent.width; text: strings.t("momentumHelp"); wrapMode: Text.WordWrap }
          }
          Column {
            width: parent.width
            spacing: Style.space(10)
            visible: root.settingsPage === "background"
          PlainText { text: strings.t("background"); font.bold: true }
          SettingToggle {
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
          OpenEditor {
            active: root.opened && root.ready && root.settingsPage === "background"
            sourceComponent: TextField {
              text: root.values.skydome_path || ""
              placeholderText: strings.t("imagePlaceholder")
              maximumLength: 4096
              Accessible.name: strings.t("image")
              onTextEdited: root.change("skydome_path", text)
            }
          }
          PlainText { width: parent.width; text: strings.t("imageHelp"); wrapMode: Text.WordWrap }
          PlainText { width: parent.width; text: strings.t("parallaxHelp"); wrapMode: Text.WordWrap }
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
          }
          Column {
            width: parent.width
            spacing: Style.space(10)
            visible: root.settingsPage === "presets"
            PlainText { text: strings.t("builtinPresets"); font.bold: true }
            PlainText { width: parent.width; text: strings.t("builtinHelp"); wrapMode: Text.WordWrap }
            Grid {
              width: parent.width
              columns: width >= Style.space(420) ? 2 : 1
              spacing: Style.space(12)
              Repeater {
                model: root.builtinPresets
                Column {
                  required property var modelData
                  width: (parent.width - (parent.columns - 1) * parent.spacing) / parent.columns
                  spacing: Style.space(6)
                  Image {
                    width: parent.width
                    height: width / 2
                    source: root.imageUrl(parent.modelData.preview)
                    sourceSize.width: 480
                    sourceSize.height: 240
                    fillMode: Image.PreserveAspectCrop
                    asynchronous: true
                  }
                  Button {
                    width: parent.width
                    text: strings.t("builtin_" + parent.modelData.id)
                    selected: root.builtinSelection === parent.modelData.id
                    bordered: true; focusable: true
                    onClicked: root.preset("builtin", parent.modelData.id)
                  }
                  PlainText {
                    width: parent.width
                    text: strings.tn("builtinWorkspaces", parent.modelData.workspace_count).arg(Commons.I18n.formatNumber(parent.modelData.workspace_count))
                  }
                  PlainText {
                    width: parent.width
                    text: strings.t("builtinDescription_" + parent.modelData.id)
                    wrapMode: Text.WordWrap
                  }
                }
              }
            }
            PlainText { text: strings.t("myPresets"); font.bold: true; topPadding: Style.space(8) }
            PlainText { width: parent.width; text: strings.t("presetsHelp"); wrapMode: Text.WordWrap }
            Dropdown {
              width: parent.width
              label: strings.t("savedPresets")
              options: root.presetNames
              value: root.presetDraft
              onChanged: function(value) { root.presetDraft = value }
            }
            OpenEditor {
              active: root.opened && root.ready && root.settingsPage === "presets"
              sourceComponent: TextField {
                text: root.presetDraft
                maximumLength: 128
                placeholderText: strings.t("presetName")
                Accessible.name: strings.t("presetName")
                onTextEdited: root.presetDraft = text
              }
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
                  enabled: root.presetDraft.trim() !== "" && (modelData === "save" || root.presetNames.indexOf(root.presetDraft) >= 0)
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
      Row {
        width: parent.width
        spacing: Style.space(8)
        Button {
          width: root.ready ? (parent.width - Style.space(8)) * 0.65 : 0
          visible: root.ready
          text: strings.t(root.busy ? "applying" : "apply")
          selected: root.dirty
          bordered: true; focusable: true
          enabled: root.dirty && !root.busy
          onClicked: root.run("apply")
        }
        Button {
          width: root.ready ? (parent.width - Style.space(8)) * 0.35 : parent.width
          text: strings.t("refresh")
          bordered: true; focusable: true
          enabled: !root.busy && !root.dirty
          onClicked: root.run("read")
        }
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
        visible: !root.ready
        text: strings.t("setup")
        bordered: true; focusable: true
        enabled: !root.busy && !setupLauncher.running
        onClicked: { setupLauncher.running = true; root.close() }
      }
    }
  }
}
