import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model
import "." as Plugin

Panel {
  id: root
  moduleName: "io.github.davidojedalopez.hermes-kanban"
  ipcTarget: "io.github.davidojedalopez.hermes-kanban"
  manageIpc: false

  property Item anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color surface: Color.popups.background
  readonly property color blockedBrightColor: "#ff6b6b"
  readonly property color blockedDarkColor: "#b42318"
  readonly property color blockedColor: Model.higherContrastColor(blockedBrightColor, blockedDarkColor, surface)
  readonly property color runningColor: "#34d399"
  readonly property color reviewColor: "#fbbf24"
  readonly property color readyColor: "#60a5fa"
  readonly property string fontFamily: bar && bar.fontFamily ? bar.fontFamily : "monospace"

  readonly property var store: Plugin.SnapshotStore
  readonly property string connectionMode: store.connectionMode
  readonly property string endpointLabel: connectionMode === "remote" ? store.sshHost : "Local"
  readonly property var selectedSlugs: store.selectedSlugs
  readonly property var snapshot: store.snapshot
  readonly property bool refreshing: store.refreshing
  readonly property bool stale: store.stale
  readonly property string lastError: store.lastError
  readonly property double nowSeconds: store.nowSeconds

  readonly property var aggregate: Model.aggregate(snapshot, selectedSlugs)
  readonly property var selectedBoards: Model.selectedBoardModels(snapshot, selectedSlugs)
  readonly property color barIconColor: lastError !== "" && !snapshot ? urgent
    : aggregate.blocked > 0 ? blockedColor
    : aggregate.review > 0 ? reviewColor
    : aggregate.running > 0 ? runningColor
    : dim
  readonly property string tooltipText: lastError !== ""
    ? "Hermes Kanban · " + lastError
    : aggregate.selected === 0
      ? "Hermes Kanban · choose boards"
      : "Hermes Kanban · " + aggregate.running + " running, " + aggregate.blocked + " blocked"

  function configureStore() {
    store.configure(
      setting("connectionMode", "Local"),
      setting("hermesPath", "hermes"),
      setting("sshHost", ""),
      setting("includeTaskBodies", false) === true,
      setting("openRefreshSec", 15),
      setting("backgroundRefreshSec", 120)
    )
  }

  function statusColor(status) {
    if (status === "blocked") return blockedColor
    if (status === "review") return reviewColor
    if (status === "running") return runningColor
    if (status === "ready") return readyColor
    if (status === "done") return dim
    return foreground
  }

  function refresh() {
    store.refresh()
  }

  function applyBoardSelection(values) {
    store.applyBoardSelection(values)
  }

  function openHermes() {
    Quickshell.execDetached(["gtk-launch", "hermes"])
  }

  function copyTaskId(taskId) {
    if (!taskId) return
    Quickshell.execDetached(["wl-copy", String(taskId)])
  }

  onOpenedChanged: {
    store.setPanelOpen(opened)
    if (opened) {
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
    }
  }

  onSettingsChanged: configureStore()

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Component.onCompleted: configureStore()

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "▦"
    active: root.aggregate.blocked > 0 || (!root.snapshot && root.lastError !== "")
    activeColor: root.barIconColor
    foreground: root.barIconColor
    tooltipText: root.tooltipText
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton || buttonCode === Qt.RightButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem || button
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(460))
    contentHeight: panel.fittedContentHeight(contentColumn.implicitHeight, Style.space(650))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(text) {
        if (text === "r" || text === "R") root.refresh()
        else if (text === "o" || text === "O") root.openHermes()
      }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: contentColumn
          width: panelFlick.width
          spacing: Style.space(12)

          PanelHero {
            width: parent.width
            title: "Hermes Kanban"
            meta: root.refreshing ? "Refreshing " + root.connectionMode + " boards…"
              : root.snapshot ? Model.ageLabel(root.snapshot.fetchedAt, root.nowSeconds)
              : "Waiting for the first snapshot"
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconComponent: Component {
            Text {
              text: "▦"
              textFormat: Text.PlainText
                color: root.barIconColor
                font.family: root.fontFamily
                font.pixelSize: Style.font.display
              }
            }
          }

          RowLayout {
            width: parent.width
            spacing: Style.space(8)

            Button {
              text: root.refreshing ? "Refreshing" : "Refresh"
              iconText: "󰑐"
              iconSpinning: root.refreshing
              enabled: !root.refreshing
              focusable: true
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.refresh()
            }

            Button {
              text: "Open Hermes"
              iconText: "󰋜"
              focusable: true
              foreground: root.foreground
              fontFamily: root.fontFamily
              onClicked: root.openHermes()
            }

            Item { Layout.fillWidth: true }

            Text {
              text: root.endpointLabel
              textFormat: Text.PlainText
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              elide: Text.ElideMiddle
              Layout.maximumWidth: Style.space(130)
            }
          }

          Text {
            visible: root.lastError !== ""
            width: parent.width
            text: (root.stale ? "Showing stale data · " : "") + root.lastError
            textFormat: Text.PlainText
            color: root.urgent
            font.family: root.fontFamily
            font.pixelSize: Style.font.bodySmall
            wrapMode: Text.WordWrap
          }

          MultiSelect {
            width: parent.width
            label: "BOARDS"
            values: root.selectedSlugs
            options: Model.boardOptions(root.snapshot)
            noSelectionText: root.snapshot ? "Choose boards" : "Boards unavailable"
            placeholderText: "Search boards…"
            emptyText: "No Hermes boards found"
            foreground: root.foreground
            fontFamily: root.fontFamily
            onChanged: function(values) { root.applyBoardSelection(values) }
          }

          Text {
            visible: root.selectedSlugs.length === 0
            width: parent.width
            text: root.snapshot ? "Choose one or more boards to monitor."
              : (root.connectionMode === "remote" ? "Connect over SSH to discover boards." : "Start Hermes locally to discover boards.")
            textFormat: Text.PlainText
            color: root.dim
            font.family: root.fontFamily
            font.pixelSize: Style.font.body
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
          }

          Repeater {
            model: root.selectedBoards

            delegate: Column {
              id: boardSection
              required property var modelData
              width: contentColumn.width
              spacing: Style.space(8)

              PanelSeparator {
                width: parent.width
                foreground: root.foreground
              }

              RowLayout {
                width: parent.width
                spacing: Style.space(8)

                ColumnLayout {
                  Layout.fillWidth: true
                  spacing: Style.space(1)

                  Text {
                    text: modelData.name
                    textFormat: Text.PlainText
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.heading
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }

                  Text {
                    text: modelData.missing ? modelData.slug + " · unavailable" : modelData.slug
                    textFormat: Text.PlainText
                    color: modelData.missing ? root.urgent : root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }
                }

                Text {
                  text: modelData.counts.running + " running"
                  textFormat: Text.PlainText
                  color: modelData.counts.running > 0 ? root.runningColor : root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.bodySmall
                  Layout.alignment: Qt.AlignTop
                }
              }

              RowLayout {
                visible: !modelData.missing
                width: parent.width
                spacing: Style.space(3)

                Repeater {
                  model: Model.STATUS_ORDER

                  delegate: Rectangle {
                    id: statusCell
                    required property string modelData
                    readonly property int statusCount: Math.max(0, Number(boardSection.modelData.counts[modelData] || 0))
                    readonly property bool blockedActive: modelData === "blocked" && statusCount > 0
                    Layout.fillWidth: true
                    implicitHeight: funnelColumn.implicitHeight + Style.space(8)
                    radius: Style.cornerRadius
                    color: blockedActive
                      ? Util.alpha(root.blockedColor, 0.15)
                      : Style.normalFillFor(root.foreground, Color.accent)
                    border.width: blockedActive ? 1 : 0
                    border.color: blockedActive ? Util.alpha(root.blockedColor, 0.72) : "transparent"
                    Accessible.name: Model.statusLabel(modelData) + ": " + statusCount
                    Accessible.role: Accessible.StaticText
                    ToolTip.visible: statusHover.hovered
                    ToolTip.delay: 400
                    ToolTip.text: Accessible.name

                    HoverHandler {
                      id: statusHover
                    }

                    Column {
                      id: funnelColumn
                      anchors.centerIn: parent
                      spacing: Style.space(1)

                      Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: String(statusCell.statusCount)
                        color: root.statusColor(statusCell.modelData)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.body
                        font.bold: statusCell.statusCount > 0
                      }

                      StatusIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: Style.font.body
                        height: width
                        iconName: Model.statusIcon(statusCell.modelData)
                        iconColor: statusCell.statusCount > 0 ? root.statusColor(statusCell.modelData) : root.foreground
                        opacity: statusCell.statusCount > 0 ? 1 : 0.45
                        spinning: statusCell.modelData === "running" && statusCell.statusCount > 0
                      }
                    }
                  }
                }
              }

              Text {
                visible: !modelData.missing && Model.detailTaskCount(modelData.tasks) === 0
                width: parent.width
                text: "No running, blocked, review, or ready tasks."
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.bodySmall
                horizontalAlignment: Text.AlignHCenter
              }

              Repeater {
                model: Model.DETAIL_STATUSES

                delegate: Column {
                  id: statusGroup
                  required property string modelData
                  readonly property var statusTasks: Model.tasksForStatus(boardSection.modelData.tasks, modelData)
                  visible: statusTasks.length > 0
                  width: parent.width
                  spacing: Style.space(5)

                  PanelSectionHeader {
                    width: parent.width
                    text: Model.statusLabel(modelData).toUpperCase() + "  " + statusTasks.length
                    foreground: root.statusColor(modelData)
                    fontFamily: root.fontFamily
                  }

                  Repeater {
                    model: statusGroup.statusTasks

                    delegate: TaskRow {
                      required property var modelData
                      width: parent.width
                      task: modelData
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }

  component TaskRow: CursorSurface {
    id: taskRow
    property var task: null
    property bool expanded: false
    foreground: root.foreground
    implicitHeight: taskContent.implicitHeight + Style.space(12)

    Rectangle {
      visible: taskRow.task && taskRow.task.status === "blocked"
      anchors.left: parent.left
      anchors.top: parent.top
      anchors.bottom: parent.bottom
      width: 3
      radius: width / 2
      color: root.blockedColor
    }

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onClicked: taskRow.expanded = !taskRow.expanded
    }

    ColumnLayout {
      id: taskContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(9)
      anchors.rightMargin: Style.space(9)
      spacing: Style.space(3)

      RowLayout {
        Layout.fillWidth: true
        spacing: Style.space(7)

        Text {
          text: Model.statusGlyph(taskRow.task.status)
          color: root.statusColor(taskRow.task.status)
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
        }

        Text {
          Layout.fillWidth: true
          text: taskRow.task.title
          textFormat: Text.PlainText
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          elide: Text.ElideRight
        }

        Text {
          text: taskRow.task.status === "running"
            ? Model.elapsed(taskRow.task.startedAt, root.nowSeconds)
            : (taskRow.task.assignee || "unassigned")
          textFormat: Text.PlainText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      Text {
        visible: taskRow.expanded && taskRow.task.body !== ""
        Layout.fillWidth: true
        text: taskRow.task.body
        textFormat: Text.PlainText
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
        wrapMode: Text.WordWrap
        maximumLineCount: 6
        elide: Text.ElideRight
      }

      RowLayout {
        visible: taskRow.expanded
        Layout.fillWidth: true
        spacing: Style.space(6)

        Text {
          Layout.fillWidth: true
          text: taskRow.task.id + (taskRow.task.assignee ? " · " + taskRow.task.assignee : "")
          textFormat: Text.PlainText
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }

        Button {
          text: "Copy ID"
          iconText: "󰆏"
          foreground: root.foreground
          fontFamily: root.fontFamily
          horizontalPadding: Style.space(6)
          verticalPadding: Style.space(3)
          onClicked: root.copyTaskId(taskRow.task.id)
        }
      }
    }
  }
}
