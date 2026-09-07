import QtQuick
import QtTest
import "../Model.js" as Model

TestCase {
  name: "HermesKanbanModel"

  function fixture() {
    return JSON.stringify({
      schemaVersion: 3,
      fetchedAt: 1000,
      boards: [
        { slug: "alpha", name: "Alpha", is_current: true, counts: { running: 1, blocked: 1, done: 2 } },
        { slug: "beta", name: "Beta", counts: { review: 1 } }
      ],
      tasksByBoard: {
        alpha: [
          { id: "t_run", title: "Run", status: "running", priority: 1, started_at: 900, tags: ["system"] },
          { id: "t_block", title: "Block", status: "blocked", priority: 3, blocked_reason: "needs input", dependencies: ["t_plan"] }
        ],
        beta: [{ id: "t_review", title: "Review", status: "review", priority: 2 }]
      },
      cronJobs: [
        {
          id: "job_1",
          name: "Hardware watch",
          prompt: "Check listings",
          schedule: "every 2h",
          state: "scheduled",
          enabled: true,
          next_run_at: "2026-09-07T23:00:00Z",
          skills: ["hardware-watch"]
        }
      ]
    })
  }

  function test_parse_and_aggregate() {
    var parsed = Model.parseSnapshot(fixture())
    verify(parsed.ok)
    compare(Model.currentBoardSlug(parsed.data), "alpha")
    var aggregate = Model.aggregate(parsed.data, ["alpha", "beta"])
    compare(aggregate.running, 1)
    compare(aggregate.blocked, 1)
    compare(aggregate.review, 1)
    compare(aggregate.attention, 2)
    compare(Model.cronJobs(parsed.data).length, 1)
    compare(Model.cronJobs(parsed.data)[0].name, "Hardware watch")
  }

  function test_invalid_snapshot() {
    verify(!Model.parseSnapshot("not-json").ok)
    verify(!Model.parseSnapshot('{"schemaVersion":1}').ok)
  }

  function test_state_round_trip_and_dedupe() {
    var legacy = Model.parseState('{"version":1,"initialized":true,"selectedBoards":["alpha","alpha","beta"]}')
    verify(legacy.profiles.legacy.initialized)
    compare(legacy.profiles.legacy.selectedBoards.length, 2)
    var profiles = {
      local: legacy.profiles.legacy,
      "remote:workstation": { initialized: true, selectedBoards: ["beta"] }
    }
    var again = Model.parseState(Model.stateJson(profiles))
    compare(again.profiles.local.selectedBoards.length, 2)
    compare(again.profiles["remote:workstation"].selectedBoards[0], "beta")
  }

  function test_missing_board_is_preserved() {
    var parsed = Model.parseSnapshot(fixture()).data
    var boards = Model.selectedBoardModels(parsed, ["gone"])
    compare(boards.length, 1)
    verify(boards[0].missing)
    compare(boards[0].slug, "gone")
  }

  function test_task_sort_and_elapsed() {
    var tasks = [
      Model.normalizeTask({ id: "a", title: "A", status: "ready", priority: 1, created_at: 20 }),
      Model.normalizeTask({ id: "b", title: "B", status: "ready", priority: 3, created_at: 30 })
    ]
    var sorted = Model.tasksForStatus(tasks, "ready")
    compare(sorted[0].id, "b")
    compare(Model.elapsed(900, 1000), "1m")
  }

  function test_richer_task_metadata() {
    var parsed = Model.parseSnapshot(fixture()).data
    var blocked = Model.tasksForStatus(Model.tasksFor(parsed, "alpha"), "blocked")[0]
    compare(blocked.blockedReason, "needs input")
    compare(blocked.dependencies[0], "t_plan")
  }

  function test_cron_helpers() {
    var parsed = Model.parseSnapshot(fixture()).data
    var job = Model.cronJobs(parsed)[0]
    compare(Model.cronStateLabel(job), "scheduled")
    compare(Model.cronGlyph(job), "◷")
    verify(Model.cronMeta(job).indexOf("every 2h") >= 0)
  }

  function test_board_metadata_counts_are_not_replaced_by_filtered_tasks() {
    var parsed = Model.parseSnapshot(fixture()).data
    var board = Model.selectedBoardModels(parsed, ["alpha"])[0]
    compare(board.counts.running, 1)
    compare(board.counts.done, 2)
  }

  function test_status_icon_mapping() {
    compare(Model.statusIcon("triage"), "inbox")
    compare(Model.statusIcon("todo"), "list-check")
    compare(Model.statusIcon("scheduled"), "calendar-time")
    compare(Model.statusIcon("ready"), "player-play")
    compare(Model.statusIcon("running"), "loader-2")
    compare(Model.statusIcon("blocked"), "alert-octagon")
    compare(Model.statusIcon("review"), "eye-check")
    compare(Model.statusIcon("done"), "circle-check")
    compare(Model.statusIcon("unknown"), "list-check")
  }

  function test_blocked_color_contrast() {
    var brightRed = Qt.color("#ff6b6b")
    var darkRed = Qt.color("#b42318")
    var darkSurface = Qt.color("#0b0c16")
    var lightSurface = Qt.color("#f8fafc")

    compare(Model.higherContrastColor(brightRed, darkRed, darkSurface), brightRed)
    verify(Model.contrastRatio(brightRed, darkSurface) >= 4.5)
    compare(Model.higherContrastColor(brightRed, darkRed, lightSurface), darkRed)
    verify(Model.contrastRatio(darkRed, lightSurface) >= 4.5)
  }
}
