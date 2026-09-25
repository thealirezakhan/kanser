"use client";

import { useEffect, useReducer, useState } from "react";
import { ApiError, api, getToken, wsUrl } from "./api";
import { applyEvent, type RunEvent } from "./runEvents";

interface RunSnap {
  status: string;
  events: RunEvent[];
}

export function useRunStream(runId: string) {
  const [state, dispatch] = useReducer(applyEvent, { events: [], done: false });
  const [status, setStatus] = useState("queued");

  useEffect(() => {
    let stopped = false;
    let ws: WebSocket | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;

    const stop = () => {
      stopped = true;
      if (poll) {
        clearInterval(poll);
        poll = null;
      }
    };

    const pollOnce = async () => {
      if (stopped) return;
      try {
        const run = await api<RunSnap>(`/api/runs/${runId}`);
        if (stopped) return;
        setStatus(run.status);
        run.events.forEach((ev) => dispatch(ev));
        if (run.status === "completed" || run.status === "failed") stop();
      } catch (err) {
        if (err instanceof ApiError && err.status === 404) {
          setStatus("expired"); // run lost (server restart) — stop spamming
          stop();
        }
        // transient 429/network errors: keep polling
      }
    };

    const token = getToken();
    if (token) {
      try {
        ws = new WebSocket(wsUrl(`/ws/runs/${runId}?token=${token}`));
        ws.onmessage = (msg) => {
          const ev = JSON.parse(msg.data) as RunEvent;
          setStatus(
            ev.type === "run_failed"
              ? "failed"
              : ev.type === "run_completed"
                ? "completed"
                : "running",
          );
          dispatch(ev);
          if (ev.type === "run_completed" || ev.type === "run_failed") stop();
        };
        ws.onclose = () => {
          if (!stopped && poll === null) poll = setInterval(pollOnce, 1000);
        };
      } catch {
        poll = setInterval(pollOnce, 1000);
      }
    } else {
      poll = setInterval(pollOnce, 1000);
    }
    void pollOnce();

    return () => {
      stop();
      if (ws) ws.close();
    };
  }, [runId]);

  return { events: state.events, done: state.done, status };
}
