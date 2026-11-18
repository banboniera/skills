import { describe, expect, test } from "bun:test"
import { SubagentEdits } from "./index"

const tested = () => true
const TEST = "cargo nextest run -p inventory"

describe("subagent edits", () => {
  test("a subagent's passing check clears the edits it made before starting", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.started("worker-a:1", TEST, "worker-a")
    edits.finished("worker-a:1", true, tested)
    expect(edits.paths()).toEqual([])
  })

  test("an edit made after the check started stays pending", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.started("worker-a:1", TEST, "worker-a")
    edits.record(["src/a.rs"], "worker-a")
    edits.finished("worker-a:1", true, tested)
    expect(edits.paths()).toEqual(["src/a.rs"])
  })

  test("a failing check clears nothing", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.started("worker-a:1", TEST, "worker-a")
    edits.finished("worker-a:1", false, tested)
    expect(edits.paths()).toEqual(["src/a.rs"])
  })

  test("a subagent's check does not cover another subagent's edits", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.record(["src/b.rs"], "worker-b")
    edits.started("worker-a:1", TEST, "worker-a")
    edits.finished("worker-a:1", true, tested)
    expect(edits.paths()).toEqual(["src/b.rs"])
  })

  test("a main-agent check covers every subagent's edits", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.record(["src/b.rs"], "worker-b")
    edits.started("main:1", TEST)
    edits.finished("main:1", true, tested)
    expect(edits.paths()).toEqual([])
  })

  test("committing an unverified edit does not clear it", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.started("main:1", "git commit -am wip")
    edits.finished("main:1", true, tested)
    expect(edits.paths()).toEqual(["src/a.rs"])
  })

  test("a backgrounded check clears its edits when its job completes", () => {
    const edits = new SubagentEdits()
    edits.record(["src/a.rs"], "worker-a")
    edits.started("worker-a:1", TEST, "worker-a")
    edits.moved("worker-a:1", "bg_7")
    edits.finished("worker-a:1", true, tested)
    expect(edits.paths()).toEqual(["src/a.rs"])
    edits.finished("bg_7", true, tested)
    expect(edits.paths()).toEqual([])
  })
})
