import { describe, expect, it } from "vitest";
import { applyEvent, type RunState } from "./runEvents";

const start: RunState = { events: [], done: false };

describe("applyEvent", () => {
  it("appends events in order", () => {
    let s = applyEvent(start, { type: "agent_step", node: "radiology" });
    s = applyEvent(s, { type: "evidence" });
    expect(s.events.map((e) => e.type)).toEqual(["agent_step", "evidence"]);
    expect(s.done).toBe(false);
  });

  it("marks run_completed as terminal and ignores later events", () => {
    let s = applyEvent(start, { type: "run_completed" });
    expect(s.done).toBe(true);
    s = applyEvent(s, { type: "agent_step" });
    expect(s.events).toHaveLength(1);
  });

  it("treats run_failed as terminal", () => {
    const s = applyEvent(start, { type: "run_failed" });
    expect(s.done).toBe(true);
  });

  it("does not mutate previous state", () => {
    const s1 = applyEvent(start, { type: "a" });
    applyEvent(s1, { type: "b" });
    expect(start.events).toHaveLength(0);
    expect(s1.events).toHaveLength(1);
  });

  it("drops duplicate or stale seq (poll + ws overlap)", () => {
    let s = applyEvent(start, { type: "agent_step", seq: 0 });
    s = applyEvent(s, { type: "evidence", seq: 1 });
    s = applyEvent(s, { type: "agent_step", seq: 0 });
    expect(s.events).toHaveLength(2);
    s = applyEvent(s, { type: "run_completed", seq: 2 });
    expect(s.done).toBe(true);
    s = applyEvent(s, { type: "agent_step", seq: 3 });
    expect(s.events).toHaveLength(3);
  });
});
