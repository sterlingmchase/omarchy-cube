import QtQuick
import QtQuick.Controls.Basic as Controls
import qs.Commons
import qs.Commons as Commons

Column {
  id: root
  property string title: ""
  property string unit: ""
  property real value: 0
  property real minimum: 0
  property real maximum: 1
  property real step: 1
  property int decimals: 0
  signal edited(real number)
  spacing: Style.space(4)
  Text {
    textFormat: Text.PlainText
    text: root.title + "  ·  " + Commons.I18n.formatNumber(root.value, root.decimals) + root.unit
    color: Commons.Color.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.bodySmall
  }
  Controls.Slider {
    id: slider
    width: parent.width
    implicitHeight: Style.space(30)
    from: root.minimum
    to: root.maximum
    stepSize: root.step
    snapMode: Controls.Slider.SnapAlways
    // Let wheel/trackpad scrolling reach the surrounding Flickable.
    wheelEnabled: false
    Accessible.name: root.title
    value: root.value
    activeFocusOnTab: true
    opacity: activeFocus ? 1 : .85
    Keys.onLeftPressed: root.edited(Math.max(root.minimum, root.value - root.step))
    Keys.onRightPressed: root.edited(Math.min(root.maximum, root.value + root.step))
    onMoved: root.edited(Math.max(root.minimum, Math.min(root.maximum,
      root.minimum + Math.round((value - root.minimum) / root.step) * root.step)))
    background: Rectangle {
      x: slider.leftPadding
      y: slider.topPadding + slider.availableHeight / 2 - height / 2
      width: slider.availableWidth
      height: Style.space(4)
      radius: height / 2
      color: Qt.rgba(Commons.Color.foreground.r, Commons.Color.foreground.g, Commons.Color.foreground.b, 0.18)
      Rectangle {
        width: parent.width * slider.position
        height: parent.height
        radius: height / 2
        color: Commons.Color.accent
      }
    }
    handle: Rectangle {
      x: slider.leftPadding + slider.visualPosition * (slider.availableWidth - width)
      y: slider.topPadding + slider.availableHeight / 2 - height / 2
      width: Style.space(16); height: width; radius: width / 2
      color: slider.pressed ? Commons.Color.accent : Commons.Color.foreground
      border.width: slider.activeFocus ? 2 : 1
      border.color: Commons.Color.background
    }
  }
}
