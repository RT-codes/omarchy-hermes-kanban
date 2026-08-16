import QtQuick
import QtTest
import "../Model.js" as Model

TestCase {
  name: "HermesKanbanModel"

  function fixture() {
    return JSON.stringify({
      schemaVersion: 1,
      fetchedAt: 1000,
      boards: [
        { slug: "alpha", name: "Alpha", is_current: true, counts: { running: 1, blocked: 1, done: 2 } },
        { slug: "beta", name: "Beta", counts: { review: 1 } }
      ],
      tasksByBoard: {
        alpha: [
          { id: "t_run", title: "Run", status: "running", priority: 1, started_at: 900 },
          { id: "t_block", title: "Block", status: "blocked", priority: 3 }
        ],
        beta: [{ id: "t_review", title: "Review", status: "review", priority: 2 }]
      }
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
  }

  function test_invalid_snapshot() {
    verify(!Model.parseSnapshot("not-json").ok)
    verify(!Model.parseSnapshot('{"schemaVersion":2}').ok)
  }

  function test_state_round_trip_and_dedupe() {
    var state = Model.parseState('{"version":1,"initialized":true,"selectedBoards":["alpha","alpha","beta"]}')
    verify(state.initialized)
    compare(state.selectedBoards.length, 2)
    compare(state.selectedBoards[1], "beta")
    var again = Model.parseState(Model.stateJson(true, state.selectedBoards))
    compare(again.selectedBoards.length, 2)
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
}
