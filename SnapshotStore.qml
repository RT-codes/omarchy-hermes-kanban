pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

QtObject {
  id: root

  property string connectionMode: "local"
  property string hermesPath: "hermes"
  property string sshHost: ""
  property bool includeTaskBodies: false
  property int openRefreshSec: 15
  property int backgroundRefreshSec: 120
  property bool panelOpen: false

  property bool stateLoaded: false
  property var profiles: ({})
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

  readonly property string helperPath: String(Qt.resolvedUrl("bin/hermes-kanban-snapshot")).replace(/^file:\/\//, "")
  readonly property string stateDir: Quickshell.env("HOME") + "/.local/state/omarchy"
  readonly property string statePath: stateDir + "/hermes-kanban.json"
  readonly property string profileKey: connectionMode === "remote" ? "remote:" + sshHost : "local"

  function bounded(value, fallback, minimum, maximum) {
    var parsed = parseInt(String(value), 10)
    if (!isFinite(parsed)) parsed = fallback
    return Math.max(minimum, Math.min(maximum, parsed))
  }

  function configure(mode, executable, host, bodies, openInterval, backgroundInterval) {
    var nextMode = String(mode || "Local").toLowerCase() === "remote" ? "remote" : "local"
    var nextPath = String(executable || "hermes")
    var nextHost = String(host || "")
    var changed = nextMode !== connectionMode || nextPath !== hermesPath || nextHost !== sshHost
      || (bodies === true) !== includeTaskBodies
    var endpointChanged = nextMode !== connectionMode || nextHost !== sshHost
    connectionMode = nextMode
    hermesPath = nextPath
    sshHost = nextHost
    includeTaskBodies = bodies === true
    openRefreshSec = bounded(openInterval, 15, 5, 300)
    backgroundRefreshSec = bounded(backgroundInterval, 120, 30, 3600)
    if (stateLoaded && endpointChanged) loadActiveProfile()
    if (stateLoaded && changed) refresh()
  }

  function loadActiveProfile() {
    var profile = profiles[profileKey]
    if (!profile && profiles.legacy) {
      var migrated = JSON.parse(JSON.stringify(profiles || {}))
      migrated[profileKey] = migrated.legacy
      delete migrated.legacy
      profiles = migrated
      profile = profiles[profileKey]
      stateFile.setText(Model.stateJson(profiles))
    }
    selectionInitialized = profile ? profile.initialized === true : false
    selectedSlugs = profile ? Model.normalizedSelection(profile.selectedBoards) : []
  }

  function persistProfile() {
    if (!stateLoaded) return
    var next = JSON.parse(JSON.stringify(profiles || {}))
    next[profileKey] = {
      initialized: selectionInitialized === true,
      selectedBoards: Model.normalizedSelection(selectedSlugs)
    }
    profiles = next
    stateFile.setText(Model.stateJson(next))
  }

  function applyBoardSelection(values) {
    selectionInitialized = true
    selectedSlugs = Model.normalizedSelection(values)
    persistProfile()
    refresh()
  }

  function setPanelOpen(value) {
    panelOpen = value === true
    refreshTimer.restart()
    if (panelOpen) refresh()
  }

  function refresh() {
    if (!stateLoaded || refreshing) return
    if (connectionMode === "remote" && sshHost.trim() === "") {
      lastError = "Choose an SSH host or alias in widget settings"
      return
    }
    stdoutText = ""
    stderrText = ""
    refreshExitCode = -1
    stdoutFinished = false
    stderrFinished = false
    processFinished = false
    var command = [helperPath, "snapshot", "--mode", connectionMode, "--hermes", hermesPath]
    if (connectionMode === "remote") command.push("--host", sshHost)
    if (includeTaskBodies) command.push("--include-task-bodies")
    for (var i = 0; i < selectedSlugs.length; i++) command.push("--board", String(selectedSlugs[i]))
    refreshProc.command = command
    refreshing = true
    refreshProc.running = true
  }

  function safeError(raw, exitCode) {
    var match = String(raw || "").match(/HERMES_KANBAN_ERROR:([a-z-]+):([^\r\n]{1,200})/)
    var code = match ? match[1] : ""
    var messages = {
      "configuration": "Check the Hermes connection settings",
      "hermes-not-found": "Hermes executable was not found",
      "hermes-timeout": "Hermes did not respond in time",
      "hermes-failed": "Hermes could not read the Kanban boards",
      "invalid-response": "Hermes returned an invalid response",
      "response-too-large": "Hermes returned more data than the safety limit",
      "unknown-board": "A selected board is no longer available",
      "ssh-not-found": "OpenSSH is not installed",
      "ssh-timeout": "The SSH connection timed out",
      "ssh-failed": "SSH authentication, host key, or connection failed",
      "remote-failed": "The remote snapshot command failed"
    }
    return messages[code] || (exitCode === 10 ? messages["ssh-failed"] : "Hermes snapshot failed")
  }

  function maybeFinishRefresh() {
    if (!processFinished || !stdoutFinished || !stderrFinished) return
    refreshing = false
    if (refreshExitCode !== 0) {
      stale = snapshot !== null
      lastError = safeError(stderrText, refreshExitCode)
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
      persistProfile()
      if (initial !== "") Qt.callLater(refresh)
    }
    refreshTimer.restart()
  }

  function loadState(raw) {
    if (stateLoaded) return
    profiles = Model.parseState(raw).profiles
    stateLoaded = true
    loadActiveProfile()
    refresh()
  }

  Component.onCompleted: ensureStateDir.running = true

  property Process ensureStateDir: Process {
    command: ["mkdir", "-p", root.stateDir]
    onExited: function(exitCode) {
      if (exitCode === 0) stateFile.reload()
      else root.loadState("")
    }
  }

  property FileView stateFile: FileView {
    path: root.statePath
    watchChanges: false
    atomicWrites: true
    printErrors: false
    onLoaded: root.loadState(text())
    onLoadFailed: root.loadState("")
  }

  property Process refreshProc: Process {
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

  property Timer refreshTimer: Timer {
    interval: (root.panelOpen ? root.openRefreshSec : root.backgroundRefreshSec) * 1000
    repeat: false
    running: root.stateLoaded
    onTriggered: root.refresh()
  }

  property Timer clockTimer: Timer {
    interval: 1000
    repeat: true
    running: root.panelOpen
    onTriggered: root.nowSeconds = Date.now() / 1000
  }
}
