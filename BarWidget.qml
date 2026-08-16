import QtQuick
import qs.Commons
import qs.Ui

BarWidget {
  id: root
  moduleName: "perro.hermes-kanban"

  function injectPanel() {
    var target = panelLoader.item
    if (!target) return
    if ("bar" in target) target.bar = root.bar
    if ("settings" in target) target.settings = root.settings
    if ("anchorItem" in target) target.anchorItem = button
    if ("hostWidget" in target) target.hostWidget = root
  }

  function refresh() {
    if (panelLoader.item && panelLoader.item.refresh) panelLoader.item.refresh()
  }

  function togglePanel() {
    if (panelLoader.item && panelLoader.item.toggle) panelLoader.item.toggle()
  }

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened === true : false
  readonly property bool popoutSwitchClosing: panelLoader.item ? panelLoader.item.popoutSwitchClosing === true : false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function closeForPopoutSwitch() { if (panelLoader.item) panelLoader.item.closeForPopoutSwitch() }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  onBarChanged: injectPanel()
  onSettingsChanged: injectPanel()

  Loader {
    id: panelLoader
    active: true
    source: Qt.resolvedUrl("Panel.qml")
    visible: false
    onLoaded: {
      root.injectPanel()
      Qt.callLater(root.injectPanel)
    }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: panelLoader.item ? panelLoader.item.tooltipText : "Hermes Kanban"
    iconComponent: Component {
      Item {
        Text {
          anchors.centerIn: parent
          text: "▦"
          color: panelLoader.item ? panelLoader.item.barIconColor : root.barForeground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.pixelSize: Style.font.icon
        }

        Rectangle {
          visible: panelLoader.item && panelLoader.item.aggregate.running > 0
          anchors.right: parent.right
          anchors.bottom: parent.bottom
          width: Math.max(Style.space(8), badgeText.implicitWidth + Style.space(3))
          height: Style.space(8)
          radius: height / 2
          color: panelLoader.item ? panelLoader.item.runningColor : root.barForeground

          Text {
            id: badgeText
            anchors.centerIn: parent
            text: panelLoader.item && panelLoader.item.aggregate.running > 99
              ? "99+" : String(panelLoader.item ? panelLoader.item.aggregate.running : 0)
            color: Color.background
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Math.max(Style.space(5), Style.font.caption - 2)
            font.bold: true
          }
        }

        Rectangle {
          visible: panelLoader.item && panelLoader.item.aggregate.blocked > 0
          anchors.right: parent.right
          anchors.top: parent.top
          width: Style.space(5)
          height: width
          radius: width / 2
          color: panelLoader.item ? panelLoader.item.urgent : Color.urgent
        }
      }
    }
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton || buttonCode === Qt.RightButton) root.refresh()
      else root.togglePanel()
    }
  }
}
