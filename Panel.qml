import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui
import "Model.js" as Model

Panel {
  id: root
  moduleName: "perro.hermes-kanban"
  ipcTarget: "perro.hermes-kanban"
  manageIpc: false

  property Item anchorItem: null
  property var hostWidget: null
  readonly property var barIdentity: hostWidget || root

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color urgent: bar ? bar.urgent : Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color runningColor: "#34d399"
  readonly property color reviewColor: "#fbbf24"
  readonly property color readyColor: "#60a5fa"
  readonly property string fontFamily: bar && bar.fontFamily ? bar.fontFamily : "monospace"

  readonly property string sshHost: String(setting("sshHost", "ssh-ninalyx") || "ssh-ninalyx")
  readonly property string remoteHermesPath: String(setting("remoteHermesPath", "hermes") || "hermes")
  readonly property int openRefreshSec: boundedSetting("openRefreshSec", 15, 5, 300)
  readonly property int backgroundRefreshSec: boundedSetting("backgroundRefreshSec", 60, 15, 3600)
  readonly property string helperPath: String(Qt.resolvedUrl("bin/hermes-kanban-remote")).replace(/^file:\/\//, "")
  readonly property string stateDir: Quickshell.env("HOME") + "/.local/state/omarchy"
  readonly property string statePath: stateDir + "/hermes-kanban.json"

  property bool stateLoaded: false
  property bool selectionInitialized: false
  property var selectedSlugs: []
  property var snapshot: null
  property bool refreshing: false
  property bool stale: false
  property string lastError: ""
  property string stdoutText: ""
  property string stderrText: ""
  property int refreshExitCode: -1
  property bool stdoutFinished: false
  property bool stderrFinished: false
  property bool processFinished: false
  property double nowSeconds: Date.now() / 1000

  readonly property var aggregate: Model.aggregate(snapshot, selectedSlugs)
  readonly property var selectedBoards: Model.selectedBoardModels(snapshot, selectedSlugs)
  readonly property color barIconColor: lastError !== "" && !snapshot ? urgent
    : aggregate.blocked > 0 ? urgent
    : aggregate.review > 0 ? reviewColor
    : aggregate.running > 0 ? runningColor
    : dim
  readonly property string tooltipText: lastError !== ""
    ? "Hermes Kanban · " + lastError
    : aggregate.selected === 0
      ? "Hermes Kanban · choose boards"
      : "Hermes Kanban · " + aggregate.running + " running, " + aggregate.blocked + " blocked"

  function boundedSetting(name, fallback, min, max) {
    var n = parseInt(String(setting(name, fallback)), 10)
    if (!isFinite(n)) n = fallback
    return Math.max(min, Math.min(max, n))
  }

  function statusColor(status) {
    if (status === "blocked") return urgent
    if (status === "review") return reviewColor
    if (status === "running") return runningColor
    if (status === "ready") return readyColor
    if (status === "done") return dim
    return foreground
  }

  function refresh() {
    if (!stateLoaded || refreshing) return
    stdoutText = ""
    stderrText = ""
    refreshExitCode = -1
    stdoutFinished = false
    stderrFinished = false
    processFinished = false
    var command = [helperPath, "snapshot", "--host", sshHost, "--hermes", remoteHermesPath]
    for (var i = 0; i < selectedSlugs.length; i++) command.push("--board", String(selectedSlugs[i]))
    refreshProc.command = command
    refreshing = true
    refreshProc.running = true
  }

  function maybeFinishRefresh() {
    if (processFinished && stdoutFinished && stderrFinished) finishRefresh()
  }

  function finishRefresh() {
    if (refreshExitCode < 0) return
    refreshing = false
    if (refreshExitCode !== 0) {
      stale = snapshot !== null
      var clean = String(stderrText || "").replace(/\s+/g, " ").trim()
      lastError = clean || (refreshExitCode === 10 ? "SSH connection failed" : "Remote Hermes request failed")
      refreshTimer.restart()
      return
    }

    var result = Model.parseSnapshot(stdoutText)
    if (!result.ok) {
      stale = snapshot !== null
      lastError = result.error
      refreshTimer.restart()
      return
    }

    snapshot = result.data
    stale = false
    lastError = ""

    if (!selectionInitialized) {
      selectionInitialized = true
      var initial = Model.currentBoardSlug(snapshot)
      selectedSlugs = initial === "" ? [] : [initial]
      saveState()
      if (initial !== "") Qt.callLater(refresh)
    }
    refreshTimer.restart()
  }

  function loadState(raw) {
    if (stateLoaded) return
    var state = Model.parseState(raw)
    selectionInitialized = state.initialized
    selectedSlugs = state.selectedBoards
    stateLoaded = true
    refresh()
  }

  function saveState() {
    if (!stateLoaded) return
    stateFile.setText(Model.stateJson(selectionInitialized, selectedSlugs))
  }

  function applyBoardSelection(values) {
    var next = []
    for (var i = 0; values && i < values.length; i++) next.push(String(values[i]))
    selectionInitialized = true
    selectedSlugs = next
    saveState()
    refresh()
  }

  function openHermes() {
    Quickshell.execDetached(["gtk-launch", "hermes"])
  }

  function copyTaskId(taskId) {
    if (!taskId) return
    Quickshell.execDetached(["wl-copy", String(taskId)])
  }

  onOpenedChanged: {
    refreshTimer.restart()
    if (opened) {
      refresh()
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  Process {
    id: ensureStateDir
    command: ["mkdir", "-p", root.stateDir]
    onExited: function(exitCode) {
      if (exitCode === 0) stateFile.reload()
      else root.loadState("")
    }
  }

  FileView {
    id: stateFile
    path: root.statePath
    watchChanges: false
    atomicWrites: true
    printErrors: false
    onLoaded: root.loadState(text())
    onLoadFailed: root.loadState("")
  }

  Process {
    id: refreshProc
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.stdoutText = String(text || "")
        root.stdoutFinished = true
        root.maybeFinishRefresh()
      }
    }
    stderr: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        root.stderrText = String(text || "")
        root.stderrFinished = true
        root.maybeFinishRefresh()
      }
    }
    onExited: function(exitCode) {
      root.refreshExitCode = exitCode
      root.processFinished = true
      root.maybeFinishRefresh()
    }
  }

  Timer {
    id: refreshTimer
    interval: (root.opened ? root.openRefreshSec : root.backgroundRefreshSec) * 1000
    repeat: false
    running: root.stateLoaded
    onTriggered: root.refresh()
  }

  Timer {
    interval: 1000
    repeat: true
    running: root.opened
    onTriggered: root.nowSeconds = Date.now() / 1000
  }

  Component.onCompleted: ensureStateDir.running = true

  IpcHandler {
    target: root.ipcTarget
    function open() { root.open() }
    function close() { root.close() }
    function show() { root.open() }
    function hide() { root.close() }
    function toggle() { root.toggle() }
    function refresh() { root.refresh(); return "ok" }
    function status() { return root.tooltipText }
  }

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
            meta: root.refreshing ? "Refreshing remote boards…"
              : root.snapshot ? Model.ageLabel(root.snapshot.fetchedAt, root.nowSeconds)
              : "Waiting for the first snapshot"
            foreground: root.foreground
            fontFamily: root.fontFamily
            iconComponent: Component {
              Text {
                text: "▦"
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
              text: root.sshHost
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
            text: root.snapshot ? "Choose one or more boards to monitor." : "Connect over SSH to discover boards."
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
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.heading
                    font.bold: true
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }

                  Text {
                    text: modelData.missing ? modelData.slug + " · unavailable" : modelData.slug
                    color: modelData.missing ? root.urgent : root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                  }
                }

                Text {
                  text: modelData.counts.running + " running"
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
                    Layout.fillWidth: true
                    implicitHeight: funnelColumn.implicitHeight + Style.space(8)
                    radius: Style.cornerRadius
                    color: Style.normalFillFor(root.foreground, Color.accent)

                    Column {
                      id: funnelColumn
                      anchors.centerIn: parent
                      spacing: Style.space(1)

                      Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: statusCell.modelData === "blocked" && boardSection.modelData.counts[statusCell.modelData] > 0
                          ? "!" : String(boardSection.modelData.counts[statusCell.modelData] || 0)
                        color: root.statusColor(statusCell.modelData)
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.body
                        font.bold: boardSection.modelData.counts[statusCell.modelData] > 0
                      }

                      Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: Model.statusLabel(statusCell.modelData).slice(0, 3).toUpperCase()
                        color: root.dim
                        font.family: root.fontFamily
                        font.pixelSize: Math.max(Style.space(5), Style.font.caption - 2)
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
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          elide: Text.ElideRight
        }

        Text {
          text: taskRow.task.status === "running"
            ? Model.elapsed(taskRow.task.startedAt, root.nowSeconds)
            : (taskRow.task.assignee || "unassigned")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }

      Text {
        visible: taskRow.expanded && taskRow.task.body !== ""
        Layout.fillWidth: true
        text: taskRow.task.body
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
