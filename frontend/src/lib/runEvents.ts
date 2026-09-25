export interface RunEvent {
  type: string;
  seq?: number;
  node?: string;
  status?: string;
  [key: string]: unknown;
}

export interface RunState {
  events: RunEvent[];
  done: boolean;
}

const TERMINAL = new Set(["run_completed", "run_failed"]);

export function applyEvent(state: RunState, ev: RunEvent): RunState {
  if (state.done) return state;
  if (typeof ev.seq === "number") {
    const last = state.events[state.events.length - 1];
    if (typeof last?.seq === "number" && ev.seq <= last.seq) return state;
  }
  return {
    events: [...state.events, ev],
    done: state.done || TERMINAL.has(ev.type),
  };
}

export function isTerminal(ev: RunEvent): boolean {
  return TERMINAL.has(ev.type);
}
