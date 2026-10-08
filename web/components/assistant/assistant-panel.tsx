"use client";

import { FormEvent, KeyboardEvent, useCallback, useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import {
  ArrowUp,
  Check,
  CircleAlert,
  Copy,
  Loader2,
  Maximize2,
  Minimize2,
  RotateCcw,
  Sparkles,
  Square,
  SquarePen,
  X,
} from "lucide-react";

import { AnswerText } from "@/components/assistant/answer-text";
import { ResultBlock } from "@/components/assistant/blocks";
import { copyText } from "@/components/candidate-mail";
import {
  ASK_EVENT,
  ASSISTANT_STORE,
  type AssistantMessage,
  historyForServer,
  type Message,
  pageContext,
  type StreamEvent,
  streamAssistant,
  suggestions,
} from "@/lib/assistant";

export type PanelMode = "closed" | "open" | "wide";

const KEEP_MESSAGES = 30;

function load(): Message[] {
  try {
    const raw = sessionStorage.getItem(ASSISTANT_STORE);
    const parsed = raw ? (JSON.parse(raw) as Message[]) : [];
    return parsed.map((message) =>
      message.role === "assistant" && message.status === "streaming" ? { ...message, status: "stopped" } : message,
    );
  } catch {
    return [];
  }
}

function save(messages: Message[]) {
  try {
    sessionStorage.setItem(ASSISTANT_STORE, JSON.stringify(messages.slice(-KEEP_MESSAGES)));
  } catch {
    // Storage full or blocked: the chat still works for this page view.
  }
}

function Steps({ message }: { message: AssistantMessage }) {
  if (!message.steps.length) return null;
  return (
    <ol className="space-y-1">
      {message.steps.map((step) => (
        <li key={step.id} className="flex items-start gap-2 text-xs text-ink/60">
          <span className="mt-0.5 shrink-0">
            {step.ok === undefined ? (
              <Loader2 className="size-3.5 animate-spin text-pine" />
            ) : step.ok ? (
              <Check className="size-3.5 text-emerald-600" />
            ) : (
              <CircleAlert className="size-3.5 text-amber-600" />
            )}
          </span>
          <span className="min-w-0">
            <span className="font-medium text-ink/70">{step.label}</span>
            {step.summary ? <span className="text-ink/50"> · {step.summary}</span> : null}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Thinking() {
  return (
    <div className="flex items-center gap-1.5 py-1" aria-label="Thinking">
      {[0, 1, 2].map((dot) => (
        <span key={dot} className="size-1.5 animate-bounce rounded-full bg-pine/60" style={{ animationDelay: `${dot * 120}ms` }} />
      ))}
    </div>
  );
}

export function AssistantPanel({ mode, onMode }: { mode: PanelMode; onMode: (mode: PanelMode) => void }) {
  const pathname = usePathname();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [model, setModel] = useState("");
  const [copied, setCopied] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const stickRef = useRef(true);
  const loaded = useRef(false);
  const open = mode !== "closed";

  useEffect(() => {
    setMessages(load());
    loaded.current = true;
  }, []);

  useEffect(() => {
    if (loaded.current && !busy) save(messages);
  }, [messages, busy]);

  useEffect(() => {
    if (!open || model) return;
    fetch("/api/admin/assistant/info")
      .then((response) => (response.ok ? response.json() : null))
      .then((info) => info && setModel(info.model))
      .catch(() => undefined);
  }, [open, model]);

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 50);
  }, [open]);

  useEffect(() => {
    const node = scrollRef.current;
    if (node && stickRef.current) node.scrollTop = node.scrollHeight;
  }, [messages]);

  const context = pageContext(pathname, typeof window === "undefined" ? "" : window.location.search);

  const send = useCallback(
    async (text: string, base?: Message[]) => {
      const question = text.trim();
      if (!question || busy) return;
      const prior = base ?? messages;
      const user: Message = { role: "user", content: question };
      const reply: AssistantMessage = { role: "assistant", content: "", steps: [], blocks: [], status: "streaming" };
      const next = [...prior, user];
      setMessages([...next, reply]);
      setInput("");
      setBusy(true);
      stickRef.current = true;
      const controller = new AbortController();
      abortRef.current = controller;

      const update = (change: (message: AssistantMessage) => AssistantMessage) =>
        setMessages((current) => {
          const copy = current.slice();
          const last = copy[copy.length - 1];
          if (last?.role === "assistant") copy[copy.length - 1] = change(last);
          return copy;
        });

      const onEvent = (event: StreamEvent) => {
        switch (event.type) {
          case "step":
            update((m) => ({ ...m, steps: [...m.steps, { id: event.id, tool: event.tool, label: event.label, args: event.args }] }));
            break;
          case "step_done":
            update((m) => ({
              ...m,
              steps: m.steps.map((step) => (step.id === event.id ? { ...step, ok: event.ok, summary: event.summary, memo: event.memo } : step)),
            }));
            break;
          case "block":
            update((m) => ({ ...m, blocks: [...m.blocks, event.block] }));
            break;
          case "token":
            update((m) => ({ ...m, content: m.content + event.text }));
            break;
          case "reset":
            update((m) => ({ ...m, content: "" }));
            break;
          case "final":
            update((m) => ({ ...m, content: event.text }));
            break;
          case "error":
            update((m) => ({ ...m, status: "error", error: event.message }));
            break;
          case "done":
            update((m) => ({ ...m, status: m.status === "error" ? "error" : "done", meta: { elapsed_ms: event.elapsed_ms, model: event.model, tools: event.tools } }));
            break;
        }
      };

      try {
        await streamAssistant(
          {
            messages: historyForServer(next),
            page: pageContext(window.location.pathname, window.location.search),
            timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
          },
          onEvent,
          controller.signal,
        );
        update((m) => (m.status === "streaming" ? { ...m, status: "done" } : m));
      } catch (error) {
        if (controller.signal.aborted) update((m) => ({ ...m, status: "stopped" }));
        else update((m) => ({ ...m, status: "error", error: error instanceof Error ? error.message : "The assistant is unavailable." }));
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [busy, messages],
  );

  useEffect(() => {
    const onAsk = (event: Event) => {
      const question = (event as CustomEvent<{ question: string }>).detail?.question;
      if (!question) return;
      onMode(mode === "closed" ? "open" : mode);
      void send(question);
    };
    window.addEventListener(ASK_EVENT, onAsk);
    return () => window.removeEventListener(ASK_EVENT, onAsk);
  }, [mode, onMode, send]);

  useEffect(() => {
    const onKey = (event: globalThis.KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        onMode(mode === "closed" ? "open" : "closed");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [mode, onMode]);

  function submit(event: FormEvent) {
    event.preventDefault();
    void send(input);
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send(input);
    } else if (event.key === "Escape" && !busy) {
      onMode("closed");
    }
  }

  function stop() {
    abortRef.current?.abort();
  }

  function retry() {
    const lastUser = [...messages].reverse().findIndex((message) => message.role === "user");
    if (lastUser < 0 || busy) return;
    const index = messages.length - 1 - lastUser;
    void send(messages[index].content, messages.slice(0, index));
  }

  function reset() {
    if (busy) stop();
    setMessages([]);
    save([]);
    inputRef.current?.focus();
  }

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => onMode("open")}
        className="fixed bottom-5 right-5 z-40 inline-flex items-center gap-2 rounded-full bg-night py-3 pl-4 pr-5 text-sm font-medium text-white shadow-lift ring-1 ring-white/10 transition hover:-translate-y-0.5 hover:bg-black"
        title="Ask the assistant (Ctrl+J)"
      >
        <Sparkles className="size-4 text-pine-soft" />
        Ask the desk
        <kbd className="ml-1 hidden rounded bg-white/10 px-1.5 py-0.5 font-sans text-[10px] text-white/60 sm:inline">Ctrl J</kbd>
      </button>
    );
  }

  const ideas = suggestions(context);
  const lastIndex = messages.length - 1;

  return (
    <aside
      className={`fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-line bg-desk shadow-lift sm:w-[440px] ${
        mode === "wide" ? "xl:w-[720px]" : ""
      }`}
      aria-label="Desk assistant"
    >
      <header className="flex items-center gap-2 border-b border-black/20 bg-night px-4 py-3 text-white">
        <Sparkles className="size-4 text-pine-soft" />
        <div className="min-w-0 flex-1 leading-tight">
          <p className="text-sm font-medium">Desk assistant</p>
          <p className="truncate text-[11px] text-white/50">
            {context.label}
            {model ? ` · ${model}` : ""}
          </p>
        </div>
        <button type="button" onClick={reset} title="New chat" className="rounded-md p-1.5 text-white/60 hover:bg-white/10 hover:text-white">
          <SquarePen className="size-4" />
        </button>
        <button
          type="button"
          onClick={() => onMode(mode === "wide" ? "open" : "wide")}
          title={mode === "wide" ? "Narrow" : "Widen"}
          className="hidden rounded-md p-1.5 text-white/60 hover:bg-white/10 hover:text-white xl:block"
        >
          {mode === "wide" ? <Minimize2 className="size-4" /> : <Maximize2 className="size-4" />}
        </button>
        <button type="button" onClick={() => onMode("closed")} title="Close (Ctrl+J)" className="rounded-md p-1.5 text-white/60 hover:bg-white/10 hover:text-white">
          <X className="size-4" />
        </button>
      </header>

      <div
        ref={scrollRef}
        onScroll={(event) => {
          const node = event.currentTarget;
          stickRef.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80;
        }}
        className="flex-1 space-y-5 overflow-y-auto px-4 py-4"
      >
        {messages.length === 0 && (
          <div className="animate-fade-up space-y-4 pt-6">
            <div>
              <p className="font-serif text-xl text-ink">Ask about this desk</p>
              <p className="mt-1 text-sm leading-6 text-ink/60">
                Jobs, candidates, fits, the pipeline, and reports. Answers come from your data, with the rows to back them up.
              </p>
            </div>
            <div className="flex flex-col gap-2">
              {ideas.map((idea) => (
                <button
                  key={idea}
                  type="button"
                  onClick={() => void send(idea)}
                  className="rounded-xl border border-line bg-white px-3 py-2 text-left text-sm text-ink/80 shadow-sm transition hover:border-pine/40 hover:text-ink"
                >
                  {idea}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((message, index) =>
          message.role === "user" ? (
            <div key={index} className="flex justify-end">
              <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-night px-3.5 py-2 text-sm text-white">{message.content}</p>
            </div>
          ) : (
            <div key={index} className="animate-fade-up space-y-2.5">
              <Steps message={message} />
              {message.blocks.map((block, blockIndex) => (
                <ResultBlock key={blockIndex} block={block} />
              ))}
              {message.content ? (
                <AnswerText text={message.content} blocks={message.blocks} />
              ) : message.status === "streaming" ? (
                <Thinking />
              ) : null}
              {message.status === "error" && (
                <p className="flex items-start gap-1.5 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                  <CircleAlert className="mt-0.5 size-3.5 shrink-0" />
                  {message.error}
                </p>
              )}
              {message.status === "stopped" && <p className="text-xs text-ink/45">Stopped.</p>}
              {message.status !== "streaming" && (
                <div className="flex items-center gap-1 text-[11px] text-ink/40">
                  {message.meta && <span>{(message.meta.elapsed_ms / 1000).toFixed(1)}s</span>}
                  {message.content && (
                    <button
                      type="button"
                      onClick={() => {
                        copyText(message.content);
                        setCopied(index);
                        setTimeout(() => setCopied(null), 1500);
                      }}
                      className="ml-1 rounded p-1 hover:bg-ink/5 hover:text-ink"
                      title="Copy answer"
                    >
                      {copied === index ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                    </button>
                  )}
                  {index === lastIndex && (
                    <button type="button" onClick={retry} className="rounded p-1 hover:bg-ink/5 hover:text-ink" title="Ask again">
                      <RotateCcw className="size-3.5" />
                    </button>
                  )}
                </div>
              )}
            </div>
          ),
        )}
      </div>

      <form onSubmit={submit} className="border-t border-line bg-white px-3 py-3">
        <div className="flex items-end gap-2 rounded-xl border border-line bg-white px-3 py-2 shadow-sm focus-within:border-pine/60 focus-within:ring-4 focus-within:ring-pine/15">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={2000}
            placeholder={context.code ? `Ask about ${context.code}…` : "Ask about jobs, candidates, or the pipeline…"}
            className="max-h-40 min-h-[24px] flex-1 resize-none bg-transparent text-sm text-ink outline-none placeholder:text-ink/40"
            style={{ height: "auto" }}
            onInput={(event) => {
              const node = event.currentTarget;
              node.style.height = "auto";
              node.style.height = `${Math.min(node.scrollHeight, 160)}px`;
            }}
          />
          {busy ? (
            <button type="button" onClick={stop} title="Stop" className="rounded-lg bg-ink/80 p-1.5 text-white hover:bg-ink">
              <Square className="size-4" />
            </button>
          ) : (
            <button type="submit" disabled={!input.trim()} title="Send (Enter)" className="rounded-lg bg-pine p-1.5 text-white transition hover:bg-pine-deep disabled:opacity-40">
              <ArrowUp className="size-4" />
            </button>
          )}
        </div>
        <p className="mt-1.5 px-1 text-[10px] text-ink/40">Reads your desk data only. It cannot change records. Enter to send, Shift+Enter for a new line.</p>
      </form>
    </aside>
  );
}
