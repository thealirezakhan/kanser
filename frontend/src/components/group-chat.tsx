"use client";
import { useEffect, useRef, useState } from "react";
import { api, getToken, wsUrl } from "@/lib/api";

interface ChatTurn {
  agent: string;
  name: string;
  text: string;
  tokens_in: number;
  tokens_out: number;
}

interface ChatMsg {
  key: string;
  kind: "user" | "agent" | "system";
  agent?: string;
  name?: string;
  text: string;
  tokensOut?: number;
}

const AGENT_STYLE: Record<string, string> = {
  radiology: "bg-sky-50 text-sky-800 border-sky-200",
  pathology: "bg-violet-50 text-violet-800 border-violet-200",
  genomics: "bg-amber-50 text-amber-800 border-amber-200",
  clinical: "bg-emerald-50 text-emerald-800 border-emerald-200",
};
const MENTIONS = ["@all", "@radiologist", "@pathologist", "@genomicist", "@clinician"];

function initial(name: string): string {
  return name
    .replace(/\(.*\)/, "")
    .trim()
    .split(/\s+/)
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

export function GroupChat({ caseId }: { caseId: string }) {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [mode, setMode] = useState<"connecting" | "ws" | "rest">("connecting");
  const [tokenTotals, setTokenTotals] = useState<Record<string, number>>({});
  const wsRef = useRef<WebSocket | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    const ws = new WebSocket(wsUrl(`/ws/cases/${caseId}/chat`));
    wsRef.current = ws;
    ws.onopen = () => {
      // token rides first message, never the URL (keeps access logs clean)
      ws.send(JSON.stringify({ type: "auth", token }));
      setMode("ws");
    };
    ws.onmessage = (event) => {
      const ev = JSON.parse(event.data) as {
        type: string;
        agent?: string;
        name?: string;
        text?: string;
        tokens_out?: number;
        tokens?: Record<string, { in: number; out: number }>;
      };
      if (ev.type === "chat_turn" && ev.agent) {
        setMessages((prev) => [
          ...prev,
          {
            key: `t-${seq.current++}`,
            kind: "agent",
            agent: ev.agent,
            name: ev.name,
            text: ev.text ?? "",
            tokensOut: ev.tokens_out,
          },
        ]);
      } else if (ev.type === "chat_done") {
        setSending(false);
        if (ev.tokens) {
          setTokenTotals((prev) => {
            const next = { ...prev };
            for (const [agent, usage] of Object.entries(ev.tokens!)) {
              next[agent] = (next[agent] ?? 0) + usage.out;
            }
            return next;
          });
        }
      }
    };
    ws.onclose = () => {
      setMode((m) => (m === "ws" ? "rest" : "rest"));
    };
    ws.onerror = () => setMode("rest");
    return () => {
      ws.onclose = null;
      ws.close();
      wsRef.current = null;
    };
  }, [caseId]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  function addTurns(turns: ChatTurn[]) {
    setMessages((prev) => [
      ...prev,
      ...turns.map((t) => ({
        key: `t-${seq.current++}`,
        kind: "agent" as const,
        agent: t.agent,
        name: t.name,
        text: t.text,
        tokensOut: t.tokens_out,
      })),
    ]);
    setTokenTotals((prev) => {
      const next = { ...prev };
      for (const t of turns) next[t.agent] = (next[t.agent] ?? 0) + t.tokens_out;
      return next;
    });
  }

  async function send() {
    const text = input.trim();
    if (!text || sending) return;
    setMessages((prev) => [...prev, { key: `u-${seq.current++}`, kind: "user", text }]);
    setInput("");
    setSending(true);
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ message: text }));
      return;
    }
    try {
      const data = await api<{ turns: ChatTurn[]; tokens: Record<string, { in: number; out: number }> }>(
        `/api/cases/${caseId}/chat`,
        { method: "POST", body: JSON.stringify({ message: text }) },
      );
      addTurns(data.turns);
      setTokenTotals((prev) => {
        const next = { ...prev };
        for (const [agent, usage] of Object.entries(data.tokens)) {
          next[agent] = (next[agent] ?? 0) + usage.out;
        }
        return next;
      });
      setMode("rest");
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          key: `e-${seq.current++}`,
          kind: "system",
          text: err instanceof Error ? err.message : "Message failed",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-xl border border-outline-variant bg-surface-container-lowest shadow-sm">
      <header className="flex items-center justify-between border-b border-outline-variant px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-primary">
            forum
          </span>
          <h2 className="text-sm font-bold uppercase tracking-wider text-on-surface">
            Board Group Chat
          </h2>
          <span className="flex items-center gap-1.5 rounded-full border border-outline-variant bg-surface-container px-2 py-0.5 font-mono text-[10px] text-outline">
            <span
              className={`h-1.5 w-1.5 rounded-full ${mode === "ws" ? "bg-emerald-500" : "bg-amber-500"}`}
            />
            {mode === "ws" ? "live" : "rest fallback"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          {Object.keys(tokenTotals).map((agent) => (
            <span
              key={agent}
              className="rounded bg-surface-container px-1.5 py-0.5 font-mono text-[10px] text-outline"
              title={`tokens used by ${agent}`}
            >
              {agent.slice(0, 4)} {tokenTotals[agent]}
            </span>
          ))}
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-outline-variant p-6 text-center">
            <span className="material-symbols-outlined text-[28px] text-outline">
              groups_3
            </span>
            <p className="text-sm font-semibold text-on-surface-variant">
              Ask the tumor board
            </p>
            <p className="font-mono text-xs text-outline">
              @radiologist · @pathologist · @genomicist · @clinician · @all
            </p>
          </div>
        )}
        {messages.map((m) =>
          m.kind === "user" ? (
            <div key={m.key} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-sm border border-primary/30 bg-primary/10 px-4 py-2.5 text-sm text-on-surface">
                {m.text}
              </div>
            </div>
          ) : m.kind === "system" ? (
            <div
              key={m.key}
              className="rounded-lg border border-rose-200 bg-error-container px-3 py-2 font-mono text-xs text-on-error-container"
            >
              {m.text}
            </div>
          ) : (
            <div key={m.key} className="flex gap-2.5">
              <div
                className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${AGENT_STYLE[m.agent ?? "clinical"]}`}
              >
                {initial(m.name ?? m.agent ?? "?")}
              </div>
              <div className="flex min-w-0 flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-on-surface">{m.name}</span>
                  {m.tokensOut !== undefined && (
                    <span className="font-mono text-[10px] text-outline">
                      {m.tokensOut} tok
                    </span>
                  )}
                </div>
                <div
                  className={`max-w-[85%] rounded-2xl rounded-tl-sm border px-4 py-2.5 text-sm leading-relaxed text-on-surface ${AGENT_STYLE[m.agent ?? "clinical"]}`}
                >
                  {m.text}
                </div>
              </div>
            </div>
          ),
        )}
        {sending && (
          <div className="flex items-center gap-2 pl-10 font-mono text-xs text-outline">
            <span className="flex gap-1">
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:120ms]" />
              <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary [animation-delay:240ms]" />
            </span>
            board is responding turn by turn…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <footer className="border-t border-outline-variant p-3">
        <div className="mb-2 flex flex-wrap gap-1.5">
          {MENTIONS.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() =>
                setInput((prev) => (prev.trim() ? `${prev.trim()} ${m} ` : `${m} `))
              }
              className="rounded-full border border-outline-variant bg-surface-container px-2.5 py-1 font-mono text-[11px] text-on-surface-variant transition-colors hover:border-primary hover:text-primary"
            >
              {m}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            placeholder="@all give me your reports…"
            className="h-10 flex-1 rounded-lg border border-outline-variant bg-white px-3 text-sm text-on-surface placeholder:text-outline focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20"
          />
          <button
            onClick={() => void send()}
            disabled={sending || !input.trim()}
            className="flex h-10 items-center gap-1.5 rounded-lg bg-primary-container px-4 text-xs font-bold uppercase tracking-wider text-white transition hover:opacity-90 disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[16px]">send</span>
            Send
          </button>
        </div>
      </footer>
    </section>
  );
}
