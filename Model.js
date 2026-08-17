.pragma library

var STATUS_ORDER = ["triage", "todo", "scheduled", "ready", "running", "blocked", "review", "done"]
var DETAIL_STATUSES = ["running", "blocked", "review", "ready"]

function arrayFrom(value) {
  if (!value || typeof value.length !== "number" || typeof value === "string") return []
  var out = []
  for (var i = 0; i < value.length; i++) out.push(value[i])
  return out
}

function stringValue(value, fallback) {
  if (value === undefined || value === null) return fallback || ""
  return String(value)
}

function numberValue(value, fallback) {
  var n = Number(value)
  return isFinite(n) ? n : (fallback || 0)
}

function emptyCounts() {
  var out = {}
  for (var i = 0; i < STATUS_ORDER.length; i++) out[STATUS_ORDER[i]] = 0
  return out
}

function normalizedCounts(raw) {
  var out = emptyCounts()
  var source = raw && typeof raw === "object" ? raw : {}
  for (var i = 0; i < STATUS_ORDER.length; i++) {
    var status = STATUS_ORDER[i]
    out[status] = Math.max(0, Math.floor(numberValue(source[status], 0)))
  }
  return out
}

function normalizeBoard(raw) {
  var source = raw && typeof raw === "object" ? raw : {}
  return {
    slug: stringValue(source.slug),
    name: stringValue(source.name, stringValue(source.slug)),
    description: stringValue(source.description),
    isCurrent: source.is_current === true,
    counts: normalizedCounts(source.counts)
  }
}

function normalizeTask(raw) {
  var source = raw && typeof raw === "object" ? raw : {}
  var status = stringValue(source.status, "todo")
  if (STATUS_ORDER.indexOf(status) === -1) status = "todo"
  return {
    id: stringValue(source.id),
    title: stringValue(source.title, "Untitled task"),
    body: stringValue(source.body),
    assignee: stringValue(source.assignee),
    status: status,
    priority: numberValue(source.priority, 0),
    createdAt: numberValue(source.created_at, 0),
    startedAt: numberValue(source.started_at, 0)
  }
}

function parseSnapshot(raw) {
  var parsed
  try {
    parsed = typeof raw === "string" ? JSON.parse(raw) : raw
  } catch (e) {
    return { ok: false, error: "Hermes returned invalid JSON" }
  }
  if (!parsed || typeof parsed !== "object" || parsed.schemaVersion !== 2)
    return { ok: false, error: "Unsupported Hermes Kanban snapshot" }

  var boards = []
  var rawBoards = arrayFrom(parsed.boards)
  for (var i = 0; i < rawBoards.length; i++) {
    var board = normalizeBoard(rawBoards[i])
    if (board.slug !== "") boards.push(board)
  }

  var tasksByBoard = {}
  var rawTasks = parsed.tasksByBoard && typeof parsed.tasksByBoard === "object"
    ? parsed.tasksByBoard : {}
  for (var slug in rawTasks) {
    var tasks = []
    var sourceTasks = arrayFrom(rawTasks[slug])
    for (var j = 0; j < sourceTasks.length; j++) {
      var task = normalizeTask(sourceTasks[j])
      if (task.id !== "") tasks.push(task)
    }
    tasksByBoard[String(slug)] = tasks
  }

  return {
    ok: true,
    data: {
      schemaVersion: 2,
      fetchedAt: numberValue(parsed.fetchedAt, 0),
      boards: boards,
      tasksByBoard: tasksByBoard
    }
  }
}

function parseState(raw) {
  if (!raw || String(raw).trim() === "")
    return { profiles: {} }
  try {
    var parsed = JSON.parse(String(raw))
    if (!parsed || typeof parsed !== "object") return { profiles: {} }
    if (parsed.version === 1) {
      return { profiles: { legacy: {
        initialized: parsed.initialized === true,
        selectedBoards: normalizedSelection(parsed.selectedBoards)
      } } }
    }
    if (parsed.version !== 2 || !parsed.profiles || typeof parsed.profiles !== "object")
      return { profiles: {} }
    var profiles = {}
    for (var key in parsed.profiles) {
      if (String(key).length <= 300) {
        var profile = parsed.profiles[key]
        profiles[String(key)] = {
          initialized: profile && profile.initialized === true,
          selectedBoards: normalizedSelection(profile ? profile.selectedBoards : [])
        }
      }
    }
    return { profiles: profiles }
  } catch (e) {
    return { profiles: {} }
  }
}

function normalizedSelection(values) {
  var selected = []
  var source = arrayFrom(values)
  var seen = {}
  for (var i = 0; i < source.length && selected.length < 20; i++) {
    var slug = String(source[i] || "")
    if (/^[a-z0-9][a-z0-9-]{0,63}$/.test(slug) && !seen[slug]) {
      selected.push(slug)
      seen[slug] = true
    }
  }
  return selected
}

function stateJson(profiles) {
  return JSON.stringify({
    version: 2,
    profiles: profiles && typeof profiles === "object" ? profiles : {}
  }, null, 2) + "\n"
}

function currentBoardSlug(snapshot) {
  if (!snapshot) return ""
  var boards = arrayFrom(snapshot.boards)
  for (var i = 0; i < boards.length; i++) if (boards[i].isCurrent) return boards[i].slug
  return boards.length > 0 ? boards[0].slug : ""
}

