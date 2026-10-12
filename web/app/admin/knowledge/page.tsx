"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BookOpen } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCan } from "@/lib/desk";

type DocumentRow = {
  id: string;
  title: string;
  audience: string;
  source_name: string;
  chunks: number;
  characters: number;
  updated_at: string | null;
  body?: string;
};

const AUDIENCE: Record<string, string> = {
  public: "Careers visitors",
  internal: "Internal",
};

export default function KnowledgePage() {
  const router = useRouter();
  const canEdit = useCan("knowledge_edit");
  const canDelete = useCan("delete");
  const [rows, setRows] = useState<DocumentRow[]>([]);
  const [title, setTitle] = useState("");
  const [audience, setAudience] = useState("public");
  const [text, setText] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const [editing, setEditing] = useState<DocumentRow | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    const response = await fetch("/api/admin/knowledge");
    if (response.status === 401) {
      router.push("/admin/login");
      return;
    }
    const data = await response.json().catch(() => ({ documents: [] }));
    setRows(data.documents || []);
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    const form = new FormData();
    form.set("title", title);
    form.set("audience", audience);
    form.set("text", text);
    if (file) form.set("file", file);
    try {
      const response = await fetch("/api/admin/knowledge", { method: "POST", body: form });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(typeof data.detail === "string" ? data.detail : "The document was not saved.");
        return;
      }
      setTitle("");
      setText("");
      setFile(null);
      setFileKey((key) => key + 1);
      setAudience("public");
      await load();
    } catch {
      setError("The server did not answer. Try again.");
    } finally {
      setBusy(false);
    }
  }

  async function openRow(id: string) {
    setError("");
    const response = await fetch(`/api/admin/knowledge/${id}`);
    if (!response.ok) {
      setError("That document could not be opened.");
      return;
    }
    setEditing(await response.json());
  }

  async function saveEdit(event: FormEvent) {
    event.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/knowledge/${editing.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title: editing.title, audience: editing.audience, body: editing.body }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        setError(typeof data.detail === "string" ? data.detail : "The document was not saved.");
        return;
      }
      setEditing(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      const response = await fetch(`/api/admin/knowledge/${id}`, { method: "DELETE" });
      if (!response.ok) {
        setError("The document was not deleted.");
        return;
      }
      if (editing?.id === id) setEditing(null);
      await load();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <p className="text-xs uppercase tracking-[0.18em] text-pine-deep">Library</p>
        <h1 className="mt-1 font-serif text-3xl">Knowledge base</h1>
        <p className="mt-2 text-sm leading-6 text-ink/65">
          {canEdit
            ? "Upload any document people should be able to ask about: benefits, onboarding, expenses, a procedure, or a research note. Careers visitors can ask about documents marked for them. Internal documents stay off the public site."
            : "The documents the desk assistant and the careers site answer from. Open one to read it. An admin adds, edits, or removes documents."}
        </p>
      </div>
      {canEdit && (
      <form onSubmit={onCreate} className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm">
        <span className="inline-flex size-10 items-center justify-center rounded-xl bg-pine/10 text-pine-deep">
          <BookOpen className="size-5" />
        </span>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kb-title">Title</Label>
          <Input id="kb-title" value={title} onChange={(event) => setTitle(event.target.value)} required minLength={2} maxLength={200} placeholder="Expense procedure" />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kb-audience">Who can ask about it</Label>
          <select id="kb-audience" className="field h-10" value={audience} onChange={(event) => setAudience(event.target.value)}>
            <option value="public">Careers visitors</option>
            <option value="internal">Internal only</option>
          </select>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kb-file">File</Label>
          <Input key={fileKey} id="kb-file" type="file" accept=".pdf,.doc,.docx,.txt" onChange={(event) => setFile(event.target.files?.[0] || null)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="kb-text">Or paste the text</Label>
          <textarea id="kb-text" value={text} onChange={(event) => setText(event.target.value)} rows={6} className="field min-h-32 px-3 py-2" placeholder="Paste a section if you are not uploading a file." />
        </div>
        {error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{error}</p>}
        <Button type="submit" disabled={busy || title.trim().length < 2 || (!text.trim() && !file)}>
          {busy ? "Saving…" : "Add document"}
        </Button>
      </form>
      )}
      {!canEdit && error && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800" role="alert">{error}</p>}
      <ul className="flex flex-col gap-3">
        {rows.map((row) => (
          <li key={row.id} className="rounded-2xl border border-line bg-white px-4 py-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-medium">{row.title}</p>
                <p className="mt-1 text-xs text-ink/50">
                  {AUDIENCE[row.audience] || row.audience} · {row.chunks} section{row.chunks === 1 ? "" : "s"} · {row.source_name}
                </p>
              </div>
              <div className="flex gap-2">
                <Button type="button" variant="outline" onClick={() => void openRow(row.id)}>{canEdit ? "Edit" : "Open"}</Button>
                {canDelete && <Button type="button" variant="outline" onClick={() => void remove(row.id)}>Delete</Button>}
              </div>
            </div>
          </li>
        ))}
        {rows.length === 0 && <li className="text-sm text-ink/50">No documents yet.</li>}
      </ul>
      {editing && !canEdit && (
        <article className="flex flex-col gap-3 rounded-2xl border border-line bg-white p-5 shadow-sm">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="font-serif text-2xl">{editing.title}</h2>
              <p className="mt-1 text-xs text-ink/50">{AUDIENCE[editing.audience] || editing.audience} · {editing.source_name}</p>
            </div>
            <Button type="button" variant="outline" onClick={() => setEditing(null)}>Close</Button>
          </div>
          <p className="max-h-[32rem] overflow-y-auto whitespace-pre-wrap text-sm leading-6 text-ink/80">{editing.body || "This document has no text."}</p>
        </article>
      )}
      {editing && canEdit && (
        <form onSubmit={saveEdit} className="flex flex-col gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm">
          <h2 className="font-serif text-2xl">Edit {editing.title}</h2>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-title">Title</Label>
            <Input id="edit-title" value={editing.title} onChange={(event) => setEditing({ ...editing, title: event.target.value })} required />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-audience">Who can ask about it</Label>
            <select id="edit-audience" className="field h-10" value={editing.audience} onChange={(event) => setEditing({ ...editing, audience: event.target.value })}>
              <option value="public">Careers visitors</option>
              <option value="internal">Internal only</option>
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-body">Text</Label>
            <textarea id="edit-body" value={editing.body || ""} onChange={(event) => setEditing({ ...editing, body: event.target.value })} rows={10} className="field min-h-40 px-3 py-2" />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy}>Save changes</Button>
            <Button type="button" variant="outline" onClick={() => setEditing(null)}>Close</Button>
          </div>
        </form>
      )}
    </div>
  );
}
