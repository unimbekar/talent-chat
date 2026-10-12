"use client";

import { type FormEvent, type ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Copy, Cpu, Moon, Plus, SunMedium, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type ModelRow = { tag: string; label: string; note: string; added_at: string };

type DeskSettings = {
  theme: "dark" | "light";
  models: ModelRow[];
  chat_model: string;
  assistant_model: string;
  running_model: string;
  running_assistant_model: string;
  llm_backend: string;
  embedding_model: string;
  deploy_required: boolean;
  deploy_command: string;
};

const EMPTY: DeskSettings = {
  theme: "dark",
  models: [],
  chat_model: "",
  assistant_model: "",
  running_model: "",
  running_assistant_model: "",
  llm_backend: "",
  embedding_model: "",
  deploy_required: false,
  deploy_command: "docker compose up -d --build api",
};

function messageOf(data: { detail?: string | { msg?: string }[] }, fallback: string) {
  if (typeof data.detail === "string") return data.detail;
  return fallback;
}

export default function SettingsPage() {
  const router = useRouter();
  const [desk, setDesk] = useState<DeskSettings>(EMPTY);
  const [account, setAccount] = useState("");
  const [chat, setChat] = useState("");
  const [assistant, setAssistant] = useState("");
  const [tag, setTag] = useState("");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState("");
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let gone = false;
    async function load() {
      const session = await fetch("/api/admin/session");
      if (session.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (session.ok) {
        const claims = await session.json();
        if (!gone && claims.email) setAccount(claims.email);
      }
      const response = await fetch("/api/admin/settings");
      if (response.status === 401) {
        router.push("/admin/login");
        return;
      }
      if (!response.ok || gone) return;
      const data = (await response.json()) as DeskSettings;
      setDesk(data);
      setChat(data.chat_model);
      setAssistant(data.assistant_model === data.chat_model ? "" : data.assistant_model);
      document.documentElement.dataset.theme = data.theme;
    }
    load().catch(() => setError("Settings could not be loaded."));
    return () => {
      gone = true;
    };
  }, [router]);

  function apply(data: DeskSettings) {
    setDesk(data);
    setChat(data.chat_model);
    setAssistant(data.assistant_model === data.chat_model ? "" : data.assistant_model);
    document.documentElement.dataset.theme = data.theme;
  }

  async function saveTheme(theme: "dark" | "light") {
    if (theme === desk.theme) return;
    setError("");
    setNotice("");
    setBusy("theme");
    document.documentElement.dataset.theme = theme;
    try {
      const response = await fetch("/api/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme }),
      });
      const data = await response.json();
      if (!response.ok) {
        document.documentElement.dataset.theme = desk.theme;
        setError(messageOf(data, "The theme could not be saved."));
        return;
      }
      apply(data);
      setNotice(theme === "light" ? "Light background is on for the careers page and the desk." : "Dark background is on for the careers page and the desk.");
    } finally {
      setBusy("");
    }
  }

  async function saveModels(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy("models");
    try {
      const response = await fetch("/api/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_model: chat, assistant_model: assistant }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(messageOf(data, "The model choice could not be saved."));
        return;
      }
      apply(data);
      setNotice(data.deploy_required ? "Saved. Rebuild the API to deploy this model." : "Saved. The running process already uses this model.");
    } finally {
      setBusy("");
    }
  }

  async function addModel(event: FormEvent) {
    event.preventDefault();
    setError("");
    setNotice("");
    setBusy("add");
    try {
      const response = await fetch("/api/admin/settings/models", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tag, label, note }),
      });
      const data = await response.json();
      if (!response.ok) {
        setError(messageOf(data, "That model could not be added."));
        return;
      }
      apply(data);
      setTag("");
      setLabel("");
      setNote("");
      setNotice("Added to the catalog. Choose it below, then rebuild the API to deploy it.");
    } finally {
      setBusy("");
    }
  }

  async function removeModel(modelTag: string) {
    setError("");
    setNotice("");
    setBusy(modelTag);
    try {
      const response = await fetch(`/api/admin/settings/models?tag=${encodeURIComponent(modelTag)}`, { method: "DELETE" });
      const data = await response.json();
      if (!response.ok) {
        setError(messageOf(data, "That model could not be removed."));
        return;
      }
      apply(data);
      setNotice("Removed from the catalog.");
    } finally {
      setBusy("");
    }
  }

  async function copyCommand() {
    try {
      await navigator.clipboard.writeText(desk.deploy_command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }

  const choiceDirty = chat !== desk.chat_model || (assistant || desk.chat_model) !== desk.assistant_model;

  return (
    <main className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6">
      <p className="careers-kicker">Desk</p>
      <h1 className="page-title mt-2">Settings</h1>
      <p className="page-lead">Appearance applies at once. A new local model is recorded here and starts answering after the API is rebuilt.</p>

      {error && (
        <p className="mt-6 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800" role="alert">
          {error}
        </p>
      )}
      {notice && <p className="mt-6 rounded-xl border border-line bg-card px-4 py-3 text-sm text-ink/80">{notice}</p>}

      <section className="panel mt-8 p-5 sm:p-6">
        <h2 className="text-lg font-medium tracking-tight">Appearance</h2>
        <p className="mt-1 text-sm text-ink/60">The careers page and the recruiter desk share this background.</p>
        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <ThemeCard
            name="Dark"
            detail="Night field, light type"
            selected={desk.theme === "dark"}
            disabled={busy === "theme"}
            onSelect={() => saveTheme("dark")}
            icon={<Moon className="size-4" />}
            swatch="dark"
          />
          <ThemeCard
            name="Light"
            detail="Paper field, dark type"
            selected={desk.theme === "light"}
            disabled={busy === "theme"}
            onSelect={() => saveTheme("light")}
            icon={<SunMedium className="size-4" />}
            swatch="light"
          />
        </div>
      </section>

      <section className="panel mt-6 p-5 sm:p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-medium tracking-tight">Local models</h2>
            <p className="mt-1 text-sm leading-6 text-ink/60">
              Add an Ollama tag that is already on this machine. Saving a choice does not switch the live process.
            </p>
          </div>
          <Cpu className="mt-1 hidden size-5 text-ink/40 sm:block" />
        </div>

        <dl className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-line bg-desk/60 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-ink/45">Running now</dt>
            <dd className="mt-1 font-mono text-sm">{desk.running_model || "—"}</dd>
            <dd className="mt-1 text-xs text-ink/50">
              Assistant {desk.running_assistant_model && desk.running_assistant_model !== desk.running_model ? desk.running_assistant_model : "uses the same model"}
            </dd>
          </div>
          <div className="rounded-xl border border-line bg-desk/60 px-4 py-3">
            <dt className="text-xs uppercase tracking-wide text-ink/45">Saved for the next start</dt>
            <dd className="mt-1 font-mono text-sm">{desk.chat_model || "—"}</dd>
            <dd className="mt-1 text-xs text-ink/50">{desk.deploy_required ? "Waiting for a rebuild" : "Matches the running process"}</dd>
          </div>
        </dl>

        {desk.deploy_required && (
          <div className="mt-4 rounded-xl border border-amber-300/40 bg-amber-50 px-4 py-4 text-sm text-amber-950">
            <p className="font-medium">Rebuild required</p>
            <p className="mt-1 leading-6">
              From the project directory, rebuild the API. Ollama must already have the tag. This does not download weights. Check with <span className="font-mono">ollama list</span>, or pull first with <span className="font-mono">ollama pull {desk.chat_model}</span>.
            </p>
            <div className="mt-3 flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-lg border border-amber-300/50 bg-white/70 px-3 py-2 font-mono text-xs">{desk.deploy_command}</code>
              <Button type="button" variant="outline" size="sm" onClick={copyCommand}>
                {copied ? <Check /> : <Copy />}
                {copied ? "Copied" : "Copy"}
              </Button>
            </div>
          </div>
        )}

        <form onSubmit={saveModels} className="mt-5">
          <label className="mb-3 inline-flex items-center gap-2 text-sm">
            <input type="radio" name="assistant" checked={assistant === ""} onChange={() => setAssistant("")} />
            Assistant uses the answers model
          </label>
          <ul className="divide-y divide-line overflow-hidden rounded-xl border border-line">
            {desk.models.map((model) => {
              const running = model.tag === desk.running_model || model.tag === desk.running_assistant_model;
              return (
                <li key={model.tag} className="flex flex-col gap-3 bg-card px-4 py-4 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-mono text-sm">{model.tag}</p>
                    <p className="mt-0.5 truncate text-sm text-ink/70">{model.label}</p>
                    {model.note && <p className="mt-1 text-xs leading-5 text-ink/50">{model.note}</p>}
                    {running && <p className="mt-1 text-xs text-ink/45">Running</p>}
                  </div>
                  <fieldset className="flex flex-wrap items-center gap-3 text-sm">
                    <legend className="sr-only">{model.label}</legend>
                    <label className="inline-flex items-center gap-2">
                      <input type="radio" name="chat" checked={chat === model.tag} onChange={() => setChat(model.tag)} />
                      Answers
                    </label>
                    <label className="inline-flex items-center gap-2">
                      <input
                        type="radio"
                        name="assistant"
                        checked={assistant === model.tag}
                        onChange={() => setAssistant(model.tag)}
                      />
                      Assistant
                    </label>
                    <button
                      type="button"
                      className="inline-flex items-center gap-1 text-xs text-ink/50 hover:text-red-700 disabled:opacity-40"
                      disabled={running || busy === model.tag}
                      onClick={() => removeModel(model.tag)}
                    >
                      <Trash2 className="size-3.5" />
                      Remove
                    </button>
                  </fieldset>
                </li>
              );
            })}
          </ul>
          <p className="mt-3 text-xs leading-5 text-ink/50">
            Leave the assistant unset to use the answers model for the desk assistant as well. Embeddings stay on {desk.embedding_model || "the installed embedding model"} and are not changed here.
          </p>
          <Button type="submit" className="mt-4" disabled={busy === "models" || !choiceDirty || !chat}>
            {busy === "models" ? "Saving…" : "Save model choice"}
          </Button>
        </form>

        <form onSubmit={addModel} className="mt-8 border-t border-line pt-6">
          <h3 className="text-sm font-medium">Add a local model</h3>
          <div className="mt-4 grid gap-3 sm:grid-cols-2">
            <div>
              <Label htmlFor="model-tag">Ollama tag</Label>
              <Input id="model-tag" className="mt-1.5 font-mono" value={tag} onChange={(event) => setTag(event.target.value)} placeholder="qwen3.6:latest" autoComplete="off" required />
            </div>
            <div>
              <Label htmlFor="model-label">Display name</Label>
              <Input id="model-label" className="mt-1.5" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Qwen 3.6" autoComplete="off" />
            </div>
          </div>
          <div className="mt-3">
            <Label htmlFor="model-note">Note</Label>
            <Input id="model-note" className="mt-1.5" value={note} onChange={(event) => setNote(event.target.value)} placeholder="Used for visitor answers" autoComplete="off" />
          </div>
          <Button type="submit" variant="outline" className="mt-4" disabled={busy === "add" || !tag.trim()}>
            <Plus />
            {busy === "add" ? "Adding…" : "Add to catalog"}
          </Button>
        </form>
      </section>

      <section className="panel mt-6 p-5 sm:p-6">
        <h2 className="text-lg font-medium tracking-tight">Runtime</h2>
        <dl className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink/45">Backend</dt>
            <dd className="mt-1 text-sm">{desk.llm_backend || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink/45">Embeddings</dt>
            <dd className="mt-1 break-all text-sm">{desk.embedding_model || "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-ink/45">Signed-in account</dt>
            <dd className="mt-1 break-all text-sm">{account || "—"}</dd>
          </div>
        </dl>
        <p className="mt-4 text-sm text-ink/55">
          The account is the session you signed in with. Change the password on the <Link href="/admin/password" className="text-pine-deep underline-offset-2 hover:underline">password page</Link>.
        </p>
      </section>
    </main>
  );
}

function ThemeCard({
  name,
  detail,
  selected,
  disabled,
  onSelect,
  icon,
  swatch,
}: {
  name: string;
  detail: string;
  selected: boolean;
  disabled: boolean;
  onSelect: () => void;
  icon: ReactNode;
  swatch: "dark" | "light";
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={`rounded-2xl border p-3 text-left transition ${selected ? "border-pine ring-4 ring-pine/15" : "border-line hover:border-pine/40"}`}
    >
      <span className={`block h-24 overflow-hidden rounded-xl border ${swatch === "dark" ? "border-white/10 bg-[#070b12]" : "border-black/10 bg-[#f4f7fb]"}`}>
        <span className={`block h-2 ${swatch === "dark" ? "bg-[#9ce2ff]" : "bg-[#122033]"}`} />
        <span className="block px-3 pt-3">
          <span className={`block h-2 w-16 rounded-full ${swatch === "dark" ? "bg-white/80" : "bg-[#152433]"}`} />
          <span className={`mt-2 block h-2 w-24 rounded-full ${swatch === "dark" ? "bg-white/25" : "bg-[#152433]/20"}`} />
        </span>
      </span>
      <span className="mt-3 flex items-center gap-2 text-sm font-medium">
        {icon}
        {name}
        {selected && <Check className="ml-auto size-4 text-pine-deep" />}
      </span>
      <span className="mt-0.5 block text-xs text-ink/55">{detail}</span>
    </button>
  );
}