function boardOptions(snapshot) {
  if (!snapshot) return []
  var boards = arrayFrom(snapshot.boards)
  var out = []
  for (var i = 0; i < boards.length; i++) {
    var board = boards[i]
    out.push({
      value: board.slug,
      label: board.name || board.slug,
      description: board.isCurrent ? board.slug + " · current" : board.slug
    })
  }
  return out
}

function tasksFor(snapshot, slug) {
  if (!snapshot || !snapshot.tasksByBoard) return []
  return arrayFrom(snapshot.tasksByBoard[String(slug)])
}

function countsForTasks(tasks) {
  var out = emptyCounts()
  var source = arrayFrom(tasks)
  for (var i = 0; i < source.length; i++) {
    var status = source[i].status
    if (out[status] !== undefined) out[status]++
  }
  return out
}

function selectedBoardModels(snapshot, selectedSlugs) {
  var out = []
  var selected = arrayFrom(selectedSlugs)
  var boards = snapshot ? arrayFrom(snapshot.boards) : []
  var bySlug = {}
  for (var i = 0; i < boards.length; i++) bySlug[boards[i].slug] = boards[i]
  for (var j = 0; j < selected.length; j++) {
    var slug = String(selected[j])
    var meta = bySlug[slug]
    var tasks = tasksFor(snapshot, slug)
    out.push({
      slug: slug,
      name: meta ? (meta.name || slug) : slug,
      description: meta ? meta.description : "",
      missing: !meta,
      tasks: tasks,
      counts: meta ? meta.counts : countsForTasks(tasks)
    })
  }
  return out
}

function aggregate(snapshot, selectedSlugs) {
  var counts = emptyCounts()
  var boards = selectedBoardModels(snapshot, selectedSlugs)
  var missing = 0
  for (var i = 0; i < boards.length; i++) {
    if (boards[i].missing) missing++
    for (var j = 0; j < STATUS_ORDER.length; j++) {
      var status = STATUS_ORDER[j]
      counts[status] += numberValue(boards[i].counts[status], 0)
    }
  }
  return {
    counts: counts,
    running: counts.running,
    blocked: counts.blocked,
    review: counts.review,
    attention: counts.blocked + counts.review,
    selected: arrayFrom(selectedSlugs).length,
    missing: missing
  }
}

function tasksForStatus(tasks, status) {
  var out = []
  var source = arrayFrom(tasks)
  for (var i = 0; i < source.length; i++) if (source[i].status === status) out.push(source[i])
  out.sort(function(a, b) {
    if (a.priority !== b.priority) return b.priority - a.priority
    if (a.createdAt !== b.createdAt) return a.createdAt - b.createdAt
    return a.title.localeCompare(b.title)
  })
  return out
}

function detailTaskCount(tasks) {
  var total = 0
  for (var i = 0; i < DETAIL_STATUSES.length; i++) total += tasksForStatus(tasks, DETAIL_STATUSES[i]).length
  return total
}

function statusLabel(status) {
  var labels = {
    triage: "Triage",
    todo: "Todo",
    scheduled: "Scheduled",
    ready: "Ready",
    running: "Running",
    blocked: "Blocked",
    review: "Review",
    done: "Done"
  }
  return labels[status] || status
}

function statusIcon(status) {
  var icons = {
    triage: "inbox",
    todo: "list-check",
    scheduled: "calendar-time",
    ready: "player-play",
    running: "loader-2",
    blocked: "alert-octagon",
    review: "eye-check",
    done: "circle-check"
  }
  return icons[status] || "list-check"
}

function colorChannelLuminance(value) {
  var channel = Number(value)
  if (!isFinite(channel)) return 0
  return channel <= 0.04045
    ? channel / 12.92
    : Math.pow((channel + 0.055) / 1.055, 2.4)
}

function colorLuminance(color) {
  return 0.2126 * colorChannelLuminance(color.r)
    + 0.7152 * colorChannelLuminance(color.g)
    + 0.0722 * colorChannelLuminance(color.b)
}

function contrastRatio(first, second) {
  var firstLuminance = colorLuminance(first)
  var secondLuminance = colorLuminance(second)
  var lighter = Math.max(firstLuminance, secondLuminance)
  var darker = Math.min(firstLuminance, secondLuminance)
  return (lighter + 0.05) / (darker + 0.05)
}

function higherContrastColor(first, second, background) {
  return contrastRatio(first, background) >= contrastRatio(second, background) ? first : second
}

function statusGlyph(status) {
  var glyphs = {
    triage: "◇",
    todo: "○",
    scheduled: "◷",
    ready: "▷",
    running: "●",
    blocked: "!",
    review: "◉",
    done: "✓"
  }
  return glyphs[status] || "·"
}

function elapsed(startedAt, nowSeconds) {
  var start = numberValue(startedAt, 0)
  var now = numberValue(nowSeconds, Date.now() / 1000)
  if (!(start > 0) || now < start) return ""
  var seconds = Math.floor(now - start)
  var minutes = Math.floor(seconds / 60)
  var hours = Math.floor(minutes / 60)
  var days = Math.floor(hours / 24)
  if (days > 0) return days + "d " + (hours % 24) + "h"
  if (hours > 0) return hours + "h " + (minutes % 60) + "m"
  if (minutes > 0) return minutes + "m"
  return Math.max(1, seconds) + "s"
}

function ageLabel(timestamp, nowSeconds) {
  var age = elapsed(timestamp, nowSeconds)
  return age === "" ? "Never updated" : age + " ago"
}
