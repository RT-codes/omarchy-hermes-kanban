import QtQuick
import QtQuick.Effects

Item {
  id: root

  property string iconName: ""
  property color iconColor: "white"
  property bool spinning: false

  implicitWidth: 16
  implicitHeight: 16

  Image {
    id: sourceImage
    anchors.fill: parent
    source: root.iconName === "" ? "" : Qt.resolvedUrl("assets/status/" + root.iconName + ".svg")
    sourceSize.width: Math.max(1, Math.round(width))
    sourceSize.height: Math.max(1, Math.round(height))
    fillMode: Image.PreserveAspectFit
    smooth: true
    visible: false
    layer.enabled: true
  }

  MultiEffect {
    anchors.fill: sourceImage
    source: sourceImage
    colorization: 1.0
    colorizationColor: root.iconColor
  }

  RotationAnimator {
    target: root
    from: 0
    to: 360
    duration: 1200
    loops: Animation.Infinite
    running: root.spinning && root.visible
  }

  onSpinningChanged: if (!spinning) rotation = 0
}
